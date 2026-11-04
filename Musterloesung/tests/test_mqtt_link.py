import json
import zlib
from typing import Any

import pytest

from parkleitsystem.mqtt_link import forward_message
from parkleitsystem.parking import CarPark, FreeSpaces, Guidance, Side, Space

ENTRY_LINE = "Einfahrt"


class RecordingLeds:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def switch(self, led: int, on: bool) -> None:
        self.calls.append((led, on))


def make_car_park() -> tuple[CarPark, RecordingLeds]:
    leds = RecordingLeds()
    spaces = [Space("P1", Side.LEFT, led=1), Space("P2", Side.RIGHT, led=2)]
    return CarPark(spaces, leds, guidance_s=10), leds


def message(**sub_event: Any) -> bytes:
    """An event as the BMA sends it (schema 6.0), as raw MQTT payload."""
    event = {
        "uuid": "e-1",
        "version": "6.0",
        "eventSchema": "https://docs.bernard-gruppe.com/events/schema/6.0",
        "node": {"id": "bma-1", "name": "G-A2610-0007"},
        "stream": {"id": "s-1", "name": ""},
        **sub_event,
    }
    return json.dumps(event).encode()


def zone(name: str, state: str) -> bytes:
    return message(
        regionOfInterestEvent={
            "roiId": f"id-{name}",
            "roiName": name,
            "triggerType": "change",
            "timestamp": "2026-11-02T09:30:00Z",
            "state": state,
            "objects": [],
        }
    )


def crossing(line: str = ENTRY_LINE, direction: str = "in") -> bytes:
    return message(
        crossingLineEvent={
            "class": "car",
            "lineId": "line-1",
            "lineName": line,
            "direction": direction,
            "timestamp": "2026-11-02T09:30:00Z",
        }
    )


def forward(car_park: CarPark, payload: bytes) -> None:
    forward_message(payload, car_park, entry_line=ENTRY_LINE, now=50.0)


# --- Events in --------------------------------------------------------------


def test_zone_states_switch_leds() -> None:
    car_park, leds = make_car_park()

    forward(car_park, zone("P1", "occupied"))
    forward(car_park, zone("P2", "vacant"))

    assert leds.calls == [(1, True), (2, False)]


def test_compressed_events_are_unpacked() -> None:
    # The BMA can send events zlib-compressed (seen on 2026-11-04).
    car_park, leds = make_car_park()

    forward(car_park, zlib.compress(zone("P1", "occupied")))

    assert leds.calls == [(1, True)]


def test_zone_with_unknown_state_is_ignored() -> None:
    car_park, leds = make_car_park()

    forward(car_park, zone("P1", "unknown"))

    assert leds.calls == []


def test_car_driving_in_gets_guidance() -> None:
    car_park, _ = make_car_park()
    forward(car_park, zone("P2", "vacant"))

    forward(car_park, crossing())

    assert car_park.screen(now=50.0) == Guidance(side=Side.RIGHT, free=1)


@pytest.mark.parametrize(
    "payload",
    [crossing(direction="out"), crossing(line="Ausfahrt")],
    ids=["driving out", "other line"],
)
def test_other_crossings_get_no_guidance(payload: bytes) -> None:
    car_park, _ = make_car_park()
    forward(car_park, zone("P2", "vacant"))

    forward(car_park, payload)

    assert car_park.screen(now=50.0) == FreeSpaces(free=1)


def test_invalid_messages_are_logged_and_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    car_park, leds = make_car_park()

    forward(car_park, b"not json")
    forward(car_park, b'{"version": "6.0"}')

    assert leds.calls == []
    assert caplog.text.count("skipping invalid event") == 2
