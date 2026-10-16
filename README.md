# Tirol Hackathon: Smartes Lego-Parkhaus mit dem BERNARD BMA

Willkommen beim Hackathon! In diesem Repository findest du alles, was du
brauchst, um mit unserem Kamerasystem **BMAv3** zu arbeiten.

## Die Challenge

Auf einem Lego-Parkplatz werden Modellautos herumgeschoben. Ein BMAv3
beobachtet den Parkplatz und erkennt die Autos. Eure Aufgabe:

> **Zeigt jedem ankommenden Auto auf einem kleinen Bildschirm an, in welche
> Richtung es fahren soll, um einen freien Parkplatz zu finden.**

**Bonus:** Erkennt spezielle Symbole am Auto, zum Beispiel ein
Rollstuhl-Kennzeichen, und leitet diese Autos zu einem Behindertenparkplatz.

## Der Aufbau

```
 ┌──────────────┐   MQTT-Events   ┌──────────────────────────────┐
 │  BMAv3       │ ──────────────► │  Raspberry Pi                │
 │  (erkennt    │                 │  ├─ Mosquitto (MQTT-Broker)  │
 │   die Autos) │                 │  ├─ euer Python-Programm     │
 └──────────────┘                 │  └─ TFT-Bildschirm (Schild)  │
                                  └──────────────────────────────┘
 ┌──────────────┐   Kamerabild           ▲
 │  Webcam      │ ───────────────────────┘   (nur für den Bonus)
 └──────────────┘
```

1. Der **BMA** erkennt die Autos auf dem Parkplatz. Bei jeder Erkennung
   verschickt er eine Nachricht (ein **Event**) im JSON-Format.
2. Die Events landen auf einem **MQTT-Broker** (Mosquitto), der auf dem
   Raspberry Pi läuft. MQTT funktioniert wie ein Briefkasten-System: Der BMA
   wirft Nachrichten unter einem **Topic** (einer Art Adresse) ein, und euer
   Programm abonniert dieses Topic und bekommt jede Nachricht.
3. **Euer Programm** wertet die Events aus, entscheidet, wohin das Auto soll,
   und zeigt die Richtung auf dem **TFT-Bildschirm** an.
4. **Bonus:** Mit einer Webcam und der Logo-Erkennung aus diesem Repository
   erkennt ihr Symbole wie das Rollstuhl-Kennzeichen.

## Was ist schon fertig?

Ihr müsst nicht bei null anfangen. Dieses Repository enthält zwei fertige
Bausteine:

| Baustein | Wofür? | Doku |
| --- | --- | --- |
| `detection_worker` | Verbindet sich mit dem MQTT-Broker, liest die BMA-Events und wandelt sie in Python-Objekte um. Ihr könnt Funktionen registrieren, die bei bestimmten Events aufgerufen werden. | [src/detection_worker/README.md](src/detection_worker/README.md) |
| `picture_pipeline` | Findet bekannte Logos/Symbole in Kamerabildern, inklusive einer Oberfläche zum Ausprobieren und Einstellen. Für den Bonus. | [src/picture_pipeline/README.md](src/picture_pipeline/README.md) |

Der Teil, den ihr selbst baut: **die Logik** (welcher Platz ist frei, wohin
schicke ich das Auto?) und **die Anzeige** auf dem Bildschirm.

## Schnellstart

### 1. Werkzeuge installieren

Ihr braucht **Git** und **uv**. uv installiert automatisch die passende
Python-Version (≥ 3.12) und alle Bibliotheken, ihr müsst Python also nicht
selbst installieren.

uv installieren (Linux/macOS):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Unter Windows (PowerShell):

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Projekt holen und einrichten

```bash
git clone <TODO: Repository-URL>
cd Tirol-Hackathon
uv sync
```

`uv sync` legt eine virtuelle Umgebung im Ordner `.venv` an und installiert
alles, was das Projekt braucht. Danach startet ihr Python-Programme immer mit
`uv run`, zum Beispiel `uv run python mein_programm.py`.

### 3. Prüfen, ob Events ankommen

Bevor ihr programmiert, schaut euch an, was der BMA überhaupt verschickt. Auf
dem Raspberry Pi ist der Mosquitto-Client installiert:

```bash
mosquitto_sub -h <TODO: Hostname/IP des Pi> -t '<TODO: Topic>' -v
```

Schiebt ein Auto über den Parkplatz. Ihr solltet JSON-Nachrichten sehen. Mit
`-t '#'` seht ihr alle Topics auf einmal.

