"""Translate BMA events into calls on the `ParkingGuide`."""

import logging
import time
import zlib
from collections.abc import Callable, Iterable

from detection_worker.data import (
    CrossingLineEvent,
    Event,
    RegionOfInterestEvent,
    parse_event,
)
from detection_worker.dispatch import EventDispatcher, HandlerKey

from parkleitsystem.config import EntrySettings
from parkleitsystem.guide import ParkingGuide

logger = logging.getLogger(__name__)

# `state` values of a regionOfInterestEvent (event schema 6.0).
OCCUPIED = "occupied"
VACANT = "vacant"

# What parse_event raises for broken input: bad JSON or zlib data
# (ValueError, zlib.error), missing required fields (TypeError) or wrong
# nesting (KeyError, AttributeError).
_INVALID_EVENT_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    zlib.error,
)


def handle_payload(
    dispatcher: EventDispatcher, topic: str, payload: bytes
) -> None:
    """Parse one MQTT message and dispatch it; log and skip invalid ones."""
    try:
        event = parse_event(payload)
    except _INVALID_EVENT_ERRORS as err:
        logger.warning("skipping invalid event on %s: %s", topic, err)
        return
    dispatcher.dispatch(topic, event)


def register_handlers(
    dispatcher: EventDispatcher,
    *,
    topic: str,
    entry: EntrySettings,
    space_names: Iterable[str],
    guide: ParkingGuide,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Route zone states and entry crossings on `topic` to `guide`.

    Only the configured zones and the entry line get a handler; the
    dispatcher drops everything else, e.g. other teams' test events.
    """

    def on_zone(event: Event, zone: RegionOfInterestEvent) -> None:
        if zone.state not in (OCCUPIED, VACANT):
            logger.warning(
                "zone %s: unknown state %r, skipped", zone.roiName, zone.state
            )
            return
        guide.on_space_state(zone.roiName, occupied=zone.state == OCCUPIED)

    def on_entry_line(event: Event, line: CrossingLineEvent) -> None:
        if line.direction != entry.direction:
            return
        if entry.vehicle_classes and line.class_ not in entry.vehicle_classes:
            logger.debug("ignoring %s on the entry line", line.class_)
            return
        logger.info("%s entering", line.class_)
        guide.on_vehicle_entered(now=clock())

    for name in space_names:
        dispatcher.add_handler(
            HandlerKey(topic, name, RegionOfInterestEvent), on_zone
        )
    dispatcher.add_handler(
        HandlerKey(topic, entry.line_name, CrossingLineEvent), on_entry_line
    )
