"""The `parkingEvent` event kind: occupancy summary of parking regions."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import Id


@dataclass
class NumberPlateEntry:
    """A single recognized number plate."""

    numberPlate: str | None = None
    numberPlateOrigin: str | None = None
    numberPlateArea: str | None = None


@dataclass
class ParkingSummaryEntry:
    """Occupancy summary for a single parking region of interest."""

    roiId: Id
    roiName: str
    capacity: float
    vehicles: float
    numberPlates: list[NumberPlateEntry] | None = None


@dataclass
class ParkingEvent:
    """Aggregated parking occupancy across one or more regions."""

    timestamp: str
    parkingSummary: list[ParkingSummaryEntry]
    totalCapacity: float | None = None
    totalVehicles: float | None = None
