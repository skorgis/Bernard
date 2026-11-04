"""Draw a `Screen` as a full-screen image for the 160x128 TFT."""

from PIL import Image, ImageDraw, ImageFont

from parkleitsystem.domain import Side
from parkleitsystem.screens import FreeSpaces, Guidance, NoSpace, Screen

type Colour = tuple[int, int, int]
type Box = tuple[int, int, int, int]

BLACK: Colour = (0, 0, 0)
WHITE: Colour = (255, 255, 255)
GREEN: Colour = (0, 200, 0)
RED: Colour = (230, 0, 0)
SIGN_BLUE: Colour = (0, 90, 200)  # blue of the Austrian/German "P" sign

TEXT_HEIGHT = 40  # bottom strip for the free count, in pixels
TEXT_SIZE = 30  # font size in pixels; "10 frei" still fits 160 px
MARGIN = 6
CROSS_LINE_WIDTH = 12


def render(screen: Screen, size: tuple[int, int]) -> Image.Image:
    """Draw `screen` on a black image of `size` (width, height)."""
    image = Image.new("RGB", size, BLACK)
    draw = ImageDraw.Draw(image)
    width, height = size
    symbol: Box = (0, 0, width, height - TEXT_HEIGHT)
    match screen:
        case Guidance(side=side, free=free):
            _arrow(draw, symbol, side)
            _caption(draw, size, f"{free} frei")
        case FreeSpaces(free=free):
            _parking_sign(draw, symbol)
            _caption(draw, size, f"{free} frei")
        case NoSpace():
            _cross(draw, symbol)
            _caption(draw, size, "voll")
    return image


def _arrow(draw: ImageDraw.ImageDraw, box: Box, side: Side) -> None:
    left, top, right, bottom = _inset(box)
    middle = (top + bottom) // 2
    head_length = (right - left) // 3
    shaft_half = (bottom - top) // 6
    neck = right - head_length
    # Outline of an arrow pointing right, clockwise from the shaft's end.
    points = [
        (left, middle - shaft_half),
        (neck, middle - shaft_half),
        (neck, top),
        (right, middle),
        (neck, bottom),
        (neck, middle + shaft_half),
        (left, middle + shaft_half),
    ]
    if side is Side.LEFT:
        points = [(left + right - x, y) for x, y in points]
    draw.polygon(points, fill=GREEN)


def _cross(draw: ImageDraw.ImageDraw, box: Box) -> None:
    left, top, right, bottom = _centred_square(_inset(box))
    draw.line((left, top, right, bottom), fill=RED, width=CROSS_LINE_WIDTH)
    draw.line((left, bottom, right, top), fill=RED, width=CROSS_LINE_WIDTH)


def _parking_sign(draw: ImageDraw.ImageDraw, box: Box) -> None:
    square = _centred_square(_inset(box))
    draw.rounded_rectangle(square, radius=8, fill=SIGN_BLUE)
    left, top, right, bottom = square
    draw.text(
        ((left + right) // 2, (top + bottom) // 2),
        "P",
        fill=WHITE,
        font=ImageFont.load_default(int((bottom - top) * 0.8)),
        anchor="mm",  # anchor the glyph's middle at the given point
    )


def _caption(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], text: str
) -> None:
    width, height = size
    draw.text(
        (width // 2, height - TEXT_HEIGHT // 2),
        text,
        fill=WHITE,
        font=ImageFont.load_default(TEXT_SIZE),
        anchor="mm",
    )


def _inset(box: Box) -> Box:
    left, top, right, bottom = box
    return left + MARGIN, top + MARGIN, right - MARGIN, bottom - MARGIN


def _centred_square(box: Box) -> Box:
    left, top, right, bottom = box
    half = min(right - left, bottom - top) // 2
    centre_x, centre_y = (left + right) // 2, (top + bottom) // 2
    return centre_x - half, centre_y - half, centre_x + half, centre_y + half
