"""JSON parsing of Bernard event schema messages.

Into `detection_worker.data.models`.
"""

from detection_worker.data.parsing.parser import from_dict, parse_event

__all__ = [
    "from_dict",
    "parse_event",
]
