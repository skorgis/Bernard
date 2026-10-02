"""Show a camera feed with a bounding box around every logo found.

No controls: it uses the settings tuned with `logo_webcam.py` (or fast
defaults if there are none) and just displays the result.

    uv run python examples/logo_viewer.py              # last listed camera
    uv run python examples/logo_viewer.py --camera 5
    uv run python examples/logo_viewer.py --source recording.mp4

Detection runs in a background thread on the newest frame, so the video
keeps the camera's frame rate; the boxes update as fast as detection
allows. Quit with q or Esc, or close the window.
"""

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path

import cv2

from picture_pipeline.cameras import list_cameras
from picture_pipeline.frame_sources import CameraSource, FileSource, FrameSource
from picture_pipeline.gui import logo_status_lines, render
from picture_pipeline.image import Image
from picture_pipeline.live import BackgroundAnalyzer, FpsCounter
from picture_pipeline.logo_loading import load_logos
from picture_pipeline.pipeline import FrameAnalysis
from picture_pipeline.tuning import TuningSettings

WINDOW = "Logo-Erkennung"
_QUIT_KEYS = {ord("q"), 27}
# Without tuned settings: SIFT on the full HD frame with more keypoints
# than the default 1000. Shrinking frames (`frame_max_side`) speeds up
# detection but loses logos smaller than ~50 px; the video stays smooth
# either way, since detection runs in the background.
FAST_DEFAULTS = TuningSettings(max_features=3000)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Show a camera feed with logo bounding boxes."
    )
    parser.add_argument("--logos", type=Path, default=Path("logos"))
    parser.add_argument("--camera", type=int, help="Camera index.")
    parser.add_argument("--source", type=Path, help="Video/image instead.")
    parser.add_argument(
        "--settings", type=Path, default=Path("logo_tuner_settings.json")
    )
    return parser.parse_args(argv)


def open_source(args: argparse.Namespace) -> FrameSource:
    """The file if given, else the chosen or last listed camera."""
    if args.source is not None:
        return FileSource(args.source)
    if args.camera is not None:
        return CameraSource(args.camera)
    cameras = list_cameras()
    if not cameras:
        raise ValueError("keine Kamera gefunden; --camera oder --source")
    # USB webcams are usually listed after the built-in camera.
    print("Kamera:", cameras[-1])
    return CameraSource(cameras[-1].index)


def load_settings(path: Path) -> TuningSettings:
    """Tuned settings if saved, else `FAST_DEFAULTS`."""
    if path.exists():
        print("Einstellungen:", path)
        return TuningSettings.load(path)
    return FAST_DEFAULTS


def annotate(
    frame: Image,
    analysis: FrameAnalysis | None,
    display: FpsCounter,
    detection: FpsCounter,
) -> Image:
    """The frame with bounding boxes, both frame rates and per-logo state.

    The state lines tell "not found" apart from "not drawn": a box only
    appears for logos that were found.
    """
    if analysis is None:
        canvas = frame.copy()
        lines = ["Erkennung startet ..."]
    else:
        canvas = render(frame, analysis, False, False, bounding_box=True)
        lines = logo_status_lines(analysis)
    lines.insert(
        0, f"Anzeige {display.fps:.0f} FPS | Erkennung {detection.fps:.1f} FPS"
    )
    for row, line in enumerate(lines):
        _draw_outlined_text(canvas, line, (12, 36 + 34 * row))
    return canvas


def _draw_outlined_text(
    canvas: Image, text: str, origin: tuple[int, int]
) -> None:
    for color, width in (((0, 0, 0), 4), ((255, 255, 255), 2)):
        cv2.putText(
            canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, width
        )


def run(
    source: FrameSource, settings: TuningSettings, logos: Mapping[str, Image]
) -> None:
    """Show `source` with detections until the user quits."""
    pipeline = settings.build_pipeline(logos)
    analyzer = BackgroundAnalyzer(pipeline.analyze)
    display, detection = FpsCounter(), FpsCounter()
    shown: FrameAnalysis | None = None
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 1280, 720)
    try:
        while cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) >= 1:
            frame = source.read()
            if frame is not None:
                analyzer.submit(frame)
                analysis = analyzer.latest()
                if analysis is not None and analysis is not shown:
                    shown = analysis
                    detection.tick()
                display.tick()
                cv2.imshow(WINDOW, annotate(frame, shown, display, detection))
            if cv2.waitKey(1) & 0xFF in _QUIT_KEYS:
                break
    finally:
        analyzer.stop()
        source.release()
        cv2.destroyAllWindows()


def main(argv: list[str] | None = None) -> int:
    """Open the source and the window."""
    args = parse_args(argv)
    try:
        logos = load_logos(args.logos)
        source = open_source(args)
    except (FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{len(logos)} Logo(s): {', '.join(logos)}")
    run(source, load_settings(args.settings), logos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
