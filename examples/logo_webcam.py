"""Find the logos from `logos/` in a camera image and tune the search live.

    uv run python examples/logo_webcam.py               # webcam 0
    uv run python examples/logo_webcam.py --source 2    # another webcam
    uv run python examples/logo_webcam.py --source http://hackathon.local:8080/stream.ts
    uv run python examples/logo_webcam.py --source video.mp4

The sliders change the `LogoFinder` settings while it runs. Press `s` to
print the matching Python line for your own program, `q` or Esc to quit.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from picture_pipeline.logo_finder import Image, LogoFinder, draw, load_logos

WINDOW = "Logo-Erkennung"
QUIT_KEYS = {ord("q"), 27}
SAVE_KEY = ord("s")
# OpenCV opens webcams at 640x480 unless asked; small logos then get too
# few pixels for keypoints. Most webcams deliver HD only as MJPG over USB.
WEBCAM_SIZE = (1920, 1080)
# Slider ranges. Trackbars only know whole numbers, so the ratio is in
# percent; 0 for the frame size means "don't shrink".
RATIO_PERCENT = (50, 95)
MIN_MATCHES = (4, 60)
FRAME_MAX_SIDE = 1920


def open_source(source: str) -> cv2.VideoCapture:
    """A webcam (given as its number), a video file or a stream URL."""
    if not source.isdigit():
        return cv2.VideoCapture(source)
    capture = cv2.VideoCapture(int(source))
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, WEBCAM_SIZE[0])
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_SIZE[1])
    return capture


def add_sliders(finder: LogoFinder) -> None:
    """One slider per setting, starting at the finder's current values."""
    cv2.createTrackbar(
        "ratio %", WINDOW, round(finder.ratio * 100), RATIO_PERCENT[1], _ignore
    )
    cv2.setTrackbarMin("ratio %", WINDOW, RATIO_PERCENT[0])
    cv2.createTrackbar(
        "min matches", WINDOW, finder.min_matches, MIN_MATCHES[1], _ignore
    )
    cv2.setTrackbarMin("min matches", WINDOW, MIN_MATCHES[0])
    cv2.createTrackbar(
        "max side", WINDOW, finder.frame_max_side, FRAME_MAX_SIDE, _ignore
    )


def read_sliders(finder: LogoFinder) -> None:
    """Copy the slider positions into the finder's settings."""
    finder.ratio = cv2.getTrackbarPos("ratio %", WINDOW) / 100
    finder.min_matches = cv2.getTrackbarPos("min matches", WINDOW)
    finder.frame_max_side = cv2.getTrackbarPos("max side", WINDOW)


def as_code(finder: LogoFinder) -> str:
    """The line that creates a finder with the current settings."""
    return (
        f"finder = LogoFinder(logos, ratio={finder.ratio}, "
        f"min_matches={finder.min_matches}, "
        f"frame_max_side={finder.frame_max_side})"
    )


def write_status(canvas: Image, lines: list[str]) -> None:
    """White text with a black outline, readable on any background."""
    for row, line in enumerate(lines):
        origin = (12, 36 + 34 * row)
        for color, width in (((0, 0, 0), 4), ((255, 255, 255), 2)):
            cv2.putText(
                canvas,
                line,
                origin,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                color,
                width,
            )


def read_frame(
    capture: cv2.VideoCapture, is_file: bool, previous: Image | None
) -> Image | None:
    """The next image, or `None` if the source delivers none.

    A file never runs out, so you can move the sliders at leisure: a video
    starts over at its end, and a photo (a one-image video for OpenCV)
    keeps showing `previous`.
    """
    ok, frame = capture.read()
    if ok:
        return np.asarray(frame, dtype=np.uint8)
    if not is_file:
        return None
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok, frame = capture.read()
    return np.asarray(frame, dtype=np.uint8) if ok else previous


def run(capture: cv2.VideoCapture, finder: LogoFinder, is_file: bool) -> None:
    """Show the source with found logos until the user quits."""
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 1280, 800)
    add_sliders(finder)
    frame = None
    while cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) >= 1:
        frame = read_frame(capture, is_file, frame)
        if frame is None:
            print("Kein Bild von der Quelle.", file=sys.stderr)
            break
        read_sliders(finder)

        start = time.perf_counter()
        found = finder.find(frame)
        seconds = time.perf_counter() - start

        canvas = draw(frame, found)
        lines = [f"{1 / seconds:.1f} Bilder/s"]
        for name, detection in found.items():
            state = (
                f"gefunden ({detection.matches} Paare)"
                if detection
                else "nicht gefunden"
            )
            lines.append(f"{name}: {state}")
        write_status(canvas, lines)
        cv2.imshow(WINDOW, canvas)

        key = cv2.waitKey(1) & 0xFF
        if key in QUIT_KEYS:
            break
        if key == SAVE_KEY:
            print(as_code(finder))


def main(argv: list[str] | None = None) -> int:
    """Load the logos, open the source and show the window."""
    parser = argparse.ArgumentParser(
        description="Find logos in a camera image."
    )
    parser.add_argument("--logos", type=Path, default=Path("logos"))
    parser.add_argument(
        "--source", default="0", help="webcam number, file or URL"
    )
    args = parser.parse_args(argv)

    try:
        logos = load_logos(args.logos)
        finder = LogoFinder(logos)
    except (FileNotFoundError, ValueError) as error:
        print(f"Logos: {error}", file=sys.stderr)
        return 1
    print(f"{len(logos)} Logo(s): {', '.join(logos)}")

    capture = open_source(args.source)
    if not capture.isOpened():
        print(
            f"Quelle {args.source!r} lässt sich nicht öffnen.", file=sys.stderr
        )
        return 1
    try:
        run(capture, finder, is_file=Path(args.source).is_file())
    finally:
        capture.release()
        cv2.destroyAllWindows()
    return 0


def _ignore(_value: int) -> None:
    """Trackbars need a callback; the values are read in the main loop."""


if __name__ == "__main__":
    sys.exit(main())
