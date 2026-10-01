"""Tests for `EventDispatcher`: routing sub-events to typed handlers."""

import pytest

from detection_worker.data import (
    CrossingLineEvent,
    Event,
    HeatmapEvent,
    Node,
    OriginDestinationEvent,
    ParkingEvent,
    ParkingSummaryEntry,
    PathPoint,
    RuleEvent,
    Stream,
    VirtualDoorEvent,
    VirtualDoorObject,
    Zone,
    ZoneCrossing,
)
from detection_worker.dispatch import EventDispatcher, HandlerKey

TOPIC = "site1/bma/events"
TS = "2026-10-01T12:00:00+00:00"


def _event(**sub_event: object) -> Event:
    return Event(
        uuid="e1",
        version="6.0",
        eventSchema="6.0",
        node=Node(id="n1", name="cam"),
        stream=Stream(id="s1", name="lane"),
        **sub_event,  # type: ignore[arg-type]
    )


def _crossing(line_name: str) -> CrossingLineEvent:
    return CrossingLineEvent(
        class_="car",
        lineId="l1",
        lineName=line_name,
        direction="in",
        timestamp=TS,
    )


def _door(door_name: str) -> VirtualDoorEvent:
    return VirtualDoorEvent(
        virtualDoorId="d1",
        virtualDoorName=door_name,
        direction="out",
        timestamp=TS,
        object=VirtualDoorObject(class_="person"),
    )


def _origin_destination(entry: str, exit_: str) -> OriginDestinationEvent:
    return OriginDestinationEvent(
        classification="car",
        entry=ZoneCrossing(zone=Zone(zoneId="z1", name=entry), timestamp=TS),
        exit=ZoneCrossing(zone=Zone(zoneId="z2", name=exit_), timestamp=TS),
        movementPath=[],
        trackId=1,
    )


def test_dispatches_to_handler_with_matching_key() -> None:
    """A sub-event reaches the handler registered for its exact key."""
    received: list[tuple[Event, VirtualDoorEvent]] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, "door-1", VirtualDoorEvent),
        lambda event, door: received.append((event, door)),
    )
    event = _event(virtualDoorEvent=_door("door-1"))

    dispatcher.dispatch(TOPIC, event)

    assert received == [(event, event.virtualDoorEvent)]


@pytest.mark.parametrize(
    ("topic", "event"),
    [
        ("other/topic", _event(virtualDoorEvent=_door("door-1"))),
        (TOPIC, _event(virtualDoorEvent=_door("door-2"))),
        (TOPIC, _event(crossingLineEvent=_crossing("door-1"))),
    ],
    ids=["wrong-topic", "wrong-name", "wrong-type"],
)
def test_ignores_event_not_matching_key(topic: str, event: Event) -> None:
    """Topic, name and event type must all match the key."""
    received: list[VirtualDoorEvent] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, "door-1", VirtualDoorEvent),
        lambda _event, door: received.append(door),
    )

    dispatcher.dispatch(topic, event)

    assert received == []


def test_none_name_matches_any_name() -> None:
    """A key with `name=None` receives that type regardless of its name."""
    received: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, None, CrossingLineEvent),
        lambda _event, line: received.append(line.lineName),
    )

    dispatcher.dispatch(TOPIC, _event(crossingLineEvent=_crossing("a")))
    dispatcher.dispatch(TOPIC, _event(crossingLineEvent=_crossing("b")))

    assert received == ["a", "b"]


def test_named_and_wildcard_handlers_both_receive_event() -> None:
    """A named key and a `name=None` key on the same type both fire."""
    received: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, "a", CrossingLineEvent),
        lambda _event, _line: received.append("named"),
    )
    dispatcher.add_handler(
        HandlerKey(TOPIC, None, CrossingLineEvent),
        lambda _event, _line: received.append("any"),
    )

    dispatcher.dispatch(TOPIC, _event(crossingLineEvent=_crossing("a")))

    assert sorted(received) == ["any", "named"]


