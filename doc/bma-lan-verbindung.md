# BMA per LAN-Kabel verbinden (Schnellstart)

Stand: 02.11.2026

Kurzanleitung, um vom Laptop per LAN-Kabel eine ssh-Sitzung auf den BMAv3
**G-A2610-0007** zu öffnen. Hintergründe (Firewall, VPN, Admin-Seite,
Kamerastream) stehen ausführlich in [bma-betreuer.md](bma-betreuer.md).

Nur für Betreuer. Passwörter gehören nicht in dieses Repository.

## Überblick

| Gerät | Schnittstelle | Adresse |
| --- | --- | --- |
| BMA | `eth0` | `169.254.42.1/16`, fest im Image |
| Laptop | USB-LAN-Adapter `enx0050b6f802ad` (ASIX AX88772B) | `169.254.42.2/16` |

- Kein DHCP, kein Router: Beide Seiten haben feste Link-Local-Adressen.
- Das Profil am Laptop setzt kein Gateway. WLAN und Internet laufen also
  unverändert weiter.
- Die Firewall des BMA lässt auf `eth0` standardmäßig nur Ping und Port 80
  (Admin-Seite) durch. **ssh (22) muss einmal pro Neustart des BMA über VPN
  freigegeben werden** (Schritt 4).

## Schritt 1: Kabel stecken, Adapter prüfen

Kabel vom USB-LAN-Adapter direkt in den LAN-Port des BMA stecken. Dann
prüfen, ob der Laptop den Adapter als Netzwerkschnittstelle sieht:

```bash
ip -br link
```

