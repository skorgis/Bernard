# picture_pipeline

Finds known logos or symbols in camera frames, and tells you **where** they
are. It includes a GUI for tuning every parameter live on a webcam stream.

```
frame ──► frame preprocessing ──► keypoint detection ──► matching ──► results per logo
                                       (shared)             ▲          (found, corners, …)
logos ──► logo preprocessing ───► keypoint detection ───────┘
          (once, at start)
```

The logos and the frames each have their **own** preprocessing, for example
to shrink only the logos or crop only the frame. Both share **one** keypoint
extractor, because descriptors from different extractors can't be compared.
The logos are processed once, at start. Per frame, keypoints are extracted
**once** and matched against every logo, so adding logos is cheap.

Built on OpenCV (`opencv-contrib-python`, for AKAZE/BRISK) and NumPy. The
design is described in [ARCHITECTURE.md](ARCHITECTURE.md).

## Quick start: webcam + GUI

1. Put one image per logo into `logos/` at the repository root (`.png`,
   `.jpg`, `.jpeg`, `.bmp`, `.webp`; transparent PNGs are fine). The file
   name becomes the logo's name.
2. Run:

   ```bash
   uv run python examples/logo_webcam.py
   ```

   Options:
   - `--logos <folder>`: use a different logo folder.
   - `--source recording.mp4`: an image or video file as an extra source.
     Use it without a camera, or to tune on a recording; videos loop.
   - `--settings <file>`: where settings are loaded from and saved to
     (default `logo_tuner_settings.json`).

The window shows the frame with each found logo outlined in its own color
and labelled with its name. On the right:

