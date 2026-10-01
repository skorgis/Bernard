"""A single entry of the `ruleEvents` list."""

from dataclasses import dataclass

from detection_worker.data.models.crossing_line_event import CrossingLineEvent
from detection_worker.data.models.origin_destination_event import (
    OriginDestinationEvent,
)
from detection_worker.data.models.parking_event import ParkingEvent
from detection_worker.data.models.region_of_interest_event import (
    RegionOfInterestEvent,
)
from detection_worker.data.models.virtual_door_event import VirtualDoorEvent


@dataclass
class RuleEvent:
    """One entry of `ruleEvents`; exactly one field is set."""

    regionOfInterestEvent: RegionOfInterestEvent | None = None
    parkingEvent: ParkingEvent | None = None
    crossingLineEvent: CrossingLineEvent | None = None
    virtualDoorEvent: VirtualDoorEvent | None = None
    originDestinationEvent: OriginDestinationEvent | None = None
