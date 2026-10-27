# MQTT-Broker auf dem Hackathon-Raspberry-Pi

Stand: 27.10.2026

Mosquitto läuft als Docker-Container auf dem Raspberry Pi `hackathon.local`.
Über ihn laufen die LED-Befehle an [bmc-interface](../bmc-interface/README.md)
auf dem BMA. Ein Cloud-Broker wird nicht verwendet.

| Zugang | Adresse | Wer |
|---|---|---|
| WLAN | `hackathon.local:1883` (IP per DHCP, wechselt) | Teilnehmende, Laptops |
| LAN-Kabel zum BMA | `169.254.42.3:1883` (fest) | bmc-interface auf dem BMA |

- Kein TLS: Passwort und Nachrichten gehen im WLAN unverschlüsselt über die
  Luft. Für den Hackathon vertretbar; das Kabel zum BMA ist ohnehin direkt.
- Kein anonymer Zugriff: Jeder Client braucht Benutzer und Passwort.

## Einrichtung (bereits erledigt am 27.10.2026)

1. Docker aus Debian installieren, `pi` in die Gruppe `docker`:

```bash
sudo apt-get install -y docker.io docker-compose
```

```bash
sudo usermod -aG docker pi
```

2. Diesen Ordner auf den Pi kopieren (vom Laptop, Repository-Root):

```bash
scp -i ~/.ssh/id_rsa -o IdentitiesOnly=yes -r deploy/pi-broker \
pi@hackathon.local:
```

3. Auf dem Pi starten (leere Passwortdatei, damit Mosquitto startet):

```bash
cd ~/pi-broker && mkdir -p data log && install -m 600 /dev/null config/passwd \
&& docker compose up -d
```

`-o IdentitiesOnly=yes` ist nötig, wenn im SSH-Agent viele Schlüssel liegen:
der Pi trennt sonst nach zu vielen Fehlversuchen.

## Route für Events aus Containern des BMA

`curiosity` (die Events) läuft auf dem BMA in einem Docker-Netz. Der BMA
ersetzt dabei die Absenderadresse durch seine **LTE-Adresse** (Bereich
`100.64.0.0/10`), nicht durch die Kabel-Adresse: `169.254.x.x` ist
link-lokal und wird dafür übergangen. Ohne Route schickt der Pi seine Antwort
übers WLAN, und die Verbindung läuft in einen Timeout. Diese Route im Profil
von `eth0` schickt die Antworten übers Kabel zurück (eingerichtet am
27.10.2026; WLAN-Geräte sind nicht betroffen):

```bash
sudo nmcli con modify netplan-eth0 +ipv4.routes "100.64.0.0/10 169.254.42.1" \
&& sudo nmcli device reapply eth0
```

Prüfen (erwartet: `via 169.254.42.1 dev eth0`):

```bash
ip route get 100.70.112.6
```

Ist LTE am BMA kurz weg, kommen Events verspätet an: `curiosity` puffert sie
und schickt sie nach. `bmc-interface` (LEDs) läuft im Host-Netz des BMA und
ist davon nicht betroffen. Entfernen: dieselben Befehle mit `-ipv4.routes`.

## Benutzer verwalten

Benutzer anlegen oder Passwort ändern (fragt das Passwort interaktiv ab) und
den Broker neu laden:

```bash
ssh -t -i ~/.ssh/id_rsa -o IdentitiesOnly=yes pi@hackathon.local \
'docker exec -it mosquitto mosquitto_passwd /mosquitto/config/passwd hackathon && docker restart mosquitto'
```

Benutzer löschen:

```bash
ssh -t -i ~/.ssh/id_rsa -o IdentitiesOnly=yes pi@hackathon.local \
'docker exec mosquitto mosquitto_passwd -D /mosquitto/config/passwd <name> && docker restart mosquitto'
```

## Betrieb

| Aufgabe | Befehl auf dem Pi |
|---|---|
| Status | `docker ps --filter name=mosquitto` |
| Logs | `docker logs --tail 50 mosquitto` |
| Neustart | `docker restart mosquitto` |
| Stoppen | `cd ~/pi-broker && docker compose down` |

Der Container startet nach einem Neustart des Pi automatisch
(`restart: unless-stopped`).

Mitlesen vom Laptop (Paket `mosquitto-clients`):

```bash
mosquitto_sub -h hackathon.local -u hackathon -P '<passwort>' \
-t 'bmc_interface/tirol-hackathon/#' -v
```