def test_heatmap_event_is_dispatched_by_wildcard_key() -> None:
    """Heatmap events have no name, so only `name=None` keys match them."""
    received: list[HeatmapEvent] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, None, HeatmapEvent),
        lambda _event, heatmap: received.append(heatmap),
    )
    heatmap = HeatmapEvent(
        class_="car", path=[PathPoint(x=0, y=0, w=1, h=1, timestamp=TS)]
    )

    dispatcher.dispatch(TOPIC, _event(heatmapEvent=heatmap))

    assert received == [heatmap]


@pytest.mark.parametrize("zone_name", ["entry-zone", "exit-zone"])
def test_origin_destination_matches_entry_or_exit_zone(zone_name: str) -> None:
    """An origin/destination event matches on either of its zone names."""
    received: list[OriginDestinationEvent] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, zone_name, OriginDestinationEvent),
        lambda _event, od: received.append(od),
    )
    od = _origin_destination("entry-zone", "exit-zone")

    dispatcher.dispatch(TOPIC, _event(originDestinationEvent=od))

    assert received == [od]


def test_origin_destination_with_same_entry_and_exit_fires_once() -> None:
    """Entry and exit in the same zone don't call the handler twice."""
    received: list[OriginDestinationEvent] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, "zone", OriginDestinationEvent),
        lambda _event, od: received.append(od),
    )

    dispatcher.dispatch(
        TOPIC,
        _event(originDestinationEvent=_origin_destination("zone", "zone")),
    )

    assert len(received) == 1


def test_parking_matches_any_summary_roi() -> None:
    """A parking event matches the name of any ROI in its summary."""
    received: list[ParkingEvent] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, "lot-b", ParkingEvent),
        lambda _event, parking: received.append(parking),
    )
    parking = ParkingEvent(
        timestamp=TS,
        parkingSummary=[
            ParkingSummaryEntry(
                roiId="r1", roiName="lot-a", capacity=10, vehicles=1
            ),
            ParkingSummaryEntry(
                roiId="r2", roiName="lot-b", capacity=10, vehicles=2
            ),
        ],
    )

    dispatcher.dispatch(TOPIC, _event(parkingEvent=parking))

    assert received == [parking]


def test_dispatches_sub_events_inside_rule_events() -> None:
    """Each sub-event nested in `ruleEvents` is dispatched too."""
    received: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(TOPIC, None, CrossingLineEvent),
        lambda _event, line: received.append(line.lineName),
    )
    event = _event(
        ruleEvents=[
            RuleEvent(crossingLineEvent=_crossing("a")),
            RuleEvent(virtualDoorEvent=_door("door-1")),
            RuleEvent(crossingLineEvent=_crossing("b")),
        ]
    )

    dispatcher.dispatch(TOPIC, event)

    assert received == ["a", "b"]


def test_rejects_duplicate_key() -> None:
    """Registering a second handler for the same key is an error."""
    dispatcher = EventDispatcher()
    key = HandlerKey(TOPIC, "door-1", VirtualDoorEvent)
    dispatcher.add_handler(key, lambda _event, _door: None)

    with pytest.raises(ValueError, match="already registered"):
        dispatcher.add_handler(key, lambda _event, _door: None)


def test_failing_handler_does_not_stop_other_handlers() -> None:
    """A handler that raises is logged and the remaining ones still run."""
    received: list[str] = []
    dispatcher = EventDispatcher()

    def failing(_event: Event, _line: CrossingLineEvent) -> None:
        raise RuntimeError("boom")

    dispatcher.add_handler(HandlerKey(TOPIC, "a", CrossingLineEvent), failing)
    dispatcher.add_handler(
        HandlerKey(TOPIC, None, CrossingLineEvent),
        lambda _event, _line: received.append("ok"),
    )

    dispatcher.dispatch(TOPIC, _event(crossingLineEvent=_crossing("a")))

    assert received == ["ok"]


def test_topics_lists_every_registered_topic() -> None:
    """`topics` is the set of topics the services must subscribe to."""
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey("t1", None, CrossingLineEvent), lambda _e, _s: None
    )
    dispatcher.add_handler(
        HandlerKey("t2", "door", VirtualDoorEvent), lambda _e, _s: None
    )
    dispatcher.add_handler(
        HandlerKey("t1", "door", VirtualDoorEvent), lambda _e, _s: None
    )

    assert dispatcher.topics == frozenset({"t1", "t2"})
