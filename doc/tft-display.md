# Das Schild: TFT-Bildschirm am Raspberry Pi

Das Schild an der Einfahrt ist ein kleiner Farbbildschirm, der **Joy-IT
RB-TFT1.8**. Er hängt direkt am Raspberry Pi. Euer Programm zeichnet ein Bild
(zum Beispiel einen Pfeil) und schickt es auf den Bildschirm.

> **Hinweis:** Die Werte unten (Verkabelung, Drehung, Versatz, Farbreihenfolge)
> stammen aus der Anleitung des Herstellers und sind am Hackathon-Pi noch nicht
> mit dem echten Bildschirm getestet. Sind Bild oder Farben verschoben oder
> vertauscht, passt `rotation`, `x_offset`/`y_offset` oder `bgr` an.

| Eigenschaft | Wert |
| --- | --- |
| Modul | Joy-IT RB-TFT1.8, 1,8 Zoll ([Anleitung](https://manuals.plus/joy-it/rb-tft1-8-18-tft-display-manual.pdf)) |
| Controller | ST7735 |
| Auflösung | **160 × 128 Pixel** im Querformat |
| Anschluss | SPI (nur senden), plus zwei Steuerleitungen |
| Spannung | 3,3 V (nicht 5 V!) |
| Bibliothek | [`luma.lcd`](https://luma-lcd.readthedocs.io/) |

## So funktioniert es

```
 euer Programm                  tft_display / luma.lcd             TFT
 ┌─────────────────────┐        ┌────────────────────────┐        ┌──────┐
 │ Pillow-Bild zeichnen│ ─────► │ Bild in Pixeldaten     │ ─SPI─► │ ◄━━  │
 │ 160 × 128 Pixel     │        │ umwandeln und senden   │        │3 frei│
 └─────────────────────┘        └────────────────────────┘        └──────┘
```

Ihr malt mit [Pillow](https://pillow.readthedocs.io/) auf ein Bild, das genau
so groß ist wie der Bildschirm. Mit `display(bild)` landet es komplett auf dem
Bildschirm. Um die Übertragung müsst ihr euch nicht kümmern.

## Verdrahtung

Laut Joy-IT-Anleitung. „Pin“ ist die Nummer auf der 40-poligen Stiftleiste des
Pi (Pin 1 erkennt ihr am eckigen statt runden Lötpunkt).

| TFT | Raspberry Pi | Pin | Wofür |
| --- | --- | --- | --- |
| VCC | 3,3 V | 1 | Strom |
| GND | GND | 6 | Masse |
| SCL | GPIO 11 (SCLK) | 23 | SPI-Takt |
| SDA | GPIO 10 (MOSI) | 19 | SPI-Daten |
| CS | GPIO 8 (CE0) | 24 | „Du bist gemeint“ (Chip Select) |
| RS/DC | GPIO 25 | 22 | Befehl oder Bilddaten? |
| RES | GPIO 24 | 18 | Reset |

Die übrigen Pins des Moduls (MISO, SCLK, MOSI, CS auf der anderen Seite)
gehören zum SD-Kartenslot auf der Rückseite und bleiben frei. Einen eigenen
Pin für die Hintergrundbeleuchtung hat das Modul nicht: Sie leuchtet, sobald
Strom anliegt.

> **Achtung:** DC und RES sind in `luma.lcd` standardmäßig **vertauscht**
> voreingestellt (DC=24, RES=25). Gebt sie deshalb immer an, wie unten
> gezeigt. `tft_display.open_tft()` macht das schon richtig.

## Einrichtung (Betreuer, einmalig)

SPI ist auf dem Pi standardmäßig aus. Einschalten und neu starten:

```bash
sudo raspi-config nonint do_spi 0
```

```bash
sudo reboot
```

Der Neustart unterbricht den MQTT-Broker für etwa eine Minute.

Danach müssen diese beiden Geräte existieren:

```bash
ls -l /dev/spidev0.*
```

Der Benutzer, der das Programm startet, muss in den Gruppen `spi` und `gpio`
sein (`pi` ist es). Dann braucht es kein `sudo`.

## Software installieren (auf dem Pi)

Im Projektordner:

```bash
uv sync --extra pi
```

`--extra pi` installiert zusätzlich die Teile, die es nur auf dem Pi gibt:
`spidev` (SPI) und `rpi-lgpio` (GPIO). Auf dem Laptop lasst ihr es weg.

> **Warum Python 3.12?** Das Projekt ist mit `.python-version` auf 3.12
> festgelegt. Die GPIO-Bibliothek `lgpio` gibt es nur bis Python 3.12 als
> fertiges Paket, mit 3.13 müsste sie erst kompiliert werden. uv lädt das
> passende Python selbst herunter.

## Erster Test

Das kleinste Beispiel: ein grüner Pfeil und „3 frei“, zehn Sekunden lang.

```bash
uv run python examples/tft_hello.py
```

Der Code dazu, zum Abschauen ([`examples/tft_hello.py`](../examples/tft_hello.py)):

```python
from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from PIL import Image, ImageDraw

serial = spi(port=0, device=0, gpio_DC=25, gpio_RST=24)
device = st7735(serial, width=160, height=128, backlight=lambda on: None)

image = Image.new("RGB", device.size, "black")
draw = ImageDraw.Draw(image)
draw.polygon(
    [(10, 30), (90, 30), (90, 10), (150, 50), (90, 90), (90, 70), (10, 70)],
    fill="green",
)
device.display(image)
```

`backlight=lambda on: None` sagt luma: „Es gibt keine Beleuchtung zum
Schalten.“ Ohne das würde luma GPIO 18 belegen.

### Testbild: stimmen Farben und Rand?

```bash
uv run python examples/tft_display_demo.py
```

Zeigt nacheinander ein Testbild, Pfeil links, Pfeil rechts, ein X und Text,
je drei Sekunden. Beim Testbild prüfen:

| Was ihr seht | Lösung |
| --- | --- |
| Balken lesen sich **Blau, Grün, Rot**, Weiß statt Rot, Grün, Blau, Weiß | `--bgr` |
| Alle Farben „negativ“ (Schwarz ist weiß) | `invert=True` in `TftConfig` |
| Eine bunte Linie oder Pixelmüll an einem Rand | `--x-offset 1` bzw. `--y-offset 1` (oder 2) probieren |
| Bild steht auf dem Kopf | `--rotation 180` |

## In eurem Programm

Am bequemsten mit dem Baustein `tft_display` aus diesem Repository:

```python
from PIL import Image, ImageDraw, ImageFont

from tft_display import TftConfig, open_tft

with open_tft(TftConfig()) as tft:
    image = Image.new("RGB", tft.size, "black")
    draw = ImageDraw.Draw(image)
    draw.text(
        (80, 64),
        "Hallo!",
        fill="white",
        font=ImageFont.load_default(30),
        anchor="mm",
    )
    tft.display(image)
    input("Enter zum Beenden")
```

- `with open_tft(...)` öffnet den Bildschirm und gibt SPI und GPIO am Ende
  wieder frei, auch bei einem Fehler. Beim Beenden geht der Bildschirm aus.
- `tft.size` ist `(160, 128)`. Das Bild muss **genau** so groß sein.
- Zeichnet das Bild nur neu, wenn sich etwas ändert. Jedes Bild sind 40 kB
  über SPI, und ständiges Neuzeichnen flackert.
- `TftConfig(rotation=180, x_offset=1, bgr=True)` übernimmt die Einstellungen
  aus dem Testbild.

Nützliches aus Pillow:

| Wofür | Aufruf |
| --- | --- |
| Text (zentriert) | `draw.text((x, y), "Text", fill="white", font=ImageFont.load_default(24), anchor="mm")` |
| Pfeil, Dreieck, Vieleck | `draw.polygon([(x1, y1), (x2, y2), ...], fill="green")` |
| Linie (z. B. für ein X) | `draw.line((x1, y1, x2, y2), fill="red", width=10)` |
| Rechteck | `draw.rectangle((links, oben, rechts, unten), fill="blue")` |
| Bild aus Datei | `Image.open("rollstuhl.png").convert("RGB").resize((64, 64))`, dann `image.paste(icon, (x, y))` |

Koordinaten: `(0, 0)` ist **oben links**, x wächst nach rechts bis 159, y nach
unten bis 127.

## Ohne Bildschirm testen

Am Laptop gibt es kein SPI. `PngPreview` verhält sich wie der Bildschirm,
schreibt das Bild aber in eine Datei, die ihr euch ansehen könnt:

```python
from pathlib import Path

from tft_display import PngPreview

tft = PngPreview(Path("schild.png"), size=(160, 128))
tft.display(image)
```

Die Demo kann das auch:

```bash
uv run python examples/tft_display_demo.py --preview tmp/tft
```

Schreibt `tmp/tft/test.png`, `left.png`, `right.png`, `cross.png` und
`text.png`.

## Hilfe, der Bildschirm bleibt dunkel oder weiß

| Was ihr seht | Ursache |
| --- | --- |
| `DeviceNotFoundError: SPI device not found` | SPI ist nicht aktiviert (siehe [Einrichtung](#einrichtung-betreuer-einmalig)) |
| `ModuleNotFoundError: No module named 'RPi'` oder `'spidev'` | `uv sync --extra pi` vergessen |
| `Permission denied` bei `/dev/spidev0.0` oder `/dev/gpiochip0` | Benutzer nicht in den Gruppen `spi`/`gpio` |
| `GPIO busy` | Ein anderes Programm nutzt den Bildschirm schon; immer nur eines gleichzeitig |
| Bildschirm leuchtet weiß, zeigt aber nichts | DC/RES vertauscht oder falsch gesteckt; Verdrahtung prüfen |
| Bildschirm komplett dunkel | Kein Strom: VCC an 3,3 V, GND prüfen |
| `ValueError` / `AssertionError` beim Anzeigen | Bild hat nicht genau `tft.size` Pixel |

### Hintergrund: Raspberry Pi 5

Der Pi 5 hat einen neuen Chip für die GPIO-Pins (RP1). Die alte Bibliothek
`RPi.GPIO` funktioniert darauf nicht mehr. `luma.lcd` nutzt deshalb
`rpi-lgpio`, einen Ersatz mit derselben Schnittstelle, der auf dem Pi 5 läuft.
Installiert nie zusätzlich `RPi.GPIO`, die beiden stören sich gegenseitig.
