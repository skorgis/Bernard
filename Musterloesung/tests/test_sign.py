from PIL import Image

from parkleitsystem.parking import FreeSpaces, Guidance, NoSpace, Side
from parkleitsystem.sign import GREEN, RED, WHITE, Sign, render

SIZE = (160, 128)
WIDTH, HEIGHT = SIZE
SYMBOL_MIDDLE = 44  # vertical centre of the symbol area above the text


def colour_count(image: Image.Image, colour: tuple[int, int, int]) -> int:
    return sum(1 for pixel in image.get_flattened_data() if pixel == colour)


class RecordingDisplay:
    size = SIZE

    def __init__(self) -> None:
        self.images: list[Image.Image] = []

    def display(self, image: Image.Image) -> None:
        self.images.append(image)


# --- Drawing ----------------------------------------------------------------


def test_image_matches_display_size() -> None:
    assert render(FreeSpaces(free=3), SIZE).size == SIZE


def test_left_arrow_tip_is_at_the_left_edge() -> None:
    image = render(Guidance(side=Side.LEFT, free=1), SIZE)

    assert image.getpixel((12, SYMBOL_MIDDLE)) == GREEN
    assert image.getpixel((WIDTH - 12, SYMBOL_MIDDLE + 20)) != GREEN


def test_right_arrow_tip_is_at_the_right_edge() -> None:
    image = render(Guidance(side=Side.RIGHT, free=1), SIZE)

    assert image.getpixel((WIDTH - 12, SYMBOL_MIDDLE)) == GREEN
    assert image.getpixel((12, SYMBOL_MIDDLE + 20)) != GREEN


def test_no_space_shows_a_red_cross_in_the_centre() -> None:
    image = render(NoSpace(), SIZE)

    assert image.getpixel((WIDTH // 2, SYMBOL_MIDDLE)) == RED
    assert colour_count(image, GREEN) == 0


def test_free_count_is_written_below_the_symbol() -> None:
    image = render(FreeSpaces(free=3), SIZE)
    text_area = image.crop((0, HEIGHT - 36, WIDTH, HEIGHT))

    assert colour_count(text_area, WHITE) > 0


def test_idle_screen_has_no_arrow() -> None:
    assert colour_count(render(FreeSpaces(free=2), SIZE), GREEN) == 0


# --- Redrawing only on change -----------------------------------------------


def test_screen_is_drawn_once_while_unchanged() -> None:
    display = RecordingDisplay()
    sign = Sign(display)

    for _ in range(5):
        sign.show(FreeSpaces(free=1))

    assert len(display.images) == 1


def test_screen_is_redrawn_when_it_changes() -> None:
    display = RecordingDisplay()
    sign = Sign(display)

    sign.show(FreeSpaces(free=1))
    sign.show(Guidance(side=Side.LEFT, free=1))

    assert len(display.images) == 2
