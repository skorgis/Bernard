from parkleitsystem.parking import (
    CarPark,
    FreeSpaces,
    Guidance,
    NoSpace,
    Side,
    Space,
)

GUIDANCE_S = 10.0
P1 = Space("P1", Side.LEFT, led=1)
P2 = Space("P2", Side.LEFT, led=2)
P3 = Space("P3", Side.RIGHT, led=3)


class RecordingLeds:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def switch(self, led: int, on: bool) -> None:
        self.calls.append((led, on))


def make_car_park(*spaces: Space) -> tuple[CarPark, RecordingLeds]:
    leds = RecordingLeds()
    car_park = CarPark(list(spaces) or [P1, P3], leds, guidance_s=GUIDANCE_S)
    return car_park, leds


def report(car_park: CarPark, **occupied: bool) -> None:
    for name, state in occupied.items():
        car_park.space_reported(name, occupied=state)


# --- LEDs show occupancy ----------------------------------------------------


def test_led_is_on_while_space_is_occupied() -> None:
    car_park, leds = make_car_park()

    report(car_park, P1=True)
    report(car_park, P1=False)

    assert leds.calls == [(1, True), (1, False)]


def test_repeated_state_does_not_switch_led_again() -> None:
    car_park, leds = make_car_park()

    report(car_park, P3=True)
    report(car_park, P3=True)

    assert leds.calls == [(3, True)]


def test_unknown_zone_is_ignored() -> None:
    car_park, leds = make_car_park()

    report(car_park, Nebenstrasse=True)

    assert leds.calls == []


# --- Which space is recommended ---------------------------------------------


def test_side_with_most_free_spaces_is_recommended() -> None:
    car_park, leds = make_car_park(P1, P2, P3)
    report(car_park, P1=True, P2=True, P3=False)
    leds.calls.clear()

    car_park.car_entered(now=0.0)
    car_park.tick(now=0.0)

    assert leds.calls == [(3, True)]


def test_left_wins_a_tie_and_configured_order_decides() -> None:
    car_park, leds = make_car_park(P1, P2, P3)
    report(car_park, P1=True, P2=False, P3=False)
    leds.calls.clear()

    car_park.car_entered(now=0.0)
    car_park.tick(now=0.0)

    assert leds.calls == [(2, True)]


def test_space_without_report_is_never_recommended() -> None:
    car_park, leds = make_car_park()

    car_park.car_entered(now=0.0)
    car_park.tick(now=0.0)

    assert leds.calls == []


# --- Blinking ---------------------------------------------------------------


def entered_with_free_p1() -> tuple[CarPark, RecordingLeds]:
    """P1 free, P3 occupied, a car entered at t=100; LED log cleared."""
    car_park, leds = make_car_park()
    report(car_park, P1=False, P3=True)
    car_park.car_entered(now=100.0)
    leds.calls.clear()
    return car_park, leds


def test_recommended_space_blinks_every_half_second() -> None:
    car_park, leds = entered_with_free_p1()

    for now in (100.0, 100.2, 100.5, 100.7, 101.0):
        car_park.tick(now=now)

    assert leds.calls == [(1, True), (1, False), (1, True)]


def test_blinking_ends_with_the_real_state_after_guidance_time() -> None:
    car_park, leds = entered_with_free_p1()
    car_park.tick(now=100.0)

    car_park.tick(now=100.0 + GUIDANCE_S)
    car_park.tick(now=100.0 + GUIDANCE_S + 1)

    assert leds.calls == [(1, True), (1, False)]


def test_blinking_ends_when_the_car_parks_there() -> None:
    car_park, leds = entered_with_free_p1()
    car_park.tick(now=100.0)
    car_park.tick(now=100.5)

    report(car_park, P1=True)
    car_park.tick(now=101.0)
    car_park.tick(now=100.0 + GUIDANCE_S)

    assert leds.calls == [(1, True), (1, False), (1, True)]


def test_next_car_moves_the_blinking_led() -> None:
    car_park, leds = make_car_park(P1, P2, P3, Space("P4", Side.RIGHT, led=4))
    report(car_park, P1=False, P2=True, P3=True, P4=True)
    car_park.car_entered(now=100.0)
    car_park.tick(now=100.0)
    report(car_park, P3=False, P4=False)
    leds.calls.clear()

    car_park.car_entered(now=105.0)
    car_park.tick(now=105.0)

    assert leds.calls == [(1, False), (3, True)]


def test_nothing_blinks_when_car_park_is_full() -> None:
    car_park, leds = make_car_park()
    report(car_park, P1=True, P3=True)
    leds.calls.clear()

    car_park.car_entered(now=0.0)
    car_park.tick(now=0.0)

    assert leds.calls == []


# --- What the sign shows ----------------------------------------------------


def test_idle_sign_shows_free_spaces() -> None:
    car_park, _ = make_car_park()
    report(car_park, P1=False, P3=False)

    assert car_park.screen(now=0.0) == FreeSpaces(free=2)


def test_entering_car_gets_an_arrow_to_the_free_side() -> None:
    car_park, _ = make_car_park()
    report(car_park, P1=True, P3=False)

    car_park.car_entered(now=100.0)

    assert car_park.screen(now=100.0) == Guidance(side=Side.RIGHT, free=1)


def test_arrow_disappears_after_guidance_time() -> None:
    car_park, _ = make_car_park()
    report(car_park, P1=False)
    car_park.car_entered(now=100.0)

    assert car_park.screen(now=100.0 + GUIDANCE_S - 0.1) == Guidance(
        side=Side.LEFT, free=1
    )
    assert car_park.screen(now=100.0 + GUIDANCE_S) == FreeSpaces(free=1)


def test_full_car_park_shows_no_space() -> None:
    car_park, _ = make_car_park()
    report(car_park, P1=True, P3=True)
    car_park.car_entered(now=0.0)

    assert car_park.screen(now=0.0) == NoSpace()


def test_no_known_space_shows_no_space() -> None:
    car_park, _ = make_car_park()

    assert car_park.screen(now=0.0) == NoSpace()
