import json
from typing import Any

import pytest
from detection_worker.data import parse_event
from detection_worker.dispatch import EventDispatcher

from parkleitsystem.config import EntrySettings
from parkleitsystem.domain import ParkingLot, ParkingSpace, Side
from parkleitsystem.events import handle_payload, register_handlers
from parkleitsystem.guide import ParkingGuide
from parkleitsystem.screens import FreeSpaces, Guidance

TOPIC = "bma/events"
NOW = 50.0


class RecordingLeds:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def switch(self, contact: int, on: bool) -> None:
        self.calls.append((contact, on))


def envelope(**sub_event: Any) -> dict[str, Any]:
    return {
        "uuid": "e-1",
        "version": "6.0",
        "eventSchema": "https://docs.bernard-gruppe.com/events/schema/6.0",
        "node": {"id": "bma-1", "name": "G-A2610-0007"},
        "stream": {"id": "s-1", "name": ""},
        **sub_event,
    }


def roi(name: str, state: str) -> dict[str, Any]:
    return envelope(
        regionOfInterestEvent={
            "roiId": f"id-{name}",
            "roiName": name,
            "triggerType": "change",
            "timestamp": "2026-11-02T09:30:00Z",
            "state": state,
            "objects": [],
        }
    )


def crossing(
    line: str = "Einfahrt", direction: str = "in", cls: str = "car"
) -> dict[str, Any]:
    return envelope(
        crossingLineEvent={
            "class": cls,
            "lineId": "line-1",
            "lineName": line,
            "direction": direction,
            "timestamp": "2026-11-02T09:30:00Z",
        }
    )


def setup(
    entry: EntrySettings | None = None,
) -> tuple[EventDispatcher, ParkingGuide, RecordingLeds]:
    lot = ParkingLot(
        [
            ParkingSpace("P1", Side.LEFT, led_contact=1),
            ParkingSpace("P2", Side.RIGHT, led_contact=2),
        ]
    )
    leds = RecordingLeds()
    guide = ParkingGuide(lot, leds, guidance_s=10)
    dispatcher = EventDispatcher()
    register_handlers(
        dispatcher,
        topic=TOPIC,
        entry=entry or EntrySettings(line_name="Einfahrt"),
        space_names=["P1", "P2"],
        guide=guide,
        clock=lambda: NOW,
    )
    return dispatcher, guide, leds


def deliver(dispatcher: EventDispatcher, payload: dict[str, Any]) -> None:
    dispatcher.dispatch(TOPIC, parse_event(payload))


def test_zone_states_switch_leds() -> None:
    dispatcher, _, leds = setup()

    deliver(dispatcher, roi("P1", "occupied"))
    deliver(dispatcher, roi("P2", "vacant"))

    assert leds.calls == [(1, True), (2, False)]


def test_unconfigured_zone_is_ignored() -> None:
    dispatcher, _, leds = setup()

    deliver(dispatcher, roi("Nebenstraße", "occupied"))

    assert leds.calls == []


def test_entering_car_triggers_guidance() -> None:
    dispatcher, guide, _ = setup()
    deliver(dispatcher, roi("P2", "vacant"))

    deliver(dispatcher, crossing())

    assert guide.screen(now=NOW) == Guidance(side=Side.RIGHT, free=1)


def test_leaving_car_does_not_trigger_guidance() -> None:
    dispatcher, guide, _ = setup()
    deliver(dispatcher, roi("P2", "vacant"))

    deliver(dispatcher, crossing(direction="out"))

    assert guide.screen(now=NOW) == FreeSpaces(free=1)


def test_other_line_does_not_trigger_guidance() -> None:
    dispatcher, guide, _ = setup()
    deliver(dispatcher, roi("P2", "vacant"))

    deliver(dispatcher, crossing(line="Ausfahrt"))

    assert guide.screen(now=NOW) == FreeSpaces(free=1)


def test_vehicle_class_filter() -> None:
    entry = EntrySettings(line_name="Einfahrt", vehicle_classes=["car"])
    dispatcher, guide, _ = setup(entry)
    deliver(dispatcher, roi("P2", "vacant"))

    deliver(dispatcher, crossing(cls="person"))
    assert guide.screen(now=NOW) == FreeSpaces(free=1)

    deliver(dispatcher, crossing(cls="car"))
    assert guide.screen(now=NOW) == Guidance(side=Side.RIGHT, free=1)


def test_payload_is_parsed_and_dispatched() -> None:
    dispatcher, _, leds = setup()

    handle_payload(
        dispatcher, TOPIC, json.dumps(roi("P1", "occupied")).encode()
    )

    assert leds.calls == [(1, True)]


def test_invalid_payload_is_logged_and_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dispatcher, _, leds = setup()

    handle_payload(dispatcher, TOPIC, b"not json")
    handle_payload(dispatcher, TOPIC, b'{"version": "6.0"}')

    assert leds.calls == []
    assert caplog.text.count("skipping invalid event") == 2
