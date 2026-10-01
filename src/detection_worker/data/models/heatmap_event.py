"""The `heatmapEvent` event kind: a track's movement path for heatmaps."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import Id, PathPoint


@dataclass
class HeatmapEvent:
    """A tracked object's movement path, used to build heatmaps."""

    class_: str  # JSON key is "class", a reserved word in Python
    path: list[PathPoint]
    subClass: str | None = None
    trackId: float | None = None
    trackUuid: Id | None = None