> **Tipp:** Kopiert euch eine echte Nachricht in eine Datei. Damit könnt ihr
> euren Code später auch ohne laufenden BMA testen (siehe
> [Ohne BMA testen](#ohne-bma-testen)).

### 4. Euer erstes Programm

Speichert dieses Beispiel als `parkhaus.py` im Hauptordner des Projekts. Es
verbindet sich mit dem Broker und gibt aus, wenn ein Parkplatz belegt oder
frei wird.

```python
"""Print parking space changes reported by the BMA."""

import logging
import os
import signal

from detection_worker.data import Event, RegionOfInterestEvent, parse_event
from detection_worker.dispatch import EventDispatcher, HandlerKey
from detection_worker.transport.client import Client, MqttConfig

TOPIC = "<TODO: Topic>"

logging.basicConfig(level=logging.INFO)


def on_parking_space(event: Event, roi: RegionOfInterestEvent) -> None:
    print(f"Parkplatz {roi.roiName}: {roi.state}")


dispatcher = EventDispatcher()
# None = every parking space on this topic; use a roiName for a single one.
dispatcher.add_handler(
    HandlerKey(TOPIC, None, RegionOfInterestEvent), on_parking_space
)

client = Client(
    MqttConfig(
        broker_host=os.environ.get("MQTT_HOST", "<TODO: Hostname/IP des Pi>"),
        broker_port=1883,
        client_id="team-<euer-teamname>",
        broker_username=os.environ.get("MQTT_USER"),
        broker_password=os.environ.get("MQTT_PASSWORD"),
    )
)
client.set_on_connect(lambda rc: client.subscribe(TOPIC))
client.set_on_message(
    lambda topic, payload: dispatcher.dispatch(topic, parse_event(payload))
)

client.connect()
client.loop_start()
try:
    signal.pause()  # wait until Ctrl+C
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop()
    client.disconnect()
```

Starten:

```bash
uv run python parkhaus.py
```

Beenden mit **Strg+C**.

> **Wichtig:** Jedes Team braucht eine eigene `client_id`. Zwei Programme mit
> derselben ID werfen sich gegenseitig vom Broker.

> **Zugangsdaten:** Benutzername und Passwort für den Broker gehören nie in
> den Code und nie in Git. Setzt sie als Umgebungsvariablen, bevor ihr das
> Programm startet:
>
> ```bash
> export MQTT_HOST=<Hostname/IP des Pi>
> export MQTT_USER=<Benutzer>
> export MQTT_PASSWORD=<Passwort>
> ```

## Die BMA-Events verstehen

Jede Nachricht des BMA ist ein `Event`. Je nachdem, welche Regel am BMA
ausgelöst hat, ist **genau eines** der folgenden Felder gefüllt:

| Feld | Bedeutung | Im Parkhaus z. B. für |
| --- | --- | --- |
| `regionOfInterestEvent` | Zustand einer Zone: `state` ist `"occupied"` (belegt) oder `"vacant"` (frei). Name der Zone in `roiName`. | Ist Parkplatz 3 frei? |
| `parkingEvent` | Zusammenfassung mehrerer Parkzonen: Kapazität und Anzahl Fahrzeuge je Zone (`parkingSummary`). | Wie viele Plätze sind insgesamt frei? |
| `crossingLineEvent` | Ein Fahrzeug hat eine virtuelle Linie überquert. Name in `lineName`, Richtung in `direction` (`"in"`/`"out"`). | Ein Auto fährt ein, jetzt Schild anzeigen! |
| `virtualDoorEvent` | Ein Fahrzeug ist durch eine virtuelle Tür gegangen. | Ein- und Ausfahrt zählen |
| `originDestinationEvent` | Ein Fahrzeug ist von Zone A nach Zone B gefahren. | Wohin ist das Auto tatsächlich gefahren? |

Mit dem `EventDispatcher` registriert ihr für jede Art von Event eine eigene
Funktion. Der `HandlerKey` legt fest, wann sie aufgerufen wird:

```python
HandlerKey(topic, name, event_type)
#          │      │     └─ z. B. RegionOfInterestEvent, CrossingLineEvent
#          │      └─ Name der Zone/Linie, oder None für alle
#          └─ das MQTT-Topic
```

Beispiel: eine Funktion nur für die Einfahrt-Linie.

```python
from detection_worker.data import CrossingLineEvent


def on_entry(event: Event, line: CrossingLineEvent) -> None:
    if line.direction == "in":
        print("Auto fährt ein:", line.class_)


dispatcher.add_handler(
    HandlerKey(TOPIC, "<TODO: Name der Einfahrt-Linie>", CrossingLineEvent),
    on_entry,
)
```

Alle Felder der Events findet ihr in `src/detection_worker/data/models/`. Die
offizielle Beschreibung des Formats (Schema 6.0) steht unter
<https://docs.bernard-gruppe.com/events/schema/>.

### Wie ist der BMA eingerichtet?

<!-- TODO: fill in once the BMA configuration for the parking lot is final. -->

| Name (`roiName` / `lineName`) | Typ | Bedeutung |
| --- | --- | --- |
| `<TODO>` | Linie | Einfahrt |
| `<TODO>` | Zone | Parkplatz 1 |
| `<TODO>` | Zone | Behindertenparkplatz |

## Das Schild: der TFT-Bildschirm

<!-- TODO: describe how the TFT display is driven (library, resolution,
     example code), or whether that is left to the teams. -->

Der TFT-Bildschirm hängt am Raspberry Pi. **TODO:** Wie man ihn anspricht,
welche Bibliothek und welche Auflösung, ergänzen wir hier.

Ideen für die Anzeige:

- Ein großer Pfeil (←, ↑, →) und die Nummer des Parkplatzes
- „Besetzt“, wenn alles voll ist
- Ein Rollstuhl-Symbol, wenn das Auto zum Behindertenparkplatz geleitet wird

## Bonus: Symbole erkennen

Mit `picture_pipeline` findet ihr Logos und Symbole im Bild einer Webcam.

1. Legt ein Bild des Symbols (z. B. Rollstuhl-Kennzeichen) in den Ordner
   `logos/`. Der Dateiname wird zum Namen des Logos, zum Beispiel
   `logos/rollstuhl.png`.
2. Startet die Oberfläche zum Ausprobieren:

   ```bash
   uv run python examples/logo_webcam.py
   ```

   Wählt oben rechts die Kamera aus und haltet ein Auto mit Symbol davor.
   Mit den Reglern stellt ihr die Erkennung ein. **Einstellungen speichern**
   schreibt sie nach `logo_tuner_settings.json` und gibt den passenden
   Python-Code aus.
3. Im eigenen Programm:

   ```python
   from picture_pipeline.logo_loading import load_logos
   from picture_pipeline.tuning import TuningSettings

   logos = load_logos("logos")
   pipeline = TuningSettings.load("logo_tuner_settings.json").build_pipeline(logos)
   analysis = pipeline.analyze(frame)  # frame: ein Kamerabild von OpenCV
   if analysis.results["rollstuhl"].found:
       print("Rollstuhl-Symbol erkannt!")
   ```

Gut zu wissen:

- Das Symbol braucht **Details und Kanten**. Ein einfarbiger Kreis wird nicht
  erkannt.
- Schneidet das Bild des Symbols **eng** zu, ohne viel Hintergrund.
- Prüft zuerst die **Schärfe** der Kamera, wenn nichts gefunden wird.

Mehr dazu in [src/picture_pipeline/README.md](src/picture_pipeline/README.md).

## Ohne BMA testen

Ihr müsst nicht warten, bis ein Auto über den Parkplatz geschoben wird. Wenn
ihr eine Nachricht aus Schritt 3 als `beispiel.json` gespeichert habt, könnt
ihr eure Funktionen direkt damit aufrufen:

```python
from pathlib import Path

from detection_worker.data import parse_event

event = parse_event(Path("beispiel.json").read_text())
dispatcher.dispatch(TOPIC, event)
```

Oder ihr schickt die Nachricht selbst an den Broker, als käme sie vom BMA:

```bash
mosquitto_pub -h <TODO: Hostname/IP des Pi> -t '<TODO: Topic>' \
  -f beispiel.json
```

## Hilfe, es geht nicht!

| Problem | Lösung |
| --- | --- |
| `uv: command not found` | Terminal neu öffnen, nachdem uv installiert wurde. |
| Keine Verbindung zum Broker | Seid ihr im richtigen WLAN? Stimmt der Hostname/die IP? Läuft `mosquitto_sub` (Schritt 3)? |
| Verbindung bricht ständig ab | Nutzt ein anderes Team dieselbe `client_id`? |
| Keine Events | Mit `mosquitto_sub -t '#' -v` prüfen, auf welchem Topic die Events wirklich ankommen. |
| Funktion wird nie aufgerufen | Stimmen Topic, Name und Event-Typ im `HandlerKey` mit den echten Nachrichten überein? Groß-/Kleinschreibung beachten. |
| Mehr Details sehen | `logging.basicConfig(level=logging.DEBUG)` statt `INFO` setzen. |

Und natürlich: **Fragt uns!** Wir sind den ganzen Hackathon über vor Ort.

## Für Fortgeschrittene

- **Tests:** `uv run pytest`
- **Code formatieren und prüfen:** `uv run ruff format .` und `uv run ruff check .`
- **Typen prüfen:** `uv run pyright`
- **Architektur:** [src/detection_worker/ARCHITECTURE.md](src/detection_worker/ARCHITECTURE.md)
  und [src/picture_pipeline/ARCHITECTURE.md](src/picture_pipeline/ARCHITECTURE.md)
- **Projektvorlage und Werkzeugwahl:** [doc/template.md](doc/template.md)

## Für Betreuer

BMA per LAN erreichen, Firewall-Freigaben und Kamerabild auf einen Test-PC
holen: [doc/bma-betreuer.md](doc/bma-betreuer.md).

## Links

- BERNARD-Dokumentation: <https://docs.bernard-gruppe.com/>
- Event-Schema 6.0: <https://docs.bernard-gruppe.com/events/schema/>
- MQTT kurz erklärt: <https://mqtt.org/>
- uv: <https://docs.astral.sh/uv/>