| Control | What it does |
| --- | --- |
| **Quelle** | Camera dropdown, listed by name, e.g. `4: Anker PowerConf C200`, plus the `--source` file. A camera switches on only when chosen. |
| **Keypoint-Extraktor** | SIFT, ORB, AKAZE or BRISK. |
| **Matcher** | Brute-Force (exact) or FLANN (approximate, faster with many keypoints). |
| **Kontrastausgleich (CLAHE)** | Contrast equalization for logos and frames. |
| **Kantenfilter (Canny)** | Edge filter for logos and frames: the extractor sees only outlines. Thresholds via `canny_low`/`canny_high`. |
| **Keypoints anzeigen** | Draws the frame's keypoints. Use it to see whether the logo region gets any. |
| **Vorverarbeitetes Bild zeigen** | Shows the frame — and the logo thumbnails — as the extractor sees them, after resize/filters/CLAHE. |
| **Bounding Box statt Umriss** | Upright box instead of the rotated outline. |
| **Vorverarbeitungsschritte zeigen** | A row of small thumbnails below the image: the input frame, then the result after each frame preprocessing step, labelled with the step and its values. Shows what each filter does. |
| **Sliders** | Every numeric parameter (see [Parameters](#parameters)). The image updates while you drag. |
| **Einstellungen speichern** | Saves the settings as JSON (loaded on the next start), prints the matching **Python code** to the terminal and copies it to the clipboard. |
| **Standardwerte** | Resets every setting to the recommended defaults (the *Default* column under [Parameters](#parameters)). Not saved until you press *Einstellungen speichern*. |
| Logo thumbnails | Each logo, top right, framed in its outline color. |
| Status | FPS, keypoints in the frame, and per logo: found or not, good matches, inliers. |

## Just watching: camera + bounding boxes

Once the settings are tuned, `logo_viewer.py` shows only the camera feed
with a box around each found logo, without any controls:

```bash
uv run python examples/logo_viewer.py              # last listed camera
uv run python examples/logo_viewer.py --camera 5
```

It loads `logo_tuner_settings.json` if present. Detection runs in a
background thread on the newest frame (`live.BackgroundAnalyzer`), so the
video keeps the camera's frame rate and the boxes update as fast as
detection allows. The title line shows both rates. Quit with `q` or `Esc`.

Cameras are opened at 1920×1080 (MJPG); OpenCV's default of 640×480 leaves
small logos too few pixels. `frame_max_side` 1280 makes SIFT about 2x
faster (160 instead of 370 ms per frame) but loses logos under ~50 px in
the full frame; the video stays smooth either way.

If logos aren't found although they're in view, check focus first: with
continuous autofocus the camera may focus on the background. Fix it with
`v4l2-ctl -d /dev/videoN -c focus_automatic_continuous=0 -c
focus_absolute=<value>` (try values across the camera's range).

## Using it in code

### One logo

```python
import cv2

from picture_pipeline.pipeline import LogoDetectionPipeline
from picture_pipeline.visualization import draw_detection

logo = cv2.imread("logo.png")
frame = cv2.imread("frame.png")

pipeline = LogoDetectionPipeline(logo)
result = pipeline.process(frame)

print(result.found, result.good_matches, result.inliers)
cv2.imwrite("frame_marked.png", draw_detection(frame, result))
```

### Several logos, e.g. from the `logos/` folder

```python
from picture_pipeline.logo_loading import load_logos
from picture_pipeline.pipeline import MultiLogoPipeline
from picture_pipeline.visualization import LOGO_COLORS, draw_detection

pipeline = MultiLogoPipeline(load_logos("logos"))
analysis = pipeline.analyze(frame)

marked = frame
for number, (name, result) in enumerate(analysis.results.items()):
    if result.found:
        print(name, "at", result.corners.tolist())
    marked = draw_detection(
        marked, result, color=LOGO_COLORS[number], show_status=False, label=name
    )
```

`analyze` returns a `FrameAnalysis` with:
- `results`: logo name → `MatchResult`,
- `preprocessed`: the frame after frame preprocessing,
- `features`: its keypoints, e.g. for `draw_keypoints(frame, analysis.features)`.

### Settings from the GUI

The code printed by **Einstellungen speichern** builds exactly the pipeline
you tuned, from a `logos` dict:

```python
logos = load_logos("logos")
# ... paste the printed code here ...
analysis = pipeline.analyze(frame)
```

Alternatively, load the saved JSON:
`TuningSettings.load("logo_tuner_settings.json").build_pipeline(logos)`.

### `MatchResult`

| Field | Meaning |
| --- | --- |
| `found` | Whether the logo is in the frame. |
| `corners` | The logo's outline in the frame: 4 points (top-left, top-right, bottom-right, bottom-left *of the logo*, so it shows the rotation). `None` if not found. |
| `homography` | 3×3 matrix mapping pixels of the *preprocessed* logo to frame pixels, e.g. for `cv2.warpPerspective`. `None` if not found. |
| `good_matches`, `inliers` | How many matches survived the ratio test, and how many of those fit the homography. They show *where* a detection failed: `good=1` means the logo isn't there, `good=25, inliers=6` means it nearly matched. |
| `frame_shape` | `(height, width)` of the frame that `corners`/`homography` refer to: the frame *after* frame preprocessing. |

### Marking the logo in the frame

`draw_detection(frame, result)` returns a **copy** of the frame, so the
original stays untouched, with the logo's outline (if found) and a status
line. Options:
- `bounding_box=True`: draw the upright rectangle instead of the outline.
- `label="name"`: write a name above the outline.
- `show_status=False`: leave out the status text.
- `color`, `thickness`: line style.

`draw_keypoints(frame, features)` draws keypoints the same way.

Both accept the **original** frame even if the frame preprocessing resized
it: coordinates are scaled from `frame_shape` to the frame you draw on. If a
frame step changed the aspect ratio (e.g. a crop), that mapping is unknown
and they raise `ValueError`. In that case, draw on `analysis.preprocessed`.

## Parameters

The building blocks behind the GUI are constructor arguments in code:

```python
from picture_pipeline.keypoints import DetectorKind, KeypointDetector
from picture_pipeline.matching import LogoMatcher, MatcherKind
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    equalize_contrast,
    gaussian_blur,
    resize_to_max_side,
    to_grayscale,
)

pipeline = MultiLogoPipeline(
    logos,
    # Logo files are high-resolution and clean: shrink them towards the
    # size they have in the frames, without blur.
    logo_preprocessing=PreprocessingPipeline(
        [to_grayscale, resize_to_max_side(200), equalize_contrast()]
    ),
    # Camera frames are large and noisy: shrink and denoise them.
    frame_preprocessing=PreprocessingPipeline(
        [
            to_grayscale,
            resize_to_max_side(960),
            gaussian_blur(3),
            equalize_contrast(),
        ]
    ),
    detector=KeypointDetector(DetectorKind.SIFT, max_features=2000),
    matcher=LogoMatcher(ratio=0.75, matcher=MatcherKind.FLANN),
)
```

| Parameter (slider) | Default | Effect |
| --- | --- | --- |
| `max_features` | 1000 | Strongest N keypoints kept per image. More can help small logos in large frames, at a speed cost. |
| `ratio` | 0.75 | Lowe's ratio. Lower is stricter, with fewer but more reliable matches. |
| `min_good_matches` | 10 | Matches needed after the ratio test. Raise it against false positives; lower it for small or blurry logos. |
| `min_inliers` | 8 | Matches that must agree on one placement (at least 4). |
| `ransac_threshold` | 5.0 px | Pixel error a match may have and still count as an inlier. |
| `max_side_ratio` | 2.0 | How much opposite sides of the outline may differ in length. It rejects wildly distorted fits; raise it if the camera sees logos at a steep angle. |
| `frame_max_side` | 0 (off) | Shrink frames to this longer side. It's the biggest speed lever. |
| `frame_blur` | 0 (off) | Gaussian blur (low-pass) kernel for frames (odd). Suppresses sensor-noise keypoints. |
| `clahe_clip_limit` | 2.0 | Strength of the contrast equalization (when CLAHE is on). |
| `logo_max_side` | 0 (off) | Shrink logos to this longer side, towards their size in the frame. |
| `logo_blur` | 0 (off) | Gaussian blur (low-pass) kernel for logos (odd), e.g. to match a blurry camera. |
| `high_pass` | 0 (off) | High-pass kernel for logos and frames (odd, ≥ 3): keeps detail finer than this, removes smooth shading and lighting gradients. Amplifies noise, so pair it with `frame_blur`. |
| `canny_low` / `canny_high` | 50 / 150 | Canny hysteresis thresholds (when the edge filter is on); `low` must not exceed `high`. Lower finds more, weaker edges. |

- **Logo vs. frame preprocessing:** they may differ, but must stay
  *comparable*. If only one side is grayscale or contrast-equalized, the
  descriptors won't match well.
- **Your own step:** any function `Image -> Image` works, e.g.
  `lambda img: img[100:400, :]` to crop to a region of interest.

### Which keypoint extractor?

Measured on the synthetic test images: a 160 px logo pasted into a
cluttered 640×480 frame at 8 rotations × 4 scales, with an outline counted as
correct within 6 px. Times are from a desktop PC, so a Raspberry Pi is
several times slower.

| Extractor | correct outline | outline off by > 6 px | not found | false positives | ms/frame |
| --- | --- | --- | --- | --- | --- |
| **SIFT** (default) | 32/32 | 0 | 0 | 0/10 | 27 |
| **ORB** | 15/32 | 13 | 4 | 0/10 | 7 |
| **AKAZE** | 2/32 | 6 | 24 | 0/10 | 24 |
| **BRISK** | 6/32 | 18 | 8 | 0/10 | 21 |

- **SIFT** is accurate across rotation and scale, down to half size. Use it
  unless speed is a problem.
- **ORB** is the fastest and fine for logos shown large (scale ≥ 0.8). For
  small or far-away logos its outline becomes imprecise (typically 6–20 px
  off on a 160 px logo), even when "found" is correct.
- **AKAZE / BRISK** did poorly on these synthetic images, which are flat
  colour shapes. They may do better on real, photographed logos. Compare them
  in the GUI on your own camera images before deciding.
- **FLANN vs. Brute-Force:** the same detection quality in the tests. FLANN
  only pays off with thousands of keypoints.

## Things to know

- **The logo needs texture.** Keypoints sit on corners and detailed
  structure. A flat single-colour shape or a plain circle yields few or none,
  and the pipeline raises `ValueError` naming that logo.
- **Crop logos tightly.** Background in a logo image produces keypoints that
  aren't part of the logo. Transparent PNG areas are flattened onto white.
- **Flat logos only.** The homography models a flat surface. Logos on
  strongly curved surfaces (bottles, round signs seen from the side) fit
  badly.
- **One match per logo per frame.** If a logo appears several times, one
  occurrence is reported.
- **Coordinates:** `corners` and `homography` are in the coordinates of the
  *preprocessed* frame. They equal the original frame's unless one of your
  *frame* steps resizes or crops; the drawing functions handle resizing.
  Logo steps don't affect them.
- **Installation:** `opencv-contrib-python` replaces `opencv-python`; never
  install both, as they overwrite each other's `cv2`. On a Raspberry Pi
  without a display, `opencv-contrib-python-headless` is the right variant,
  but the GUI then needs a display (or X forwarding) anyway.

## Tests

```bash
uv run pytest tests/test_preprocessing.py tests/test_keypoints.py \
  tests/test_logo_matching.py tests/test_multi_logo.py tests/test_visualization.py \
  tests/test_tuning.py tests/test_sources.py tests/test_frame_sources.py \
  tests/test_gui_render.py
```

They use synthetic images (`tests/picture_fixtures.py`): a generated logo
pasted into a cluttered background at a known position, rotation and scale.
The tests can therefore check *where* a logo was found, not only *that* it
was found. The GUI window itself isn't covered, but the drawing and status
functions it uses are.