Erwartet: eine Zeile `enx0050b6f802ad`. Fehlt sie, siehe
[Fehlersuche](#fehlersuche) („Adapter fehlt in `ip -br link`“).

## Schritt 2: Adresse am Laptop setzen

Das NetworkManager-Profil `enx0050b6f802ad` setzt fest `169.254.42.2/16`.
Es verbindet sich absichtlich nicht automatisch, damit der Adapter an einer
normalen Netzwerkdose nicht mit dieser Adresse hängen bleibt:

```bash
nmcli connection up enx0050b6f802ad
```

Prüfen:

```bash
ip -br addr show enx0050b6f802ad
```

Erwartet: `UP` und `169.254.42.2/16`.

## Schritt 3: Verbindung testen

```bash
ping -c 3 169.254.42.1
```

Erwartet: Antworten unter 1 ms, 0 % Verlust.

### Web-Portal (Admin-Seite)

Offiziell heißt sie „Service Interface“ (Betriebsanleitung BMA-V3, Abschnitt
7.2:
<https://docs.bernard-gruppe.com/products/BMA-V3/manual_assets/BMA-V3_operating-instructions_en.pdf>).
Ohne ssh und ohne Firewall-Freigabe erreichbar, denn Port 80 ist auf `eth0`
standardmäßig offen.

Laut Anleitung braucht die Schnittstelle unter Linux die IPv4-Methode
„Link-Local only“. Dafür gibt es am Laptop das Profil `bma-link-local`; es
wählt selbst eine freie Adresse aus `169.254.0.0/16`. Statt Schritt 2 geht
also auch:

```bash
nmcli connection up bma-link-local
```

Im Browser (die Anleitung nennt Chrome) öffnen:

```text
http://bma.local
```

Löst `bma.local` nicht auf (kein mDNS, z. B. weil die Laptop-Firewall
eingehende mDNS-Antworten blockt), die feste Adresse nehmen:

```text
http://169.254.42.1
```

Login: Benutzer `admin`. Das Startpasswort ist der erste Teil der Geräte-ID
bis zum ersten `-` (Geräte-ID steht im Control Center); es sollte beim ersten
Login geändert werden. Das aktuelle Passwort steht nicht in diesem
Repository.

Unter „Network“ nichts ändern, solange der BMA nur direkt am Laptop hängt;
„Apply“ ändert die Netzwerkkonfiguration sofort. Details:
[bma-betreuer.md, „Admin-Seite“](bma-betreuer.md#admin-seite).

### ssh-Port prüfen

Wer ssh braucht, prüft danach, ob ssh über LAN
schon freigegeben ist (`exit=0` = offen, `exit=124` = von der Firewall
gesperrt):

```bash
timeout 5 bash -c '</dev/tcp/169.254.42.1/22' 2>/dev/null; echo "exit=$?"
```

Bei `exit=0` direkt weiter mit Schritt 5.

## Schritt 4: ssh auf `eth0` freigeben (nur nach Neustart des BMA)

Die Freigabe geht nur über eine bestehende Sitzung, also per VPN. Ablauf
ausführlich in [bma-betreuer.md, Schritt 2.5 bis 2.7](bma-betreuer.md#schritt-2-lan-verbindung-pc--bma).
Kurzfassung:

1. Per VPN auf den BMA (Alias aus `~/.ssh/config`; ist die VPN-IP veraltet,
   siehe Fehlersuche):

```bash
ssh G-A2610-0007
```

2. Prompt prüfen: Er muss `G-A2610-0007:~$` lauten. Dann auf dem BMA Port 22
   (und 8080 für den Kamerastream) auf `eth0` freigeben, nur für direkt
   angeschlossene Geräte. **Ändert die Firewall des BMA** bis zum nächsten
   Neustart; andere Regeln, VPN und LTE bleiben unverändert:

```bash
sudo iptables -A INPUT -i eth0 -s 169.254.0.0/16 -p tcp \
-m multiport --dports 22,8080 -m conntrack --ctstate NEW -j ACCEPT
```

3. VPN-Sitzung mit `exit` beenden und den Port-Test aus Schritt 3
   wiederholen.

Steht in `sudo iptables -S INPUT` bereits eine `eth0`-Regel für 22, nicht
doppelt anlegen.

## Schritt 5: Per ssh über LAN verbinden

Mit dem Alias aus `~/.ssh/config`:

```bash
ssh G-A2610-0007-lan
```

Ohne Alias (anderer Rechner):

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no \
-o HostKeyAlias=G-A2610-0007 bernard@169.254.42.1
```

Passwort für `bernard` eingeben. Der Prompt muss `G-A2610-0007:~$` lauten,
sonst sofort abmelden.

Der Alias pinnt den Host-Key auf die Seriennummer (`HostKeyAlias`). Hängt am
Kabel ein anderer BMA mit derselben `169.254.42.1`, bricht ssh mit einer
Host-Key-Warnung ab, statt sich still zu verbinden.

## Trennen

1. ssh-Sitzung mit `exit` beenden.
2. LAN-Adresse am Laptop entfernen (oder Adapter abziehen):

```bash
nmcli connection down enx0050b6f802ad
```

Die Firewall-Freigabe auf dem BMA verschwindet beim nächsten Neustart. Sofort
entfernen: siehe [bma-betreuer.md, „Stoppen und aufräumen“](bma-betreuer.md#stoppen-und-aufräumen).

## Fehlersuche

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| Adapter fehlt in `ip -br link`, `lsusb` zeigt aber `ASIX AX88772B` | Nach Standby bindet der `asix`-Treiber den Adapter manchmal nicht neu (beobachtet am 02.11.2026) | Adapter abziehen und neu einstecken; hilft das nicht, Treiber neu laden (siehe unten) |
| `nmcli connection up` meldet „no suitable device“ | Adapter heißt anders (anderer Adapter, andere MAC) | Namen mit `ip -br link` ermitteln, Adresse von Hand setzen (siehe unten) |
| `ping` ohne Antwort, Adresse am Laptop stimmt | Kein Link, Kabel steckt nicht am BMA | Kabel prüfen; `ip -br link` muss beim Adapter `UP` und `LOWER_UP` zeigen |
| Ping geht, ssh läuft in Timeout | Firewall des BMA sperrt Port 22 auf `eth0` (z. B. nach Neustart) | Schritt 4 |
| ssh: „Too many authentication failures“ | ssh bietet erst alle Keys aus `~/.ssh` an | Alias verwenden oder `-o PubkeyAuthentication=no` |
| ssh: „REMOTE HOST IDENTIFICATION HAS CHANGED“ | Am Kabel hängt ein anderer BMA | Nicht verbinden; Gerät prüfen |
| `ssh G-A2610-0007` (VPN) läuft in Timeout | VPN-IP des BMA hat sich geändert | IP nachschlagen und in `~/.ssh/config` eintragen (siehe [bma-betreuer.md](bma-betreuer.md#optional-kurznamen-in-sshconfig)) |

Treiber neu laden, wenn Neustecken nicht hilft (betrifft alle
ASIX-USB-LAN-Adapter am Laptop):

```bash
sudo modprobe -r asix
```

```bash
sudo modprobe asix
```

Adresse von Hand setzen, wenn der Adapter anders heißt (`<adapter>` durch den
Namen aus `ip -br link` ersetzen; gilt bis zum Abziehen oder Neustart):

```bash
sudo ip link set <adapter> up
```

```bash
sudo ip addr add 169.254.42.2/16 dev <adapter>
```
