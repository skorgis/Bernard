"""Typed per-(topic, name, event type) handlers for parsed events."""

from detection_worker.dispatch.dispatcher import (
    EventDispatcher,
    Handler,
    HandlerKey,
    SubEvent,
)

__all__ = [
    "EventDispatcher",
    "Handler",
    "HandlerKey",
    "SubEvent",
]
