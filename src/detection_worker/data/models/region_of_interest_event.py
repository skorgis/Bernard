"""The `regionOfInterestEvent` event kind: occupancy state of a zone."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import (
    Id,
    NumberPlateRectangle,
    Rectangle,
)


@dataclass
class RegionOfInterestObject:
    """A single tracked object detected within a region of interest."""

    class_: str  # JSON key is "class", a reserved word in Python
    trackId: float | None = None
    dwellTime: float | None = None
    subClass: str | None = None
    trackUuid: Id | None = None
    numberPlate: str | None = None
    numberPlateOrigin: str | None = None
    numberPlateArea: str | None = None
    numberPlateLines: int | None = None
    numberPlateRect: NumberPlateRectangle | None = None
    vehicleRect: Rectangle | None = None
    numberPlateImage: str | None = None


@dataclass
class RegionOfInterestEvent:
    """Occupancy/dwell-time state of a region of interest."""

    roiId: Id
    roiName: str
    triggerType: str  # "time" | "change"
    timestamp: str
    state: str  # "occupied" | "vacant"
    objects: list[RegionOfInterestObject]
    capacity: float | None = None
