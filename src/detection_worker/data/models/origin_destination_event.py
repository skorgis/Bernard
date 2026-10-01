"""The `originDestinationEvent` event kind: a track's path between zones."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import Id, PathPoint, Zone


@dataclass
class ZoneCrossing:
    """A track entering or exiting a zone."""

    zone: Zone
    timestamp: str


@dataclass
class OriginDestinationEvent:
    """A tracked object's path between an entry and an exit zone."""

    classification: str
    entry: ZoneCrossing
    exit: ZoneCrossing
    movementPath: list[PathPoint]
    trackId: float
    subClass: str | None = None
    trackUuid: Id | None = None
