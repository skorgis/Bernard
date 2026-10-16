# BMA-Anleitung für Betreuer

Stand: 16.10.2026

Diese Anleitung ist für das **Betreuer-Team**, nicht für die Teilnehmenden.
Sie beschreibt, wie ihr den BMAv3 **G-A2610-0007** per LAN-Kabel erreicht und
sein Kamerabild auf einen Test-PC holt. Die Teilnehmenden arbeiten nur mit den
MQTT-Events (siehe [README](../README.md)) und greifen nie direkt auf den BMA
zu.

> **Hinweis:** Diese Datei liegt im selben Repository, das die Teilnehmenden
> klonen. Gerätepasswörter und andere Zugangsdaten gehören deshalb nie hier
> hinein.

Code, Build und Upload von `camera_stream` liegen im Repository
**camera_stream**; die ausführliche technische Anleitung dort ist
`docs/hackathon.md`. Befehle mit `deploy.sh` oder `tools/bma_connect.sh`
laufen im Ordner dieses Repositorys.

## Überblick

Der Test-PC holt das Kamerabild des BMA direkt per LAN-Kabel unter
`http://169.254.42.1:8080/stream.ts`, ohne VPN und ohne LTE-Volumen.
Getestet am 15.10.2026: Ping über LAN mit 0 % Verlust und unter 1 ms.

Der Weg des Bildes:

1. **csicamera** (Docker-Container auf dem BMA) liefert das H.264-Video der
   CSI-Kamera per ZMQ.
2. **camera_stream** (ein einzelnes Binary) verpackt es ohne Neukodierung in
   MPEG-TS und stellt es per HTTP bereit.
3. **Test-PC** spielt es mit ffplay, VLC oder OpenCV ab.

Video: 1280×720, 30 fps, ca. 4 Mbit/s. Ein neuer Client wartet bis zu 2 s auf
das erste Bild (nächster Keyframe).

Unabhängig davon verschickt der BMA seine Erkennungen als MQTT-Events an den
Broker auf dem Raspberry Pi (siehe „Der Aufbau“ im [README](../README.md)).
Dafür braucht es weder das LAN-Kabel noch camera_stream.

## Voraussetzungen

Auf dem Arbeitsrechner, einmalig vor dem Hackathon:

- [ ] Repository `camera_stream` ausgecheckt (enthält `deploy.sh` und
      `tools/bma_connect.sh`)
- [ ] Für Build und Upload: Rust über rustup, plus Ziel für den BMA:
      `rustup target add aarch64-unknown-linux-musl`
- [ ] Azure CLI angemeldet: `az login` (Zugriff auf den Jump-Host
      `bernard-openvpn`)
- [ ] `sshpass` installiert: `sudo apt install sshpass`
- [ ] Gerätepasswort für User `bernard` zur Hand (nicht in dieses Repository)
- [ ] Player: `ffplay` (Paket `ffmpeg`) oder VLC
- [ ] USB-LAN-Adapter und Netzwerkkabel

VPN und Jump-Host braucht ihr nur zum Hochladen und für ssh. Den Stream selbst
holt der Test-PC direkt übers Kabel.

## Gerät und Adressen

Der BMA heißt im Prompt `G-A2610-0007:~$`. Steht dort etwas anderes (z. B.
`G-A2604-0075`), seid ihr auf dem falschen Gerät: sofort abbrechen.

| Schnittstelle | Adresse | Wozu |
| --- | --- | --- |
| `eth0` (LAN) am BMA | `169.254.42.1/16`, fest im Image | Stream und ssh direkt vom Test-PC |
| USB-LAN-Adapter am Test-PC | `169.254.42.2/16` | Gegenstelle zum BMA |
| `tun0` (VPN) am BMA | wechselt, z. B. `10.33.19.214` | ssh und Upload über den Jump-Host |
| `wwan0` (LTE) am BMA | Carrier-NAT, `100.71.x.x` | Internet und VPN; von außen nicht erreichbar |

WLAN gibt es nicht: Das Image hat weder WLAN-Treiber, Firmware noch
`wpa_supplicant`.

Die LAN-Verbindung hat keine Default-Route. Internet und VPN laufen deshalb
weiter über LTE, auch wenn das Kabel steckt.

### Firewall auf dem BMA

