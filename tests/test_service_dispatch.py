"""Tests for `EventDispatcher` wired into both correlation services."""

import json
from datetime import timedelta

from detection_worker.correlation.correlator import Matched
from detection_worker.data import CrossingLineEvent, Event, VirtualDoorEvent
from detection_worker.dispatch import EventDispatcher, HandlerKey
from detection_worker.service.correlated_service import CorrelatedEventService
from detection_worker.service.multi_site_service import (
    MultiSiteCorrelatedService,
    Site,
)
from tests.fake_mqtt_client import FakeClient

TS = "2026-10-01T12:00:00+00:00"
TS_LATER = "2026-10-01T12:00:00.300000+00:00"


def _crossing_payload(line_name: str, timestamp: str = TS) -> bytes:
    return json.dumps(
        {
            "uuid": "e1",
            "version": "6.0",
            "eventSchema": "6.0",
            "node": {"id": "n1", "name": "cam"},
            "stream": {"id": "s1", "name": "lane"},
            "crossingLineEvent": {
                "class": "car",
                "lineId": "l1",
                "lineName": line_name,
                "direction": "in",
                "timestamp": timestamp,
            },
        }
    ).encode()


def _door_payload(door_name: str) -> bytes:
    return json.dumps(
        {
            "uuid": "e2",
            "version": "6.0",
            "eventSchema": "6.0",
            "node": {"id": "n1", "name": "cam"},
            "stream": {"id": "s1", "name": "door"},
            "virtualDoorEvent": {
                "virtualDoorId": "d1",
                "virtualDoorName": door_name,
                "direction": "in",
                "timestamp": TS,
                "object": {"class": "person"},
            },
        }
    ).encode()


def _connect(client: FakeClient) -> None:
    assert client.on_connect is not None
    client.on_connect(0)


def _deliver(client: FakeClient, topic: str, payload: bytes) -> None:
    assert client.on_message is not None
    client.on_message(topic, payload)


def _door_dispatcher(topic: str, received: list[str]) -> EventDispatcher:
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey(topic, "door-1", VirtualDoorEvent),
        lambda _event, door: received.append(door.virtualDoorName),
    )
    return dispatcher


# --- CorrelatedEventService -------------------------------------------------


def _single_pair_service(
    client: FakeClient,
    dispatcher: EventDispatcher,
    pairs: list[tuple[Matched[Event], Matched[Event]]],
) -> CorrelatedEventService:
    return CorrelatedEventService(
        client=client,
        topic_a="bma/events",
        topic_b="bca/events",
        tolerance=timedelta(seconds=1),
        on_pair=lambda a, b: pairs.append((a, b)),
        dispatcher=dispatcher,
    )


def test_single_pair_subscribes_dispatcher_only_topics() -> None:
    """Topics only a handler listens on get subscribed on connect too."""
    client = FakeClient()
    _single_pair_service(client, _door_dispatcher("doors", []), [])

    _connect(client)

    assert "subscribe:doors" in client.calls


def test_single_pair_dispatches_and_still_correlates() -> None:
    """Messages on correlated topics reach handlers and the correlator."""
    client = FakeClient()
    received: list[str] = []
    pairs: list[tuple[Matched[Event], Matched[Event]]] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey("bma/events", None, CrossingLineEvent),
        lambda _event, line: received.append(line.lineName),
    )
    _single_pair_service(client, dispatcher, pairs)

    _deliver(client, "bma/events", _crossing_payload("hard-shoulder"))
    _deliver(client, "bca/events", _crossing_payload("anpr", TS_LATER))

    assert received == ["hard-shoulder"]
    assert len(pairs) == 1


def test_single_pair_dispatches_handler_only_topic() -> None:
    """A dispatcher-only topic is dispatched, not treated as unexpected."""
    client = FakeClient()
    received: list[str] = []
    pairs: list[tuple[Matched[Event], Matched[Event]]] = []
    _single_pair_service(client, _door_dispatcher("doors", received), pairs)

    _deliver(client, "doors", _door_payload("door-1"))

    assert received == ["door-1"]
    assert pairs == []


# --- MultiSiteCorrelatedService ---------------------------------------------


def _site(name: str, bma: str, bca: str) -> Site:
    return Site(
        name=name,
        topic_bma=bma,
        topic_bca=bca,
        line_name_bma="hard-shoulder",
        line_name_bca="anpr",
        tolerance=timedelta(seconds=1),
        leading_role="bma",
    )


def test_multi_site_subscribes_dispatcher_only_topics() -> None:
    """Handler topics are subscribed alongside every site's topics."""
    client = FakeClient()
    MultiSiteCorrelatedService(
        client,
        [_site("s1", "s1/bma", "s1/bca")],
        dispatcher=_door_dispatcher("doors", []),
    )

    _connect(client)

    assert {"subscribe:s1/bma", "subscribe:s1/bca", "subscribe:doors"} <= set(
        client.calls
    )


def test_multi_site_dispatches_and_still_correlates() -> None:
    """Site messages reach both the handlers and the site's correlator."""
    client = FakeClient()
    received: list[str] = []
    pairs: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.add_handler(
        HandlerKey("s1/bma", "hard-shoulder", CrossingLineEvent),
        lambda _event, line: received.append(line.lineName),
    )
    MultiSiteCorrelatedService(
        client,
        [_site("s1", "s1/bma", "s1/bca")],
        on_pair=lambda site, _a, _b: pairs.append(site),
        dispatcher=dispatcher,
    )

    _deliver(client, "s1/bma", _crossing_payload("hard-shoulder"))
    _deliver(client, "s1/bca", _crossing_payload("anpr", TS_LATER))

    assert received == ["hard-shoulder"]
    assert pairs == ["s1"]


def test_multi_site_handles_dispatcher_only_topic() -> None:
    """A topic no site uses is still delivered to its handlers."""
    client = FakeClient()
    received: list[str] = []
    MultiSiteCorrelatedService(
        client,
        [_site("s1", "s1/bma", "s1/bca")],
        dispatcher=_door_dispatcher("doors", received),
    )

    _deliver(client, "doors", _door_payload("door-1"))

    assert received == ["door-1"]


def test_multi_site_reload_keeps_topic_a_handler_still_needs() -> None:
    """Removing a site doesn't unsubscribe a topic a handler listens on."""
    client = FakeClient()
    received: list[str] = []
    service = MultiSiteCorrelatedService(
        client,
        [_site("s1", "s1/bma", "s1/bca")],
        dispatcher=_door_dispatcher("s1/bma", received),
    )
    _connect(client)

    service.reload([])

    assert "unsubscribe:s1/bca" in client.calls
    assert "unsubscribe:s1/bma" not in client.calls
    _deliver(client, "s1/bma", _door_payload("door-1"))
    assert received == ["door-1"]
