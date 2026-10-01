"""The `virtualDoorEvent` event kind: a track passing a virtual door."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import Id


@dataclass
class VirtualDoorObject:
    """The object that triggered a virtual door event."""

    class_: str  # JSON key is "class", a reserved word in Python


@dataclass
class VirtualDoorEvent:
    """A tracked object crossing a virtual door."""

    virtualDoorId: Id
    virtualDoorName: str
    direction: str  # "in" | "out"
    timestamp: str
    object: VirtualDoorObject
    trackId: float | None = None
    trackUuid: Id | None = None
