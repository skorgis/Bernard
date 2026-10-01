"""Route each sub-event of a message to the handler registered for it.

`SubEvent` plays the role of a C++ `std::variant`: every `Event` carries
exactly one of these kinds (or several, inside `ruleEvents`). `_names_of`
is the visitor — a `match` over the alternatives, closed off with
`assert_never` so pyright flags any kind added later but not handled here.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, assert_never

from detection_worker.data.models.crossing_line_event import CrossingLineEvent
from detection_worker.data.models.event import Event
from detection_worker.data.models.heatmap_event import HeatmapEvent
from detection_worker.data.models.origin_destination_event import (
    OriginDestinationEvent,
)
from detection_worker.data.models.parking_event import ParkingEvent
from detection_worker.data.models.region_of_interest_event import (
    RegionOfInterestEvent,
)
from detection_worker.data.models.rule_event import RuleEvent
from detection_worker.data.models.virtual_door_event import VirtualDoorEvent

logger = logging.getLogger(__name__)

type SubEvent = (
    CrossingLineEvent
    | RegionOfInterestEvent
    | ParkingEvent
    | VirtualDoorEvent
    | OriginDestinationEvent
    | HeatmapEvent
)

type Handler[T: SubEvent] = Callable[[Event, T], None]
"""Called with the whole message and the sub-event its key selected."""


@dataclass(frozen=True)
class HandlerKey[T: SubEvent]:
    """Selects sub-events of `event_type` named `name` arriving on `topic`.

    `name` is matched against the sub-event's own name: `lineName`,
    `roiName`, `virtualDoorName`, the entry *or* exit zone name of an
    origin/destination event, or any `roiName` in a parking summary.
    `None` matches every sub-event of `event_type` on `topic` — the only
    way to select a `HeatmapEvent`, which has no name.
    """

    topic: str
    name: str | None
    event_type: type[T]


class EventDispatcher:
    """A `HandlerKey` → handler table, applied to each parsed message.

    Handlers go in through `add_handler` rather than a dict literal: Python
    can't type a dict whose value type depends on its key, but a generic
    method can, so pyright checks each handler against its key's
    `event_type`.
    """

    def __init__(self) -> None:
        """Start with no handlers."""
        self._handlers: dict[HandlerKey[Any], Handler[Any]] = {}

    def add_handler[T: SubEvent](
        self, key: HandlerKey[T], handler: Handler[T]
    ) -> None:
        """Register `handler` for `key`; each key takes one handler."""
        if key in self._handlers:
            raise ValueError(f"a handler is already registered for {key}")
        self._handlers[key] = handler

    @property
    def topics(self) -> frozenset[str]:
        """Every topic some handler listens on."""
        return frozenset(key.topic for key in self._handlers)

    def dispatch(self, topic: str, event: Event) -> None:
        """Call every handler whose key matches a sub-event of `event`.

        A handler that raises is logged and skipped, so it can't keep the
        other handlers — or the caller's correlation — from running.
        """
        for sub_event in _sub_events_of(event):
            for name in (*_names_of(sub_event), None):
                key = HandlerKey(topic, name, type(sub_event))
                handler = self._handlers.get(key)
                if handler is not None:
                    self._call(handler, key, event, sub_event)

    @staticmethod
    def _call(
        handler: Handler[Any],
        key: HandlerKey[Any],
        event: Event,
        sub_event: SubEvent,
    ) -> None:
        try:
            handler(event, sub_event)
        except Exception:
            logger.exception(
                "handler for %s failed on event %s", key, event.uuid
            )


def _sub_events_of(event: Event) -> list[SubEvent]:
    sub_events = _populated(event)
    if event.heatmapEvent is not None:
        sub_events.append(event.heatmapEvent)
    for rule_event in event.ruleEvents or []:
        sub_events.extend(_populated(rule_event))
    return sub_events


def _populated(carrier: Event | RuleEvent) -> list[SubEvent]:
    candidates = (
        carrier.crossingLineEvent,
        carrier.regionOfInterestEvent,
        carrier.parkingEvent,
        carrier.virtualDoorEvent,
        carrier.originDestinationEvent,
    )
    return [candidate for candidate in candidates if candidate is not None]


def _names_of(sub_event: SubEvent) -> frozenset[str]:
    match sub_event:
        case CrossingLineEvent(lineName=name):
            return frozenset({name})
        case RegionOfInterestEvent(roiName=name):
            return frozenset({name})
        case VirtualDoorEvent(virtualDoorName=name):
            return frozenset({name})
        case OriginDestinationEvent(entry=entry, exit=exit_):
            zone_names = (entry.zone.name, exit_.zone.name)
            return frozenset(name for name in zone_names if name is not None)
        case ParkingEvent(parkingSummary=summary):
            return frozenset(entry.roiName for entry in summary)
        case HeatmapEvent():
            return frozenset()
        case _:
            assert_never(sub_event)