Der BMA nutzt iptables (`nft` ist nicht installiert); die INPUT-Policy ist
`DROP`. Gesperrte Ports antworten deshalb nicht mit „refused“, die Verbindung
läuft in einen Timeout. Auslesen (nur lesend):

```bash
sudo iptables -S INPUT
```

Was standardmäßig erlaubt ist (Stand 16.10.2026):

| Schnittstelle | Erlaubt |
| --- | --- |
| `tun+` / `tun0` (VPN) | ssh (22), HTTP (80) |
| `eth0` (LAN) | nur HTTP (80) = Admin-Seite, mDNS (UDP 5353), IGMP |
| `br-+` (Docker-Netze) | TCP 10092, nur für Container |
| alle | Ping (ICMP) |

Über LAN sind also **ssh (22) und camera_stream (8080) gesperrt**, bis sie
freigegeben werden (Schritt 2). sshd selbst lauscht auf allen Adressen
(`0.0.0.0:22`); die Sperre kommt nur von der Firewall.

Freigaben aus Schritt 2.7 bleiben bis zum Neustart aktiv. Steht in
`iptables -S INPUT` schon eine `eth0`-Regel für 22 oder 8080, stammt sie von
einer früheren Sitzung; nicht doppelt anlegen.

### Admin-Seite

Unter `http://169.254.42.1/` (Port 80) läuft die Admin-Oberfläche des BMA
(Login `admin`). Unter „Networking“ lässt sich die IP von `eth0` einstellen
(DHCP oder fest).

- Für die Direktverbindung zum Test-PC dort nichts ändern: Die IP ist nicht
  das Problem, sondern die Firewall.
- Sinnvoll nur, wenn der BMA in ein bestehendes Netz soll (z. B. Schul-LAN
  ohne DHCP).
- Gateway leer lassen: Mit Gateway bekommt `eth0` die Default-Route, und
  VPN/LTE kann abreißen.
- „Apply“ ändert die Netzwerkkonfiguration sofort.
- Der Punkt „Live Video“ zeigt evtl. das Kamerabild über Port 80 (noch nicht
  geprüft).

## Schritt 1: Bauen und hochladen

Nur nötig, wenn sich der Code geändert hat oder das Binary noch nicht auf dem
BMA liegt. Im Ordner des Repositorys `camera_stream`:

```bash
cargo bma
```

```bash
./deploy.sh
```

`deploy.sh` fragt einmal nach dem Passwort für `bernard`, sucht die aktuelle
VPN-IP über die Seriennummer und legt das Binary unter
`~/camera_stream/camera_stream` ab. Erfolg: `==> [G-A2610-0007] OK`. Ein
laufender camera_stream wird dabei nicht neu gestartet. Details und Upload
über LAN: `docs/hackathon.md` im Repository camera_stream.

## Schritt 2: LAN-Verbindung PC ↔ BMA

Der BMA hat auf `eth0` fest `169.254.42.1`. Der Test-PC braucht eine Adresse
im selben Bereich, und die Firewall des BMA muss Port 22 und 8080 auf `eth0`
freigeben.

1. Kabel vom USB-LAN-Adapter des PCs direkt in den LAN-Port des BMA stecken.
2. Namen des LAN-Adapters am PC herausfinden (bisher `enx0050b6f802ad`, er
   beginnt meist mit `enx` oder `enp`):

```bash
ip -br link
```

3. Adresse setzen. Am Arbeitsrechner gibt es dafür ein NetworkManager-Profil
   (fest `169.254.42.2/16`, kein Gateway, kein DHCP). Es verbindet sich
   absichtlich nicht automatisch (`autoconnect no`), damit der Adapter an
   einer normalen Netzwerkdose nicht mit dieser Adresse hängen bleibt. WLAN
   und andere Verbindungen bleiben unberührt:

```bash
nmcli connection up enx0050b6f802ad
```

Ohne dieses Profil (anderer PC) die Adresse von Hand setzen. Sie gilt nur bis
zum Neustart oder Abziehen des Adapters, und NetworkManager kann sie
zwischendurch entfernen; dann den Befehl wiederholen:

```bash
sudo ip addr add 169.254.42.2/16 dev enx0050b6f802ad
```

4. Verbindung testen. Erwartet: Antworten unter 1 ms, 0 % Verlust:

```bash
ping -c 3 169.254.42.1
```

5. Per **VPN** auf den BMA verbinden (ssh über LAN ist noch gesperrt), im
   Ordner des Repositorys camera_stream:

```bash
bash -c 'source tools/bma_connect.sh && bma_connect_init \
&& ip=$(bma_lookup_ip G-A2610-0007) \
&& "${SSH_CMD[@]}" -o HostKeyAlias=G-A2610-0007 "$SSH_USER@$ip"'
```

6. Auf dem BMA prüfen, dass sshd auf allen Adressen lauscht; erwartet:
   `listenaddress 0.0.0.0:22`:

```bash
sudo sshd -T | grep -i listenaddress
```

7. Auf dem BMA Port 22 und 8080 auf `eth0` freigeben, nur für direkt
   angeschlossene Geräte (`169.254.0.0/16`). Ändert die Firewall bis zum
   nächsten Neustart; VPN, LTE und alle anderen Regeln bleiben unverändert:

```bash
sudo iptables -A INPUT -i eth0 -s 169.254.0.0/16 -p tcp \
-m multiport --dports 22,8080 -m conntrack --ctstate NEW -j ACCEPT
```

Nur 8080 (Stream ohne ssh über LAN):

```bash
sudo iptables -A INPUT -i eth0 -s 169.254.0.0/16 -p tcp --dport 8080 \
-m conntrack --ctstate NEW -j ACCEPT
```

> **Sicherheit:** Im Schulnetz Port 22 nicht freigeben. Die Einschränkung auf
> `169.254.0.0/16` lässt nur direkt per Kabel angeschlossene Geräte zu, keine
> Geräte mit DHCP-Adresse aus einem Netz.

8. Vom PC aus prüfen, ob die Ports jetzt offen sind (`exit=0` = offen,
   `exit=124` = gesperrt):

```bash
for p in 22 8080; do timeout 5 bash -c "</dev/tcp/169.254.42.1/$p" \
2>/dev/null; echo "port $p exit=$?"; done
```

9. Per ssh über LAN auf den BMA, ganz ohne VPN:

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no \
-o HostKeyAlias=G-A2610-0007 bernard@169.254.42.1
```

Ist der Prompt `G-A2610-0007:~$`, seid ihr richtig.

### Optional: Kurznamen in `~/.ssh/config`

Damit reichen `ssh G-A2610-0007` (VPN) und `ssh G-A2610-0007-lan` (Kabel).
Beide prüfen den Host-Key unter der Seriennummer; hängt am Kabel ein anderer
BMA mit derselben `169.254.42.1`, bricht ssh ab. `PubkeyAuthentication no`
verhindert „Too many authentication failures“, wenn in `~/.ssh` viele Keys
liegen.

```
Host G-A2610-0007
    User bernard
    HostName 10.33.19.214
    HostKeyAlias G-A2610-0007
    PreferredAuthentications password
    PubkeyAuthentication no
    ProxyCommand az ssh vm -n bernard-openvpn -g BERNARD -- -W %h:%p

Host G-A2610-0007-lan
    User bernard
    HostName 169.254.42.1
    HostKeyAlias G-A2610-0007
    PreferredAuthentications password
    PubkeyAuthentication no
```

Die VPN-IP im `HostName` wechselt bei jedem Reconnect des BMA. Aktuelle IP
nachschlagen und eintragen:

```bash
az ssh vm -n bernard-openvpn -g BERNARD -- \
cat /etc/openvpn/inst1_status.txt | grep G-A2610-0007
```

## Schritt 3: Stream starten und abrufen

**Auf dem BMA** (in der ssh-Sitzung aus Schritt 2) camera_stream nur auf der
LAN-Adresse starten:

```bash
~/camera_stream/camera_stream --listen 169.254.42.1:8080
```

Es läuft im Vordergrund und zeigt seine Logs. `Strg+C` oder das Schließen der
ssh-Sitzung beendet es. Über VPN und LTE ist es so nicht erreichbar.

**Auf dem Test-PC** den Stream abrufen, mit einem der drei Wege:

ffplay, mit geringer Verzögerung:

```bash
ffplay -fflags nobuffer -flags low_delay http://169.254.42.1:8080/stream.ts
```

VLC: Medien → Netzwerkstream öffnen → `http://169.254.42.1:8080/stream.ts`

OpenCV (Python):

```python
import cv2

cap = cv2.VideoCapture(
    "http://169.254.42.1:8080/stream.ts",
    cv2.CAP_FFMPEG,
    [cv2.CAP_PROP_N_THREADS, 1],
)
while True:
    ok, frame = cap.read()
    if not ok:
        break
    cv2.imshow("BMA", frame)
    if cv2.waitKey(1) == ord("q"):
        break
```

