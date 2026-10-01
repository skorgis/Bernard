"""Root Bernard event message (event schema 6.0)."""

from dataclasses import dataclass

from detection_worker.data.models.crossing_line_event import CrossingLineEvent
from detection_worker.data.models.heatmap_event import HeatmapEvent
from detection_worker.data.models.node import Node
from detection_worker.data.models.origin_destination_event import (
    OriginDestinationEvent,
)
from detection_worker.data.models.parking_event import ParkingEvent
from detection_worker.data.models.primitives import TenantId
from detection_worker.data.models.region_of_interest_event import (
    RegionOfInterestEvent,
)
from detection_worker.data.models.rule_event import RuleEvent
from detection_worker.data.models.stream import Stream
from detection_worker.data.models.virtual_door_event import VirtualDoorEvent


@dataclass
class Event:
    """A single Bernard event message.

    Exactly one of the `*Event`/`ruleEvents` fields is set, depending on
    the rule that produced the message.
    """

    uuid: str
    version: str
    eventSchema: str
    node: Node
    stream: Stream
    tenantId: TenantId | None = None
    ruleId: str | None = None
    ruleName: str | None = None
    timestamp: str | None = None
    regionOfInterestEvent: RegionOfInterestEvent | None = None
    parkingEvent: ParkingEvent | None = None
    crossingLineEvent: CrossingLineEvent | None = None
    heatmapEvent: HeatmapEvent | None = None
    virtualDoorEvent: VirtualDoorEvent | None = None
    originDestinationEvent: OriginDestinationEvent | None = None
    ruleEvents: list[RuleEvent] | None = None
