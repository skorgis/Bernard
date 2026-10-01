"""Dataclasses representing the Bernard event schema 6.0."""

from detection_worker.data.models.crossing_line_event import CrossingLineEvent
from detection_worker.data.models.event import Event
from detection_worker.data.models.heatmap_event import HeatmapEvent
from detection_worker.data.models.node import Node
from detection_worker.data.models.origin_destination_event import (
    OriginDestinationEvent,
    ZoneCrossing,
)
from detection_worker.data.models.parking_event import (
    NumberPlateEntry,
    ParkingEvent,
    ParkingSummaryEntry,
)
from detection_worker.data.models.primitives import (
    GeoLocation,
    Id,
    JourneyTimeInformation,
    Metadata,
    NumberPlateRectangle,
    PathPoint,
    Rectangle,
    TenantId,
    Zone,
)
from detection_worker.data.models.region_of_interest_event import (
    RegionOfInterestEvent,
    RegionOfInterestObject,
)
from detection_worker.data.models.rule_event import RuleEvent
from detection_worker.data.models.stream import Stream
from detection_worker.data.models.virtual_door_event import (
    VirtualDoorEvent,
    VirtualDoorObject,
)

__all__ = [
    "CrossingLineEvent",
    "Event",
    "GeoLocation",
    "HeatmapEvent",
    "Id",
    "JourneyTimeInformation",
    "Metadata",
    "Node",
    "NumberPlateEntry",
    "NumberPlateRectangle",
    "OriginDestinationEvent",
    "ParkingEvent",
    "ParkingSummaryEntry",
    "PathPoint",
    "Rectangle",
    "RegionOfInterestEvent",
    "RegionOfInterestObject",
    "RuleEvent",
    "Stream",
    "TenantId",
    "VirtualDoorEvent",
    "VirtualDoorObject",
    "Zone",
    "ZoneCrossing",
]