`CAP_PROP_N_THREADS = 1` ist wichtig: Mit vielen Decoder-Threads hält FFmpeg
pro Thread ein Bild zurück. Gemessen wurden ~500 ms statt ~70 ms Verzögerung.

Mehrere Clients gleichzeitig sind möglich. Solange mindestens einer zuschaut,
läuft der Encoder von csicamera.

### Alternative ohne LAN: Tunnel über VPN

Wenn das LAN nicht geht, holt ein ssh-Tunnel (`-L`) den Stream über VPN und
LTE auf den PC. Kostet ca. 1,8 GB LTE-Volumen pro Stunde Zuschauen.

Auf dem BMA (VPN-Sitzung):

```bash
~/camera_stream/camera_stream --listen 127.0.0.1:8080
```

Auf dem PC, zweites Terminal, im Ordner des Repositorys camera_stream (öffnet
nur den Tunnel, keine Shell):

```bash
bash -c 'source tools/bma_connect.sh && bma_connect_init \
&& ip=$(bma_lookup_ip G-A2610-0007) \
&& "${SSH_CMD[@]}" -o HostKeyAlias=G-A2610-0007 \
-N -L 18080:127.0.0.1:8080 "$SSH_USER@$ip"'
```

Auf dem PC, drittes Terminal:

```bash
ffplay -fflags nobuffer -flags low_delay http://127.0.0.1:18080/stream.ts
```

## Stoppen und aufräumen

1. camera_stream beenden: `Strg+C` in der ssh-Sitzung, oder von einer anderen
   Sitzung aus:

```bash
pkill -x camera_stream
```

2. Prüfen, dass nichts mehr läuft:

```bash
pgrep -a camera_stream || echo stopped
```

3. Auf dem BMA die Firewall-Freigabe entfernen (oder den BMA neu starten).
   Die Angaben müssen exakt der gesetzten Regel entsprechen:

```bash
sudo iptables -D INPUT -i eth0 -s 169.254.0.0/16 -p tcp \
-m multiport --dports 22,8080 -m conntrack --ctstate NEW -j ACCEPT
```

4. Am Test-PC die LAN-Adresse wieder entfernen (oder einfach den Adapter
   abziehen). Mit Profil aus Schritt 2.3:

```bash
nmcli connection down enx0050b6f802ad
```

Von Hand gesetzte Adresse:

```bash
sudo ip addr del 169.254.42.2/16 dev enx0050b6f802ad
```

Auf dem BMA bleibt danach nur die Datei `~/camera_stream/camera_stream`
liegen. csicamera, die Verkehrsanalyse und die Netzwerkkonfiguration wurden
nicht verändert; die Firewall-Regel verschwindet spätestens beim Neustart.

## Fehlersuche

Die häufigste Ursache ist das falsche Gerät: Immer zuerst den Prompt prüfen.

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| Prompt zeigt nicht `G-A2610-0007` | Mit einem anderen BMA verbunden | Abmelden, neu verbinden; dort nichts ausführen |
| `ping 169.254.42.1` ohne Antwort oder „Keine Route zum Zielrechner“ | PC hat keine Adresse im Bereich `169.254.x.x` | Schritt 2.3 wiederholen, mit `ip -br addr` prüfen |
| Ping geht, ssh oder Stream über LAN laufen in Timeout | Firewall des BMA lässt auf `eth0` nur Port 80 durch | Schritt 2.7 (iptables-Freigabe) |
| `ping` ohne Antwort, PC-Adresse stimmt | Kein Link, Kabel am falschen Gerät | Auf dem BMA: `cat /sys/class/net/eth0/carrier` muss `1` sein |
| `nmcli` zeigt bei `eth0` „getting IP configuration“ | BMA sucht per DHCP, am PC gibt es keinen DHCP-Server | Harmlos, die feste `169.254.42.1` gilt trotzdem |
| camera_stream meldet „Permission denied“ für `/run/camera/zmq_lowres.ipc` | User `bernard` darf den Socket von csicamera nicht lesen | Ausgabe sichern; noch ungetestet, Lösung offen |
| Port 8080 offen, Stream lädt nicht | camera_stream läuft nicht oder lauscht auf einer anderen Adresse | `pgrep -a camera_stream` prüfen, Logs in der ssh-Sitzung lesen |
| Port 80 antwortet, ist aber nicht der Stream | Dort läuft die Admin-Seite des BMA | Port 80 nicht für camera_stream verwenden |
| Bild kommt erst nach ~2 s | Client wartet auf den nächsten Keyframe | Normal |
| Bild hinkt deutlich hinterher | Player puffert | ffplay mit `-fflags nobuffer`, OpenCV mit 1 Thread |
| `deploy.sh`: „not connected to the VPN“ | BMA gerade nicht im VPN | Später erneut, oder Upload über LAN (siehe camera_stream) |
| ssh: „Too many authentication failures“ | ssh bietet erst alle Keys aus `~/.ssh` an, der BMA trennt vor der Passwortabfrage | `-o PubkeyAuthentication=no` oder ssh-config-Eintrag (Schritt 2) |
| `ssh G-A2610-0007` läuft in Timeout, `deploy.sh` geht | VPN-IP hat sich geändert, `HostName` in `~/.ssh/config` ist veraltet | Neue IP nachschlagen und eintragen (Schritt 2, ssh-config) |

