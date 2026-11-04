"""Show test images on the Joy-IT RB-TFT1.8 display (or as PNG files).

On the Raspberry Pi, with SPI enabled (see doc/tft-display.md):

    uv sync --extra pi
    uv run python examples/tft_display_demo.py

Without a display, e.g. on a laptop, write PNG files instead:

    uv run python examples/tft_display_demo.py --preview tmp/tft

The first image is a test pattern: the bars must read red, green, blue,
white from left to right (otherwise add --bgr) and the white frame must be
visible on all four edges (otherwise adjust --x-offset/--y-offset).
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tft_display import PngPreview, TftConfig, open_tft

logger = logging.getLogger(__name__)

RED = (255, 0, 0)
GREEN = (0, 200, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
SECONDS_PER_IMAGE = 3.0

type Painter = Callable[[ImageDraw.ImageDraw, int, int], None]


def test_pattern(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Four colour bars inside a one-pixel white frame."""
    colours = (RED, GREEN, BLUE, WHITE)
    bar = width // len(colours)
    for index, colour in enumerate(colours):
        draw.rectangle(
            (index * bar, 0, (index + 1) * bar - 1, height - 1), fill=colour
        )
    draw.rectangle((0, 0, width - 1, height - 1), outline=WHITE)
    draw.text((4, 4), "R G B W", fill=BLACK, font=ImageFont.load_default(14))


def arrow_left(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """A green arrow pointing left."""
    _arrow(draw, width, height, point_left=True)


def arrow_right(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """A green arrow pointing right."""
    _arrow(draw, width, height, point_left=False)


def _arrow(
    draw: ImageDraw.ImageDraw, width: int, height: int, *, point_left: bool
) -> None:
    middle = height // 2
    head = width // 3
    shaft = height // 6
    # Drawn pointing right, mirrored for left.
    points = [
        (10, middle - shaft),
        (width - 10 - head, middle - shaft),
        (width - 10 - head, 10),
        (width - 10, middle),
        (width - 10 - head, height - 10),
        (width - 10 - head, middle + shaft),
        (10, middle + shaft),
    ]
    if point_left:
        points = [(width - 1 - x, y) for x, y in points]
    draw.polygon(points, fill=GREEN)


def cross(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """A thick red X."""
    margin = 20
    left, right = (width - height) // 2 + margin, (width + height) // 2 - margin
    top, bottom = margin, height - margin
    draw.line((left, top, right, bottom), fill=RED, width=14)
    draw.line((left, bottom, right, top), fill=RED, width=14)


def text(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Centred text in Pillow's built-in font."""
    draw.text(
        (width // 2, height // 2),
        "3 frei",
        fill=WHITE,
        font=ImageFont.load_default(40),
        anchor="mm",  # anchor the text's middle at the given point
    )


PAINTERS: dict[str, Painter] = {
    "test": test_pattern,
    "left": arrow_left,
    "right": arrow_right,
    "cross": cross,
    "text": text,
}


def render(painter: Painter, size: tuple[int, int]) -> Image.Image:
    """Paint one full-screen image of `size` on a black background."""
    image = Image.new("RGB", size, BLACK)
    painter(ImageDraw.Draw(image), *size)
    return image


def write_previews(names: list[str], directory: Path) -> None:
    """Save each image as `<directory>/<name>.png`, for use without a TFT."""
    directory.mkdir(parents=True, exist_ok=True)
    size = TftConfig().size
    for name in names:
        PngPreview(directory / f"{name}.png", size=size).display(
            render(PAINTERS[name], size)
        )


def show_on_tft(names: list[str], config: TftConfig) -> None:
    """Show each image on the TFT for a few seconds."""
    with open_tft(config) as tft:
        for name in names:
            logger.info("showing %s", name)
            tft.display(render(PAINTERS[name], tft.size))
            time.sleep(SECONDS_PER_IMAGE)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Show test images on the RB-TFT1.8 or as PNG files."
    )
    parser.add_argument(
        "images",
        nargs="*",
        help=f"images to show, in order: {', '.join(PAINTERS)} (default: all)",
    )
    parser.add_argument(
        "--rotation", type=int, default=0, help="0 = landscape, 160x128"
    )
    parser.add_argument("--x-offset", type=int, default=0)
    parser.add_argument("--y-offset", type=int, default=0)
    parser.add_argument(
        "--bgr", action="store_true", help="if red and blue are swapped"
    )
    parser.add_argument(
        "--preview",
        type=Path,
        help="directory to write PNG files to instead of using the TFT",
    )
    args = parser.parse_args(argv)
    unknown = [name for name in args.images if name not in PAINTERS]
    if unknown:
        parser.error(f"unknown image(s): {', '.join(unknown)}")
    return args


def main(argv: list[str] | None = None) -> int:
    """Show the requested images on the TFT or write them as PNG."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    names = args.images or list(PAINTERS)
    if args.preview is not None:
        write_previews(names, args.preview)
        return 0
    show_on_tft(
        names,
        TftConfig(
            rotation=args.rotation,
            x_offset=args.x_offset,
            y_offset=args.y_offset,
            bgr=args.bgr,
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
