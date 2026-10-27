# LEDs am BMC per MQTT schalten (bmc-interface)

Stand: 27.10.2026

Diese Anleitung richtet [`bmc-interface`](https://github.com/bernard-technologies/bmc-interface)
auf dem BMA **G-A2610-0007** ein. Danach können die Teilnehmenden die LEDs an
den BMC-Kontakten **per MQTT** schalten, ohne Zugriff auf den BMA. Broker ist
der Mosquitto-Container auf dem Hackathon-Raspberry-Pi
([`deploy/pi-broker`](../pi-broker/README.md)); ein Cloud-Broker wird nicht
verwendet.

Der Quellcode von bmc-interface liegt als Git-Submodule unter
[`vendor/bmc-interface`](../../vendor/bmc-interface) (nach dem Klonen:
`git submodule update --init vendor/bmc-interface`). Daraus wird das Image
auf dem Raspberry Pi gebaut (arm64 wie der BMA) und per `docker save |
docker load` auf den BMA kopiert. Keine Container-Registry, keine
Azure-Zugangsdaten.

```text
Teilnehmende ──MQTT (WLAN)──▶ Raspberry Pi hackathon.local:1883 (Mosquitto)
                                   ▲
                                   │ LAN-Kabel, 169.254.42.3:1883
                                   │ bmc-interface verbindet sich selbst
                                   │ (ausgehend) und holt die Befehle ab
                       BMA G-A2610-0007: bmc-interface (Docker)
                                   │  /dev/ttyAMA2 (RS-485)
                                   ▼
                                  BMC ──▶ Kontakte 1–10 ──▶ LEDs
```

| Topic | Richtung | Inhalt |
|---|---|---|
| `bmc_interface/tirol-hackathon/out` | Teilnehmende → BMA | Schaltbefehle |
| `bmc_interface/tirol-hackathon/in` | BMA → alle | Status/Heartbeat von bmc-interface |
| `bmc_interface/tirol-hackathon/events` | BMA → alle | ein Event pro geschaltetem Kontakt |

## Wichtig vorab

- **Nur ein Programm darf den BMC steuern.** Normalerweise hält die
  Kamera-Software `curiosity` den Port `/dev/ttyAMA2`, solange im Control
  Center **„IO-device“** aktiv ist. Für den Hackathon wird „IO-device“
  abgeschaltet; damit entfallen auch alle BMC-Regeln der Kamera. Die
  Analytics laufen weiter.
- **Kontakte 11 und 12** benutzt bmc-interface selbst (Health-Check und
  Status). LEDs nur an **Kontakt 1–10** anschließen.
- **Elektrik:** Die Kontakte sind potentialfreie Optokoppler-Ausgänge, sie
  liefern keinen Strom. Jede LED braucht eine eigene Versorgung und einen
  Vorwiderstand; Spannung/Strom laut
  [BMC-Datenblatt](https://docs.bernard-gruppe.com/products/BMC/downloads/datasheet-bmc-de.pdf).
- **Zugangsdaten** (Broker-Passwort, Registry) gehören nie in dieses
  Repository. Die echte `shared/configuration.json` ist per `.gitignore`
  ausgeschlossen.
- **Kein TLS:** Der Pi-Broker spricht unverschlüsselt. Am Kabel zum BMA egal,
  im WLAN kann das Broker-Passwort mitgelesen werden.

## Dateien

| Datei | Zweck |
|---|---|
| `start.sh` | startet den Container mit `docker run` (der BMAv3 hat kein `docker compose`); `/dev/ttyAMA2` erscheint im Container als `/dev/ttyTHS2`, den bmc-interface fest erwartet |
| `shared/configuration.example.json` | Vorlage; Kopie als `shared/configuration.json` mit Broker-Passwort |
| `../../examples/bmc_mqtt_switch.py` | Sende-Beispiel für die Teilnehmenden |
| `../../tmp/run-me.sh` | Deploy-Skript (lokal, nicht im Repository) |

Abweichungen der Konfiguration von der bmc-interface-Vorlage:

| Wert | Hackathon | Grund |
|---|---|---|
| `host` / `port` / `use_tls` | `169.254.42.3` / `1883` / `false` | Pi-Broker über das LAN-Kabel |
| `hardware_simulated` | `false` | sonst wird nur simuliert |
| `max_message_within_spam_time` | `600` (pro 300 s) | Teams dürfen im Schnitt 2 Befehle/s senden, z. B. zum Blinken |
| `max_signal_delay_s` | `5` | Spielraum für ungenaue Laptop-Uhren |
| `alert_monitor_*` | leer | keine Alarm-Mails; ohne `ALERT_MONITOR_TOKEN` wird nichts gesendet |

## Einrichtung

Voraussetzungen: Der Pi-Broker läuft und hat einen Benutzer `hackathon`
(siehe [`deploy/pi-broker`](../pi-broker/README.md)); das LAN-Kabel steckt
zwischen BMA und Pi. Alle Befehle im Repository-Root ausführen. Die Schritte
3–8 sind zusätzlich als Skript `tmp/run-me.sh` vorhanden (bricht ab, wenn der
Port belegt ist).

1. Konfiguration anlegen und `<MQTT_PASSWORD>` ersetzen:

```bash
cp deploy/bmc-interface/shared/configuration.example.json \
deploy/bmc-interface/shared/configuration.json
```

2. Im Control Center beim BMA **G-A2610-0007** die Checkbox **„IO-device“**
   abwählen und **„Save“** klicken.

3. Prüfen, dass `/dev/ttyAMA2` frei ist (leere Ausgabe = frei):

```bash
ssh -t G-A2610-0007 'sudo fuser /dev/ttyAMA2'
```

4. Node-ID des BMA auslesen (wird als `target_uuid` gebraucht) und prüfen,
   ob Docker nutzbar und der Pi-Broker über das Kabel erreichbar
   ist:

```bash
ssh -t G-A2610-0007 \
'docker version --format "{{.Server.Version}}"; sudo python3 -c "import json; print(json.load(open(\"/opt/swarm/config/urban_traffic_config.json\"))[\"node\"][\"id\"])"; python3 -c "import socket; socket.create_connection((\"169.254.42.3\", 1883), 5); print(\"broker ok\")"'
```

5. Dateien kopieren:

```bash
ssh G-A2610-0007 'mkdir -p bmc-interface/shared'
```

```bash
scp deploy/bmc-interface/start.sh G-A2610-0007:bmc-interface/
```

```bash
scp deploy/bmc-interface/shared/configuration.json \
G-A2610-0007:bmc-interface/shared/
```

6. Das auf dem Pi gebaute Image zum BMA übertragen (siehe „Image bauen“).
   Der Datenstrom läuft Pi → Laptop → BMA, etwa 100 MB komprimiert:

```bash
ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes pi@hackathon.local \
'docker save bmc-interface:hackathon bmc-interface:4fc8393 | gzip -1' \
| ssh G-A2610-0007 'gunzip | docker load'
```

7. Prüfen, ob ein Container den Pi-Broker erreicht (Wegwerf-Container,
   danach gelöscht). bmc-interface läuft mit `--network host`: Aus dem
   normalen Docker-Netz heraus läuft die Verbindung zum Pi in einen Timeout,
   weil der BMA weitergeleiteten Verkehr nicht durchlässt; der BMA selbst
   erreicht den Pi. bmc-interface braucht keine eingehenden Ports:

```bash
ssh -t G-A2610-0007 \
'docker run --rm --network host --entrypoint python3 bmc-interface:hackathon -c "import socket; socket.create_connection((\"169.254.42.3\", 1883), 5); print(\"container ok\")"'
```

8. Starten und Logs ansehen (Ctrl+C beendet nur die Anzeige):

```bash
ssh -t G-A2610-0007 \
'sh bmc-interface/start.sh && docker logs -f --tail 50 bmc-interface'
```

## Image bauen (auf dem Pi)

Zuletzt gebaut am 27.10.2026 aus Commit `4fc8393` (295 MB, arm64). Neu bauen,
wenn das Submodule `vendor/bmc-interface` aktualisiert wurde; das Tag dann
auf den neuen Commit setzen (auch in `tmp/run-me.sh`).

1. Quellcode auf den Pi kopieren (ohne `.git` und Caches):

```bash
tar -C vendor/bmc-interface --exclude=.git --exclude=__pycache__ \
--exclude=.venv -czf - . \
| ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes pi@hackathon.local \
'rm -rf ~/bmc-interface-src && mkdir ~/bmc-interface-src && tar -C ~/bmc-interface-src -xzf -'
```

2. Bauen, mit Commit-Tag und dem Tag `hackathon`, auf das
   `start.sh` verweist:

```bash
ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes pi@hackathon.local \
'cd ~/bmc-interface-src && docker build -t bmc-interface:4fc8393 -t bmc-interface:hackathon .'
```

3. Kurztest ohne Netzwerk (Importe und C-Bibliothek):

```bash
ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes pi@hackathon.local \
'docker run --rm --network none --entrypoint uv bmc-interface:hackathon run --frozen python -c "import src.subscriber, ctypes; ctypes.CDLL(\"/app/libbmcserial/build/liblibbmcserial.so\"); print(\"ok\")"'
```

## Befehlsformat

Node-ID von G-A2610-0007 (`target_uuid`):
`f6b51cd4-4469-4138-831a-b5cc471f9e45` (ausgelesen am 27.10.2026).

```json
{
  "command_id": "eindeutige-id",
  "target_uuid": "<Node-ID des BMA>",
  "source_uuid": "team-1",
  "command": "ENABLE",
  "timestamp": "2026-10-27T11:30:00+00:00",
  "contacts": [
    {"id": "3", "type": "permanent", "state": "ON"},
    {"id": "4", "type": "normal", "state": "ON", "duration": 2.0}
  ]
}
```

| `type` | Verhalten |
|---|---|
| `permanent` | Kontakt bleibt `ON`/`OFF`, bis ein neuer Befehl kommt |
| `normal` | Kontakt geht `ON` und nach `duration` Sekunden (Standard 1 s) wieder aus |

bmc-interface verwirft einen Befehl, wenn …

- `target_uuid` nicht die Node-ID des BMA ist,
- `timestamp` älter als 5 s ist; immer **UTC mit `+00:00`** schreiben, **nicht
  `Z`** (Python 3.10 im Container versteht `Z` nicht),
- eine Kontakt-`id` außerhalb 0–10 liegt oder `duration` bei `permanent`
  angegeben ist,
- der Absender (`source_uuid`) mehr als 600 Befehle in 300 s geschickt hat.
  Er bleibt dann gesperrt, bis die Rate sinkt oder er einen Befehl mit
  `"command": "RESET"` schickt.

## LEDs schalten (Funktionstest)

Die vollständige Beschreibung für die Schüler steht in
[`doc/leds-per-mqtt.md`](../../doc/leds-per-mqtt.md). Kurztest mit dem
Beispielskript (BMA-ID ist eingebaut, Broker `hackathon.local:1883`):

```bash
read -rs MQTT_PASSWORD && export MQTT_USER=hackathon MQTT_PASSWORD
```

```bash
uv run python examples/bmc_mqtt_switch.py --team betreuer --contact 3 --on --duration 2
```

Rückmeldungen von bmc-interface mitlesen:

```bash
mosquitto_sub -h hackathon.local -p 1883 \
-u "$MQTT_USER" -P "$MQTT_PASSWORD" \
-t 'bmc_interface/tirol-hackathon/#' -v
```

## Betrieb

| Aufgabe | Befehl auf dem BMA (`ssh -t G-A2610-0007 '…'`) |
|---|---|
| Status | `docker ps --filter name=bmc-interface` |
| Logs | `docker logs --tail 100 bmc-interface` |
| Konfiguration ändern | Datei neu kopieren; bmc-interface lädt sie alle 600 s neu, sofort mit `docker restart bmc-interface` |
| Stoppen | `docker rm -f bmc-interface` |
| Neu starten (z. B. neues Image) | `sh bmc-interface/start.sh` |

Der Container startet nach einem Neustart des BMA automatisch wieder
(`restart: unless-stopped`).

**Zurück zum Normalbetrieb – Reihenfolge einhalten:**

1. bmc-interface stoppen (`docker rm -f bmc-interface`, siehe oben).
2. Prüfen, dass `/dev/ttyAMA2` frei ist (`sudo fuser /dev/ttyAMA2`).
3. Erst dann im Control Center „IO-device“ wieder aktivieren.

Laufen beide gleichzeitig, senden zwei Programme auf demselben
Halbduplex-Bus; Befehle werden verstümmelt und Ausgänge falsch geschaltet.

## Fehlersuche

| Symptom | Ursache / Prüfung |
|---|---|
| Log: `does not match this device UUID` | falsche `target_uuid`; Node-ID aus Schritt 4 verwenden |
| Log: `is too old` | Uhr des Senders falsch oder `timestamp` nicht in UTC |
| Log: `Invalid isoformat string` | `timestamp` mit `Z` statt `+00:00` |
| Log: `is in disabled sources list` | Spam-Sperre; `"command": "RESET"` senden |
| Container startet neu, Fehler beim Öffnen des Ports | `curiosity` hält `/dev/ttyAMA2` noch – „IO-device“ aus? |
| Keine Verbindung zum Broker | LAN-Kabel? Schritt 4 und 7; Broker-Container auf dem Pi läuft? Passwort korrekt? |
| Schritt 7: `TimeoutError` | Container nicht im Host-Netz gestartet – `--network host` fehlt |
| `Permission denied` auf `urban_traffic_config.json` | Datei ist nur für root lesbar: mit `sudo` lesen (der Container läuft als root) |
| Beispielskript: `Broker refused connection: Not authorized` | Benutzer/Passwort falsch oder Benutzer auf dem Pi nicht angelegt |
| Kontakt 11/12 schaltet von selbst | gewollt: Health-Check und Status von bmc-interface |

## Nach dem Hackathon: alles zurückbauen

Reihenfolge einhalten: erst bmc-interface entfernen und prüfen, dass der
BMC-Port frei ist, dann `curiosity` den BMC zurückgeben. Die Befehle 1–3
löschen bzw. ändern etwas auf dem BMA.

1. Container entfernen. Er startet danach auch nach einem Neustart nicht mehr,
   und `/dev/ttyAMA2` wird frei:

```bash
ssh G-A2610-0007 'docker rm -f bmc-interface'
```

2. Images, Ordner (enthält das Broker-Passwort) und Testreste löschen:

```bash
ssh G-A2610-0007 \
'docker image rm bmc-interface:hackathon bmc-interface:4fc8393; rm -rf ~/bmc-interface /tmp/bmc_serial /tmp/bmc_led_server.py /tmp/liblibbmcserial.so*'
```

3. SSH-Freigabe für das LAN entfernen (entfällt nach einem Neustart des BMA
   ohnehin; meldet „Bad rule“, wenn sie schon weg ist):

```bash
ssh -t G-A2610-0007 \
'sudo iptables -D INPUT -i eth0 -s 169.254.0.0/16 -p tcp --dport 22 -m conntrack --ctstate NEW -j ACCEPT'
```

4. Prüfen, dass nichts übrig ist und der Port frei ist (nur lesend; leere
   Ausgabe nach `fuser` = frei):

```bash
ssh -t G-A2610-0007 \
'docker ps -a --filter name=bmc-interface; docker image ls bmc-interface; ls -d ~/bmc-interface 2>/dev/null; sudo fuser /dev/ttyAMA2'
```

5. Erst jetzt im Control Center beim BMA **„IO-device“** wieder aktivieren
   und **„Save“** klicken.

6. Prüfen, dass `curiosity` den Port wieder hält (erwartet: eine PID, deren
   Programm `./curiosity` ist):

```bash
ssh -t G-A2610-0007 \
'for p in $(sudo fuser /dev/ttyAMA2 2>/dev/null); do echo "$p $(tr "\0" " " < /proc/$p/cmdline)"; done'
```

Optional auf dem Raspberry Pi (kein BERNARD-Gerät):

| Was | Befehl auf dem Pi |
|---|---|
| Broker stoppen und entfernen | `cd ~/pi-broker && docker compose down && cd && rm -rf ~/pi-broker` |
| Image-Quellen und Images | `rm -rf ~/bmc-interface-src && docker image rm bmc-interface:hackathon bmc-interface:4fc8393 eclipse-mosquitto:2.0.21` |
| `eth0` wieder auf DHCP (entfernt auch die LTE-Route) | `sudo nmcli con modify netplan-eth0 ipv4.method auto ipv4.addresses "" ipv4.routes "" ipv4.never-default no ipv6.method auto` |
| `pi` aus der Gruppe `docker` | `sudo gpasswd -d pi docker` |
