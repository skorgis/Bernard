from parkleitsystem.domain import ParkingLot, ParkingSpace, Side
from parkleitsystem.guide import ParkingGuide
from parkleitsystem.main_loop import run_main_loop
from parkleitsystem.screens import FreeSpaces, Screen


class RecordingLeds:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def switch(self, contact: int, on: bool) -> None:
        self.calls.append((contact, on))


class RecordingSign:
    def __init__(self) -> None:
        self.screens: list[Screen] = []

    def show(self, screen: Screen) -> None:
        self.screens.append(screen)


def stop_after(ticks: int):
    """A `wait` that lets the loop run `ticks` times, then stops it."""
    calls = 0

    def wait(timeout: float) -> bool:
        nonlocal calls
        calls += 1
        return calls >= ticks

    return wait


def guide_with_free_p1() -> tuple[ParkingGuide, RecordingLeds]:
    leds = RecordingLeds()
    lot = ParkingLot([ParkingSpace("P1", Side.LEFT, led_contact=1)])
    guide = ParkingGuide(lot, leds, guidance_s=10)
    guide.on_space_state("P1", occupied=False)
    leds.calls.clear()
    return guide, leds


def test_loop_blinks_without_a_sign() -> None:
    guide, leds = guide_with_free_p1()
    guide.on_vehicle_entered(now=0.0)
    times = iter([0.0, 0.5, 1.0])

    run_main_loop(guide, None, wait=stop_after(3), clock=lambda: next(times))

    assert leds.calls == [(1, True), (1, False), (1, True)]


def test_loop_shows_the_current_screen_on_the_sign() -> None:
    guide, _ = guide_with_free_p1()
    sign = RecordingSign()

    run_main_loop(guide, sign, wait=stop_after(2), clock=lambda: 0.0)

    assert sign.screens == [FreeSpaces(free=1), FreeSpaces(free=1)]
