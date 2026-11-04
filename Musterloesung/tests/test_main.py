from parkleitsystem.main import run_loop
from parkleitsystem.parking import CarPark, FreeSpaces, Screen, Side, Space


class RecordingLeds:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def switch(self, led: int, on: bool) -> None:
        self.calls.append((led, on))


class RecordingSign:
    def __init__(self) -> None:
        self.screens: list[Screen] = []

    def show(self, screen: Screen) -> None:
        self.screens.append(screen)


def stop_after(rounds: int):
    """A `wait` that lets the loop run `rounds` times, then stops it."""
    calls = 0

    def wait(timeout: float) -> bool:
        nonlocal calls
        calls += 1
        return calls >= rounds

    return wait


def car_park_with_free_p1() -> tuple[CarPark, RecordingLeds]:
    leds = RecordingLeds()
    car_park = CarPark([Space("P1", Side.LEFT, led=1)], leds, guidance_s=10)
    car_park.space_reported("P1", occupied=False)
    leds.calls.clear()
    return car_park, leds


def test_loop_blinks_without_a_sign() -> None:
    car_park, leds = car_park_with_free_p1()
    car_park.car_entered(now=0.0)
    times = iter([0.0, 0.5, 1.0])

    run_loop(car_park, None, wait=stop_after(3), clock=lambda: next(times))

    assert leds.calls == [(1, True), (1, False), (1, True)]


def test_loop_shows_the_current_screen_on_the_sign() -> None:
    car_park, _ = car_park_with_free_p1()
    sign = RecordingSign()

    run_loop(car_park, sign, wait=stop_after(2), clock=lambda: 0.0)

    assert sign.screens == [FreeSpaces(free=1), FreeSpaces(free=1)]
