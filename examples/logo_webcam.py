"""Find the logos from a folder in a webcam stream, and tune the pipeline live.

Put one image per logo into `logos/` (PNG with transparency is fine), then:

    uv run python examples/logo_webcam.py

With several cameras, pick one in the "Quelle" dropdown. Without a camera,
or to tune on a recording, pass an image or video file:

    uv run python examples/logo_webcam.py --source recording.mp4

"Einstellungen speichern" writes the settings to `logo_tuner_settings.json`
(loaded again on the next start) and prints the matching Python code.
"""

import argparse
import sys
from pathlib import Path

from picture_pipeline.cameras import list_cameras
from picture_pipeline.frame_sources import source_options
from picture_pipeline.gui import run_tuner
from picture_pipeline.logo_loading import load_logos


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Find logos from a folder in a webcam stream."
    )
    parser.add_argument(
        "--logos",
        type=Path,
        default=Path("logos"),
        help="Folder with one image per logo (default: logos).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Image or video file to use instead of / besides the cameras.",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("logo_tuner_settings.json"),
        help="Where tuned settings are loaded from and saved to.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Load the logos, find the cameras and open the tuner window."""
    args = parse_args(argv)
    try:
        logos = load_logos(args.logos)
    except (FileNotFoundError, ValueError) as error:
        print(f"Keine Logos: {error}", file=sys.stderr)
        return 1
    print(f"{len(logos)} Logo(s) geladen: {', '.join(logos)}")

    cameras = list_cameras()
    print("Kameras:", ", ".join(map(str, cameras)) or "keine")
    sources = source_options(cameras, args.source)
    if not sources:
        print(
            "Keine Kamera gefunden. Mit --source ein Bild oder Video angeben.",
            file=sys.stderr,
        )
        return 1

    run_tuner(logos, sources, args.settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
