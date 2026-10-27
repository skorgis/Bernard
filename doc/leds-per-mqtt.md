# LEDs schalten per MQTT

Am Parkplatz hängen LEDs, die ihr aus eurem Programm schalten könnt, zum
Beispiel als Richtungspfeil oder als „Parkplatz frei“-Anzeige. Dafür schickt
ihr eine MQTT-Nachricht an denselben Broker, von dem ihr auch die Events des
BMA bekommt. Ihr kennt MQTT schon vom **Abonnieren**; für die LEDs
**veröffentlicht** ihr selbst eine Nachricht.

```
 ┌──────────────────┐  Befehl auf                ┌──────────────────┐
 │ euer Programm    │  bmc_interface/            │ Raspberry Pi     │
 │                  │  tirol-hackathon/out ────► │ Mosquitto-Broker │
 └──────────────────┘                            └────────┬─────────┘
                                                          │ LAN-Kabel
                                                 ┌────────▼─────────┐
                                                 │ BMA: bmc-interface│──► BMC ──► LED
                                                 └──────────────────┘
```

## Was ihr braucht

| Angabe | Wert |
|---|---|
| Broker | `localhost`, wenn euer Programm auf dem Pi läuft; vom Laptop aus `hackathon.local` |
| Port | `1883` |
| Benutzer / Passwort | bekommt ihr von den Betreuern (`MQTT_USER` / `MQTT_PASSWORD`) |
| Topic für LED-Befehle | `bmc_interface/tirol-hackathon/out` |
| BMA-ID (`target_uuid`) | `f6b51cd4-4469-4138-831a-b5cc471f9e45` |
| LEDs | Kontakte **1–10**; welche LED an welchem Kontakt hängt, sagen euch die Betreuer |
| Teamname (`source_uuid`) | euer eigener, fester Name, z. B. `team-1` |

## Schnelltest

Passwort einmal pro Terminal setzen (wird nicht angezeigt und landet nicht in
der Shell-History):

```bash
read -rs MQTT_PASSWORD && export MQTT_USER=hackathon MQTT_PASSWORD
```

LED 3 an, aus, und einmal kurz (2 Sekunden):

```bash
uv run python examples/bmc_mqtt_switch.py --team team-1 --contact 3 --on
```

```bash
uv run python examples/bmc_mqtt_switch.py --team team-1 --contact 3 --off
```

```bash
uv run python examples/bmc_mqtt_switch.py --team team-1 --contact 3 --on --duration 2
```

## Die Nachricht

Jeder LED-Befehl ist ein JSON-Objekt:

```json
{
  "command_id": "6b0f3e4c-8a1d-4c55-9a62-3f0c1f9c2d11",
  "target_uuid": "f6b51cd4-4469-4138-831a-b5cc471f9e45",
  "source_uuid": "team-1",
  "command": "ENABLE",
  "timestamp": "2026-10-27T13:52:00.123456+00:00",
  "contacts": [
    {"id": "3", "type": "permanent", "state": "ON"},
    {"id": "4", "type": "normal", "state": "ON", "duration": 2.0}
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `command_id` | für **jede** Nachricht eine neue ID, z. B. `str(uuid.uuid4())` |
| `target_uuid` | welcher BMA gemeint ist; steht auch in jedem Event unter `node.id` |
| `source_uuid` | euer **Teamname**, immer derselbe |
| `command` | immer `"ENABLE"` (Ausnahme: `"RESET"`, siehe unten) |
| `timestamp` | **jetzt**, in UTC, mit `+00:00` am Ende |
| `contacts` | Liste der LEDs, die geschaltet werden; mehrere in einer Nachricht sind erlaubt |

Jeder Eintrag in `contacts`:

| Feld | Werte |
|---|---|
| `id` | Kontaktnummer als Text, `"1"` bis `"10"` |
| `type` | `"permanent"`: bleibt so bis zum nächsten Befehl. `"normal"`: geht an und nach `duration` Sekunden von selbst wieder aus |
| `state` | `"ON"` oder `"OFF"` |
| `duration` | nur bei `"normal"`: Sekunden (Standard 1) |

### Regeln

Eine Nachricht wird **ohne Fehlermeldung ignoriert**, wenn …

- `target_uuid` nicht stimmt,
- `timestamp` älter als **5 Sekunden** ist oder auf **`Z`** endet statt auf
  `+00:00`. Nehmt deshalb nie den Zeitstempel eines Events, sondern erzeugt
  immer einen neuen: `datetime.now(timezone.utc).isoformat()`,
- eine `id` außerhalb von 1–10 liegt (11 und 12 sind belegt),
- bei `"permanent"` eine `duration` angegeben ist,
- euer Team gesperrt ist: Mehr als **600 Nachrichten in 5 Minuten** sperren
  den Teamnamen. Die Sperre endet von selbst, sobald ihr langsamer werdet,
  oder sofort mit einer Nachricht `"command": "RESET"` mit eurem Teamnamen.

`"normal"` mit `"OFF"` bewirkt nichts; zum Ausschalten `"permanent"` mit
`"OFF"` schicken.

## In Python

`paho-mqtt` ist im Projekt schon installiert. Diese Funktion versteckt das
Nachrichtenformat:

```python
import json
import os
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

