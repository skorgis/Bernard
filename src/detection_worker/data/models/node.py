"""The `node` (edge/analytics device) part of the event envelope."""

from dataclasses import dataclass

from detection_worker.data.models.primitives import Id, Metadata


@dataclass
class Node:
    """Edge/analytics node that produced the event."""

    id: Id
    name: str
    metadata: Metadata | None = None
