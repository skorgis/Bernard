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
