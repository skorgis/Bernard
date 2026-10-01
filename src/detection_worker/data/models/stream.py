"""The `stream` (video/sensor source) part of the event envelope."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import GeoLocation, Id


@dataclass
class Stream:
    """Video/sensor stream that an event originates from."""

    id: Id
    name: str
    geoLocation: GeoLocation | None = None
