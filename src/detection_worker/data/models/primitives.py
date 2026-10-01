"""Primitive types shared across the Bernard event schema (v6.0)."""

from dataclasses import dataclass

type Id = str
type TenantId = str
type Metadata = dict[str, str]


@dataclass
class GeoLocation:
    """Geographic location, as [longitude, latitude, ...]."""

    coordinates: list[float]


@dataclass
class Rectangle:
    """Axis-aligned bounding box."""

    x: float
    y: float
    h: float
    w: float


type NumberPlateRectangle = Rectangle
"""Bounding box of a detected number plate; same shape as `Rectangle`."""


@dataclass
class PathPoint:
    """One point of a tracked object's bounding box over time.

    Shared by `crossingLineEvent.path`, `originDestinationEvent.movementPath`
    and `heatmapEvent.path`, which all use this exact item shape.
    """

    x: float
    y: float
    w: float
    h: float
    timestamp: str


@dataclass
class Zone:
    """Named zone referenced by an origin/destination event."""

    zoneId: Id
    name: str | None = None


@dataclass
class JourneyTimeInformation:
    """Anonymized journey-time correlation tag."""

    saltId: str
    hash: str
    validFrom: str
    validUntil: str
    parkingJourney: bool | None = None
