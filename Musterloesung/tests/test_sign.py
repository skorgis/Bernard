from PIL import Image

from parkleitsystem.domain import Side
from parkleitsystem.screens import FreeSpaces, Guidance
from parkleitsystem.sign import Sign

SIZE = (160, 128)


class RecordingDisplay:
    size = SIZE

    def __init__(self) -> None:
        self.images: list[Image.Image] = []

    def display(self, image: Image.Image) -> None:
        self.images.append(image)


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
    assert all(image.size == SIZE for image in display.images)
