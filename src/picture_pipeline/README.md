# picture_pipeline: Logos im Kamerabild finden

Findet bekannte Symbole (zum Beispiel ein Rollstuhl-Kennzeichen) im Bild
einer Kamera und sagt euch, **wo** sie sind. Der ganze Code steht in einer
Datei: [`logo_finder.py`](logo_finder.py).

## Schnellstart

1. Legt ein Bild pro Symbol in den Ordner `logos/` im Hauptordner des
   Projekts (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`; transparente PNGs
   gehen auch). Der Dateiname wird zum Namen: `logos/rollstuhl.png` heißt
   `"rollstuhl"`.
2. Startet das Beispiel:

   ```bash
   uv run python examples/logo_webcam.py
   ```

   Andere Quellen:

   ```bash
   uv run python examples/logo_webcam.py --source 2
   ```

   ```bash
   uv run python examples/logo_webcam.py \
     --source http://hackathon.local:8080/stream.ts
   ```

   Die erste Zeile nimmt Webcam Nummer 2, die zweite das Kamerabild des
   BMA (siehe Haupt-README), ein Dateiname geht auch.

Gefundene Symbole bekommen einen grünen Rahmen mit Namen. Oben links steht,
welches Symbol gefunden wurde und mit wie vielen **Paaren** (siehe unten).
Mit den Schiebereglern stellt ihr die Erkennung ein. Die Taste **s** gibt
die passende Zeile für euer eigenes Programm aus, **q** beendet.

## Im eigenen Programm

```python
import cv2

from picture_pipeline.logo_finder import LogoFinder, draw, load_logos

logos = load_logos("logos")
finder = LogoFinder(logos)

frame = cv2.imread("foto.jpg")  # oder ein Bild von cv2.VideoCapture
found = finder.find(frame)

rollstuhl = found["rollstuhl"]
if rollstuhl is not None:
    print("Rollstuhl-Symbol bei", rollstuhl.center)

cv2.imwrite("markiert.jpg", draw(frame, found))
```

`find` gibt für jedes Logo entweder `None` (nicht gefunden) oder eine
`Detection` zurück:

| Feld | Bedeutung |
| --- | --- |
| `corners` | Die 4 Ecken des Symbols im Bild, in Pixeln (x, y): oben links, oben rechts, unten rechts, unten links **des Symbols**. Daran seht ihr auch, ob es gedreht ist. |
| `center` | Die Mitte des Symbols im Bild (x, y). |
| `matches` | Wie viele Paare zur gefundenen Lage passen. Je mehr, desto sicherer. |

`draw(frame, found)` gibt eine **Kopie** des Bildes mit Rahmen zurück; das
Originalbild bleibt unverändert.

## Wie die Erkennung funktioniert

1. **Merkmale finden:** Das Verfahren SIFT sucht auffällige Stellen
   (Ecken, feine Details), sogenannte *Keypoints*, im Symbol und im
   Kamerabild. Jede Stelle wird durch 128 Zahlen beschrieben.
2. **Paare bilden:** Für jede Stelle im Symbol werden die zwei ähnlichsten
   Stellen im Kamerabild gesucht.
3. **Unsichere Paare aussortieren (Ratio-Test):** Ein Paar bleibt nur, wenn
   der beste Partner deutlich ähnlicher ist als der zweitbeste. Sonst ist
   es meist eine Verwechslung.
4. **Gemeinsame Lage prüfen (RANSAC):** Die übrigen Paare müssen sich auf
   eine Position, Drehung und Größe des Symbols einigen. Paare, die nur
   zufällig ähnlich aussehen, passen nicht dazu und fliegen raus. Bleiben
   genug übrig, ist das Symbol gefunden.

Vorher werden Symbol und Kamerabild in Graustufen umgewandelt und der
Kontrast ausgeglichen, damit unterschiedliches Licht weniger stört.

## Einstellungen

```python
finder = LogoFinder(logos, ratio=0.75, min_matches=10, frame_max_side=0)
```

| Einstellung | Standard | Wirkung |
| --- | --- | --- |
| `ratio` | 0.75 | Grenze für den Ratio-Test (zwischen 0 und 1). Kleiner ist strenger: weniger, aber verlässlichere Paare. |
| `min_matches` | 10 | So viele Paare müssen zur selben Lage passen. Höher gegen Fehlalarme, niedriger für kleine oder unscharfe Symbole. |
| `frame_max_side` | 0 (aus) | Verkleinert das Kamerabild auf diese längere Seite, bevor gesucht wird. Macht die Erkennung viel schneller (z. B. 1280 statt Full HD), aber sehr kleine Symbole gehen verloren. |

Die Werte könnt ihr auch während des Laufs ändern, z. B.
`finder.min_matches = 15`.

## Wenn nichts gefunden wird

- **Das Symbol braucht Details.** Gefunden werden Ecken und Strukturen.
  Ein einfarbiger Kreis hat keine; `LogoFinder` meldet dann einen Fehler
  mit dem Namen des Logos.
- **Das Bild des Symbols eng zuschneiden**, ohne viel Hintergrund. Sonst
  sucht ihr auch nach dem Hintergrund.
- **Schärfe prüfen.** Webcams mit Autofokus stellen gern auf den
  Hintergrund scharf.
- **Flache Symbole:** Die Erkennung geht von einer ebenen Fläche aus. Stark
  gewölbte Flächen passen schlecht.
- **Ein Treffer pro Symbol:** Ist dasselbe Symbol mehrmals im Bild, wird
  eines davon gemeldet.
- **Zu langsam?** `frame_max_side` auf 1280 oder 960 stellen.

## Tests

```bash
uv run pytest tests/test_logo_finder.py
```

Die Tests erzeugen künstliche Bilder (`tests/picture_fixtures.py`): Ein
Symbol wird an bekannter Stelle, gedreht und skaliert, in einen unruhigen
Hintergrund gesetzt. So prüfen die Tests nicht nur, **ob** das Symbol
gefunden wird, sondern auch **wo**.
