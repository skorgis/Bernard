from PIL import Image

from parkleitsystem.domain import ParkingLot, ParkingSpace, Side
from parkleitsystem.guide import ParkingGuide
from parkleitsystem.sign import run_sign

SIZE = (160, 128)


class RecordingDisplay:
    size = SIZE

    def __init__(self) -> None:
        self.images: list[Image.Image] = []

    def display(self, image: Image.Image) -> None:
        self.images.append(image)


class NoLeds:
    def switch(self, contact: int, on: bool) -> None:
        pass


def make_guide() -> ParkingGuide:
    lot = ParkingLot([ParkingSpace("P1", Side.LEFT, led_contact=1)])
    return ParkingGuide(lot, NoLeds(), guidance_s=10)


def stop_after(ticks: int):
    """A `wait` that lets the loop run `ticks` times, then stops it."""
    calls = 0

    def wait(timeout: float) -> bool:
        nonlocal calls
        calls += 1
        return calls >= ticks

    return wait


def test_screen_is_drawn_once_while_unchanged() -> None:
    display = RecordingDisplay()

    run_sign(make_guide(), display, wait=stop_after(5), clock=lambda: 0.0)

    assert len(display.images) == 1


def test_screen_is_redrawn_when_it_changes() -> None:
    guide = make_guide()
    display = RecordingDisplay()
    ticks = 0

    def wait(timeout: float) -> bool:
        nonlocal ticks
        ticks += 1
        if ticks == 1:
            guide.on_space_state("P1", occupied=False)
        return ticks >= 3

    run_sign(guide, display, wait=wait, clock=lambda: 0.0)

    assert len(display.images) == 2
    assert all(image.size == SIZE for image in display.images)
