"""The `crossingLineEvent` event kind: a track crossing a virtual line."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import (
    Id,
    JourneyTimeInformation,
    NumberPlateRectangle,
    PathPoint,
    Rectangle,
)


@dataclass
class CrossingLineEvent:
    """A tracked object crossing a virtual line."""

    class_: str  # JSON key is "class", a reserved word in Python
    lineId: Id
    lineName: str
    direction: str  # "in" | "out"
    timestamp: str
    subClass: str | None = None
    directionName: str | None = None
    trackId: float | None = None
    trackUuid: Id | None = None
    speedestimate: str | None = None
    numberPlate: str | None = None
    numberPlateOrigin: str | None = None
    numberPlateArea: str | None = None
    numberPlateLines: int | None = None
    numberPlateImage: str | None = None
    journeyTimePrimaryTag: JourneyTimeInformation | None = None
    journeyTimeSecondaryTag: JourneyTimeInformation | None = None
    path: list[PathPoint] | None = None
    numberPlateRect: NumberPlateRectangle | None = None
    vehicleRect: Rectangle | None = None