## Begriffe

| Begriff | Kurz erklärt |
| --- | --- |
| DHCP | Dienst, meist im Router, der Geräten automatisch IP, Gateway und DNS zuteilt. Bei der Direktverbindung PC ↔ BMA gibt es keinen, daher feste Adressen. |
| Statische IP | Von Hand gesetzte Adresse statt DHCP, hier `169.254.42.1` (BMA) und `169.254.42.2` (PC). |
| Link-Local (`169.254.0.0/16`) | Adressbereich, der nur direkt auf einem Kabel oder Switch funktioniert, ohne Router. |
| Default-Route | Weg für alles außerhalb der bekannten Netze, also ins Internet. Beim BMA über LTE (`wwan0`). |
| Carrier-NAT (`100.64.0.0/10`) | Adressbereich der Mobilfunkanbieter. Das Gerät kommt raus ins Internet, ist von außen aber nicht erreichbar. |
| VPN / Jump-Host | Der BMA hängt per OpenVPN an `bernard-openvpn` in Azure. ssh läuft darüber, die VPN-IP wechselt bei jedem Reconnect. |
| `HostKeyAlias` | ssh merkt sich den Host-Key unter der Seriennummer statt der IP. Neue IP: keine Warnung. Anderes Gerät: Abbruch. |
| SSH-Tunnel `-L` / `-R` | `-L` holt einen Port des Geräts auf den eigenen Rechner. `-R` stellt einen eigenen Port auf einem entfernten Server bereit, aufgebaut von innen nach außen. |
| MPEG-TS | Containerformat für Live-Video mit Zeitstempeln; Player können jederzeit einsteigen. |
| Keyframe (IDR) | Vollständiges Bild, ab dem ein Decoder starten kann. csicamera sendet alle 60 Bilder (2 s) eins. |

## Ausblick: Kamerabild für Teilnehmende

Teilnehmende sollen nie direkt auf den BMA, sondern nur über einen Server mit
Token. Geplant, noch nicht umgesetzt:

1. Der BMA baut über LTE einen ausgehenden SSH-Reverse-Tunnel zum Server auf
   (`ssh -N -R 8080:127.0.0.1:8080`), authentifiziert per SSH-Key.
2. camera_stream lauscht nur auf `127.0.0.1:8080`, ist also nur durch den
   Tunnel erreichbar.
3. Auf dem Server verteilt ein Relay (z. B. MediaMTX) den Stream und prüft
   einen Token pro Zugang, verschlüsselt per TLS.

Offene Punkte:

- [ ] Hat der BMA einen ssh-Client? Prüfen mit
      `command -v ssh dbclient; ssh -V`
- [ ] Server: welcher, mit Domainname für ein TLS-Zertifikat?
- [ ] Ein Token für alle oder einer pro Team?
- [ ] Zugriff per OpenCV, Browser oder beides? Mit OpenCV ließe sich das
      BMA-Bild statt der Webcam für den Bonus (Symbolerkennung mit
      `picture_pipeline`) nutzen.

LTE-Volumen beachten: 4 Mbit/s sind ca. 1,8 GB pro Stunde. Das Relay sollte
nur bei Bedarf vom Gerät ziehen (MediaMTX: `sourceOnDemand`).
