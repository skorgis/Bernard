from parkleitsystem.domain import ParkingLot, ParkingSpace, Side
from parkleitsystem.guide import ParkingGuide
from parkleitsystem.screens import FreeSpaces, Guidance, NoSpace

GUIDANCE_S = 10.0


class RecordingLeds:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def switch(self, contact: int, on: bool) -> None:
        self.calls.append((contact, on))


def make_guide() -> tuple[ParkingGuide, RecordingLeds]:
    lot = ParkingLot(
        [
            ParkingSpace("P1", Side.LEFT, led_contact=1),
            ParkingSpace("P2", Side.RIGHT, led_contact=2),
        ]
    )
    leds = RecordingLeds()
    return ParkingGuide(lot, leds, guidance_s=GUIDANCE_S), leds


def test_led_is_on_while_space_is_occupied() -> None:
    guide, leds = make_guide()

    guide.on_space_state("P1", occupied=True)
    guide.on_space_state("P1", occupied=False)

    assert leds.calls == [(1, True), (1, False)]


def test_repeated_state_does_not_switch_led_again() -> None:
    guide, leds = make_guide()

    guide.on_space_state("P2", occupied=True)
    guide.on_space_state("P2", occupied=True)

    assert leds.calls == [(2, True)]


def test_idle_screen_shows_free_spaces() -> None:
    guide, _ = make_guide()
    guide.on_space_state("P1", occupied=False)
    guide.on_space_state("P2", occupied=False)

    assert guide.screen(now=0.0) == FreeSpaces(free=2)


def test_entering_vehicle_gets_an_arrow_to_the_free_side() -> None:
    guide, _ = make_guide()
    guide.on_space_state("P1", occupied=True)
    guide.on_space_state("P2", occupied=False)

    guide.on_vehicle_entered(now=100.0)

    assert guide.screen(now=100.0) == Guidance(side=Side.RIGHT, free=1)


def test_arrow_disappears_after_guidance_time() -> None:
    guide, _ = make_guide()
    guide.on_space_state("P1", occupied=False)
    guide.on_vehicle_entered(now=100.0)

    assert guide.screen(now=100.0 + GUIDANCE_S - 0.1) == Guidance(
        side=Side.LEFT, free=1
    )
    assert guide.screen(now=100.0 + GUIDANCE_S) == FreeSpaces(free=1)


def test_arrow_follows_occupancy_changes_while_shown() -> None:
    guide, _ = make_guide()
    guide.on_space_state("P1", occupied=False)
    guide.on_space_state("P2", occupied=True)
    guide.on_vehicle_entered(now=0.0)

    guide.on_space_state("P1", occupied=True)
    guide.on_space_state("P2", occupied=False)

    assert guide.screen(now=1.0) == Guidance(side=Side.RIGHT, free=1)


def test_full_car_park_shows_no_space() -> None:
    guide, _ = make_guide()
    guide.on_space_state("P1", occupied=True)
    guide.on_space_state("P2", occupied=True)
    guide.on_vehicle_entered(now=0.0)

    assert guide.screen(now=0.0) == NoSpace()
    assert guide.screen(now=GUIDANCE_S + 1) == NoSpace()


def test_no_known_space_shows_no_space() -> None:
    guide, _ = make_guide()

    assert guide.screen(now=0.0) == NoSpace()


def entered_with_free_p1() -> tuple[ParkingGuide, RecordingLeds]:
    """P1 free, P2 occupied, a car entered at t=100; LED log cleared."""
    guide, leds = make_guide()
    guide.on_space_state("P1", occupied=False)
    guide.on_space_state("P2", occupied=True)
    guide.on_vehicle_entered(now=100.0)
    leds.calls.clear()
    return guide, leds


def test_recommended_space_blinks_after_entry() -> None:
    guide, leds = entered_with_free_p1()

    for now in (100.0, 100.2, 100.5, 100.7, 101.0):
        guide.tick(now=now)

    assert leds.calls == [(1, True), (1, False), (1, True)]


def test_blinking_ends_with_the_real_state_after_guidance_time() -> None:
    guide, leds = entered_with_free_p1()
    guide.tick(now=100.0)

    guide.tick(now=100.0 + GUIDANCE_S)
    guide.tick(now=100.0 + GUIDANCE_S + 1)

    assert leds.calls == [(1, True), (1, False)]


def test_blinking_ends_when_recommended_space_gets_occupied() -> None:
    guide, leds = entered_with_free_p1()
    guide.tick(now=100.0)
    guide.tick(now=100.5)

    guide.on_space_state("P1", occupied=True)
    guide.tick(now=101.0)
    guide.tick(now=100.0 + GUIDANCE_S)

    assert leds.calls == [(1, True), (1, False), (1, True)]


def test_nothing_blinks_when_car_park_is_full() -> None:
    guide, leds = make_guide()
    guide.on_space_state("P1", occupied=True)
    guide.on_space_state("P2", occupied=True)
    leds.calls.clear()

    guide.on_vehicle_entered(now=0.0)
    guide.tick(now=0.0)

    assert leds.calls == []


def test_next_entry_moves_recommendation_and_restores_old_led() -> None:
    lot = ParkingLot(
        [
            ParkingSpace("P1", Side.LEFT, led_contact=1),
            ParkingSpace("P2", Side.RIGHT, led_contact=2),
            ParkingSpace("P3", Side.RIGHT, led_contact=3),
        ]
    )
    leds = RecordingLeds()
    guide = ParkingGuide(lot, leds, guidance_s=GUIDANCE_S)
    guide.on_space_state("P1", occupied=False)
    guide.on_vehicle_entered(now=100.0)
    guide.tick(now=100.0)
    guide.on_space_state("P2", occupied=False)
    guide.on_space_state("P3", occupied=False)
    leds.calls.clear()

    guide.on_vehicle_entered(now=105.0)
    guide.tick(now=105.0)

    assert leds.calls == [(1, False), (2, True)]


def make_green_guide() -> tuple[ParkingGuide, RecordingLeds]:
    """Green LEDs: lit while the space is free."""
    lot = ParkingLot([ParkingSpace("P1", Side.LEFT, led_contact=1)])
    leds = RecordingLeds()
    guide = ParkingGuide(lot, leds, guidance_s=GUIDANCE_S, lit_when_free=True)
    return guide, leds


def test_green_led_is_on_while_space_is_free() -> None:
    guide, leds = make_green_guide()

    guide.on_space_state("P1", occupied=True)
    guide.on_space_state("P1", occupied=False)

    assert leds.calls == [(1, False), (1, True)]


def test_green_blink_starts_dark_and_ends_lit() -> None:
    guide, leds = make_green_guide()
    guide.on_space_state("P1", occupied=False)
    guide.on_vehicle_entered(now=100.0)
    leds.calls.clear()

    for now in (100.0, 100.5, 101.0, 100.0 + GUIDANCE_S):
        guide.tick(now=now)

    assert leds.calls == [(1, False), (1, True), (1, False), (1, True)]


def test_green_led_goes_dark_when_recommended_space_gets_occupied() -> None:
    guide, leds = make_green_guide()
    guide.on_space_state("P1", occupied=False)
    guide.on_vehicle_entered(now=100.0)
    guide.tick(now=100.5)
    leds.calls.clear()

    guide.on_space_state("P1", occupied=True)
    guide.tick(now=101.0)

    assert leds.calls == [(1, False)]
