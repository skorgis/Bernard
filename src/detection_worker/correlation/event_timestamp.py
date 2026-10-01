"""Extract the representative timestamp of a Bernard event schema message."""

from datetime import datetime
from typing import Protocol

from detection_worker.data import Event
from detection_worker.data.models.crossing_line_event import CrossingLineEvent
from detection_worker.data.models.origin_destination_event import (
    OriginDestinationEvent,
)
from detection_worker.data.models.parking_event import ParkingEvent
from detection_worker.data.models.region_of_interest_event import (
    RegionOfInterestEvent,
)
from detection_worker.data.models.virtual_door_event import VirtualDoorEvent


class _HasSubEvents(Protocol):
    """The event-kind fields `Event` and `RuleEvent` both carry.

    Mutually exclusive; each has its own timestamp.
    """

    crossingLineEvent: CrossingLineEvent | None
    regionOfInterestEvent: RegionOfInterestEvent | None
    parkingEvent: ParkingEvent | None
    virtualDoorEvent: VirtualDoorEvent | None
    originDestinationEvent: OriginDestinationEvent | None


def extract_timestamp(event: Event) -> datetime:
    """Return the timestamp that best represents when `event` occurred.

    Prefers the envelope's own `timestamp`. Otherwise looks at whichever
    event-kind field is populated and uses that kind's own timestamp: the
    exit timestamp for `originDestinationEvent` (no top-level timestamp of
    its own), the last movement-path point for `heatmapEvent` (same), and
    the first resolvable sub-event for `ruleEvents`.
    """
    if event.timestamp is not None:
        return datetime.fromisoformat(event.timestamp)

    timestamp = _extract_sub_event_timestamp(event)
    if timestamp is not None:
        return timestamp
    if event.heatmapEvent is not None:
        return datetime.fromisoformat(event.heatmapEvent.path[-1].timestamp)
    if event.ruleEvents:
        for rule_event in event.ruleEvents:
            timestamp = _extract_sub_event_timestamp(rule_event)
            if timestamp is not None:
                return timestamp

    raise ValueError(f"event {event.uuid!r} has no extractable timestamp")


def _extract_sub_event_timestamp(carrier: _HasSubEvents) -> datetime | None:
    if carrier.crossingLineEvent is not None:
        return datetime.fromisoformat(carrier.crossingLineEvent.timestamp)
    if carrier.regionOfInterestEvent is not None:
        return datetime.fromisoformat(carrier.regionOfInterestEvent.timestamp)
    if carrier.parkingEvent is not None:
        return datetime.fromisoformat(carrier.parkingEvent.timestamp)
    if carrier.virtualDoorEvent is not None:
        return datetime.fromisoformat(carrier.virtualDoorEvent.timestamp)
    if carrier.originDestinationEvent is not None:
        return datetime.fromisoformat(
            carrier.originDestinationEvent.exit.timestamp
        )
    return None
