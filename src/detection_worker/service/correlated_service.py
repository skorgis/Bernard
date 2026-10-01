"""Wires one MQTT client into an `EventCorrelator`, logging the results."""

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from detection_worker.correlation.correlator import EventCorrelator, Matched
from detection_worker.correlation.event_timestamp import extract_timestamp
from detection_worker.data import Event
from detection_worker.data.parsing import parse_event
from detection_worker.dispatch import EventDispatcher
from detection_worker.transport.client import MqttClient

logger = logging.getLogger(__name__)

OnPair = Callable[[Matched[Event], Matched[Event]], None]
OnUnmatched = Callable[[Matched[Event]], None]


def _log_pair(a: Matched[Event], b: Matched[Event]) -> None:
    logger.info(
        "correlated pair: %s@%s <-> %s@%s",
        a.source,
        a.timestamp,
        b.source,
        b.timestamp,
    )


def _log_unmatched(m: Matched[Event]) -> None:
    logger.warning("unmatched event from %s at %s", m.source, m.timestamp)


class CorrelatedEventService:
    """Subscribes one `Client` to two topics and correlates their events."""

    def __init__(
        self,
        client: MqttClient,
        topic_a: str,
        topic_b: str,
        tolerance: timedelta,
        leading_source: Literal["a", "b"] = "a",
        on_pair: OnPair | None = None,
        on_unmatched: OnUnmatched | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        """Wire `client` into a correlator over `topic_a`/`topic_b`.

        `leading_source` says which topic's event occurs first for the
        same physical crossing (see `EventCorrelator.leading_source`).
        `on_pair`/`on_unmatched` default to logging at INFO/WARNING; pass
        your own callback to handle correlated/unmatched events instead.

        `dispatcher`, if given, sees every parsed message before
        correlation; its topics are subscribed too, so a handler may listen
        on a topic that isn't `topic_a`/`topic_b`. Register its handlers
        before `start()` — topics added later aren't subscribed.
        """
        self._client = client
        self._topic_a = topic_a
        self._topic_b = topic_b
        self._dispatcher = dispatcher or EventDispatcher()
        self._correlator = EventCorrelator[Event](
            tolerance=tolerance,
            leading_source=leading_source,
            on_pair=on_pair or _log_pair,
            on_unmatched=on_unmatched or _log_unmatched,
        )
        client.set_on_message(self._handle_message)
        client.set_on_connect(self._handle_connect)
        client.set_on_disconnect(self._handle_disconnect)

    def start(self) -> None:
        """Connect the client and start its network loop.

        Subscribing happens in `_handle_connect`, not here: sending
        anything before the broker's CONNACK is a protocol violation some
        brokers punish by closing the connection, and subscribing only on
        (re)connect is also what keeps the subscriptions alive across an
        automatic reconnect.

        A generous reconnect backoff (not paho's near-instant default):
        a broker can reject a reconnect that comes in faster than it can
        release state tied to this connection's identity, and reconnecting
        immediately again just repeats that failure in a tight loop.
        """
        self._client.set_reconnect_delay(min_delay=5, max_delay=30)
        self._client.connect()
        self._client.loop_start()

    def _handle_connect(self, rc: int) -> None:
        if rc != 0:
            logger.error("connection failed (rc=%s)", rc)
            return
        for topic in {self._topic_a, self._topic_b} | self._dispatcher.topics:
            self._client.subscribe(topic)

    def _handle_disconnect(self, rc: int) -> None:
        if rc != 0:
            logger.warning(
                "unexpectedly disconnected (rc=%s); reconnecting", rc
            )

    def stop(self) -> None:
        """Stop the client's network loop and disconnect."""
        self._client.loop_stop()
        self._client.disconnect()

    def _handle_message(self, topic: str, payload: bytes) -> None:
        correlated = topic in (self._topic_a, self._topic_b)
        if not correlated and topic not in self._dispatcher.topics:
            raise ValueError(f"message on unexpected topic: {topic!r}")
        event = parse_event(payload)
        self._dispatcher.dispatch(topic, event)
        if correlated:
            self._correlate(topic, event)

    def _correlate(self, topic: str, event: Event) -> None:
        source = self._source_for_topic(topic)
        timestamp = extract_timestamp(event)
        logger.debug(
            "parsed event: source=%s timestamp=%s event=%r",
            source,
            timestamp,
            event,
        )
        self._correlator.add(source, timestamp, event)

    def _source_for_topic(self, topic: str) -> str:
        if topic == self._topic_a:
            return "a"
        if topic == self._topic_b:
            return "b"
        raise ValueError(f"message on unexpected topic: {topic!r}")