LED_TOPIC = "bmc_interface/tirol-hackathon/out"
BMA_ID = "f6b51cd4-4469-4138-831a-b5cc471f9e45"
TEAM = "team-1"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASSWORD"])
client.connect(os.environ.get("MQTT_HOST", "hackathon.local"), 1883)
client.loop_start()


def led(nummer, an, dauer=None):
    """Schaltet LED `nummer` (1-10) an oder aus; mit `dauer` nur kurz an."""
    kontakt = {"id": str(nummer), "type": "permanent", "state": "ON" if an else "OFF"}
    if dauer is not None:
        kontakt.update(type="normal", duration=dauer)
    befehl = {
        "command_id": str(uuid.uuid4()),
        "target_uuid": BMA_ID,
        "source_uuid": TEAM,
        "command": "ENABLE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contacts": [kontakt],
    }
    client.publish(LED_TOPIC, json.dumps(befehl), qos=1)


led(3, True)           # LED 3 an
time.sleep(2)
led(3, False)          # LED 3 aus
led(5, True, dauer=1)  # LED 5 leuchtet 1 Sekunde
time.sleep(1)          # kurz warten, damit die letzte Nachricht rausgeht
```

## Auf Events reagieren

Die Events des BMA kommen auf dem Topic `bma/events` (Format: Schema 6.0,
siehe [„Die BMA-Events verstehen“](../README.md#die-bma-events-verstehen)).
So sieht ein echtes Event aus, gekürzt: ein Auto steht in einer Zone.

```json
{
  "version": "6.0",
  "node": {"id": "f6b51cd4-4469-4138-831a-b5cc471f9e45", "name": "G-A2610-0007"},
  "regionOfInterestEvent": {
    "roiId": "8e40652d-1333-43a3-96f5-3c0b07ea0326",
    "roiName": "",
    "state": "occupied",
    "triggerType": "time",
    "objects": [{"class": "car", "dwellTime": 203}],
    "timestamp": "2026-10-27T13:51:27.680198Z"
  }
}
```

Ein Auto, das eine Linie überquert, kommt als `crossingLineEvent` mit
`lineName`, `class`, `direction` (`"in"` oder `"out"`) und `timestamp`.

Dieses Beispiel schaltet LED 1, solange die Zone belegt ist, und lässt LED 2
bzw. 3 kurz aufleuchten, wenn ein Auto ein- oder ausfährt. Es nutzt die
Funktion `led()` von oben:

```python
EVENT_TOPIC = "bma/events"
letzter_zustand = {}  # roiId -> True/False


def bei_event(client, userdata, nachricht):
    event = json.loads(nachricht.payload)

    if roi := event.get("regionOfInterestEvent"):
        belegt = roi["state"] == "occupied"
        # Zonen melden sich alle 10 s, auch ohne Änderung: nur Änderungen senden.
        if letzter_zustand.get(roi["roiId"]) != belegt:
            letzter_zustand[roi["roiId"]] = belegt
            led(1, belegt)

    elif linie := event.get("crossingLineEvent"):
        led(2 if linie["direction"] == "in" else 3, True, dauer=2)


client.on_message = bei_event
client.subscribe(EVENT_TOPIC)
client.loop_forever()
```

## Ohne Auto testen

Alle dürfen auf alle Topics schreiben. Ihr könnt also selbst ein Event auf
`bma/events` veröffentlichen, um euer Programm zu testen, z. B. mit dem Event
von oben. Denkt daran, dass die anderen Teams eure Test-Events auch bekommen:
gebt Zonen und Linien in Test-Events einen eindeutigen Namen.

## Rückmeldung sehen

`bmc-interface` meldet jeden geschalteten Kontakt auf
`bmc_interface/tirol-hackathon/events`, inklusive eures Teamnamens:

```bash
mosquitto_sub -h hackathon.local -u "$MQTT_USER" -P "$MQTT_PASSWORD" \
-t 'bmc_interface/tirol-hackathon/#' -v
```

## Hilfe, die LED geht nicht an

| Was ihr seht | Ursache |
|---|---|
| `Broker refused connection: Not authorized` | Benutzer oder Passwort falsch |
| Befehl geht raus, aber auf `…/events` erscheint nichts | Nachricht wurde ignoriert: `target_uuid`, Zeitstempel (älter als 5 s oder mit `Z`), `id` außerhalb 1–10, oder euer Team ist gesperrt |
| Euer Programm schickt sehr viele Befehle | Spam-Sperre: langsamer werden oder `"command": "RESET"` senden |
| Auf `…/events` erscheint der Kontakt, die LED bleibt dunkel | Verdrahtung: fragt die Betreuer |
