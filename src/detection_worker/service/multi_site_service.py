"""Wires one MQTT client into per-site `EventCorrelator`s.

Generalizes `CorrelatedEventService` from one BMA/BCA topic pair to many:
every site still gets its own `EventCorrelator` (so sites never
cross-correlate), but all of them share a single `Client`, since a
`Client` only supports one handler per callback slot — and this broker
only allows one live connection per client id in the first place.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from detection_worker.correlation.correlator import EventCorrelator, Matched
from detection_worker.correlation.event_timestamp import extract_timestamp
from detection_worker.data import Event
from detection_worker.data.parsing import parse_event
from detection_worker.dispatch import EventDispatcher
from detection_worker.transport.client import MqttClient

logger = logging.getLogger(__name__)

OnPair = Callable[[str, Matched[Event], Matched[Event]], None]
OnUnmatched = Callable[[str, Matched[Event]], None]
OnJam = Callable[[str, datetime, Event], None]
OnEvent = Callable[[str, str, str, datetime, Event], None]

LineType = Literal["crossing_line", "origin_destination"]
Role = Literal["bma", "bca"]

# (site_name, role, line_name, line_type, jam_line_name, jam_line_type)
_TopicConfig = tuple[str, str, str, str, str | None, str]


def _matches_configured_line(
    event: Event, line_type: str, line_name: str
) -> bool:
    """Whether `event` is on the named line/zone for `line_type`.

    An origin/destination event matches on either its entry or its exit
    zone — `line_name` doesn't say which side of the pair it names.
    """
    if line_type == "crossing_line":
        cle = event.crossingLineEvent
        return cle is not None and cle.lineName == line_name
    ode = event.originDestinationEvent
    return ode is not None and (
        ode.entry.zone.name == line_name or ode.exit.zone.name == line_name
    )


@dataclass
class Site:
    """One BMA/BCA topic pair, identified by `name`.

    Each topic can carry events for more than one virtual line/zone (e.g.
    a BMA publishes both a jam-detection line and a hard-shoulder/
    emergency-lane line on the same topic) — only the named line on each
    side is fed into correlation; everything else on that topic is
    ignored. `line_type_*` says whether that name is a
    `crossingLineEvent.lineName` or an `originDestinationEvent` zone name.

    `line_name_jam`, on `topic_bma`, is a third, independent line: its
    events never go into correlation (there's nothing to pair a jam
    reading with) — they're routed to `on_jam` instead. `None` disables
    jam handling for this site.

    `tolerance` is this site's own `EventCorrelator` window: how far
    apart its BMA/BCA events may be and still count as one pass. Sites
    aren't required to share a tolerance — e.g. a site with more distance
    between its two devices needs a wider window than one with them close
    together.

    `leading_role` says which device's line a vehicle physically crosses
    first at this site (e.g. `"bma"` if the hard-shoulder line comes
    before the ANPR line on the road) — see `EventCorrelator.
    leading_source`. Sites can differ here depending on device placement.

    `symmetric_tolerance` is passed straight through to `EventCorrelator`
    — see its docstring. Off by default (strict leading/trailing order);
    turn on per-site where the two devices' measurement points are close
    enough that reported order can jitter across the true crossing.
    """

    name: str
    topic_bma: str
    topic_bca: str
    line_name_bma: str
    line_name_bca: str
    tolerance: timedelta
    leading_role: Role
    line_type_bma: LineType = "crossing_line"
    line_type_bca: LineType = "crossing_line"
    line_name_jam: str | None = None
    line_type_jam: LineType = "crossing_line"
    symmetric_tolerance: bool = False


class MultiSiteCorrelatedService:
    """Subscribes one `Client` to every site's topics.

    Correlates each site's events independently.
    """

    def __init__(
        self,
        client: MqttClient,
        sites: list[Site],
        on_pair: OnPair | None = None,
        on_unmatched: OnUnmatched | None = None,
        on_jam: OnJam | None = None,
        on_event: OnEvent | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        """Wire `client` into one correlator per site in `sites`.

        Each site brings its own correlation `tolerance` (see `Site`).
        `on_pair`/`on_unmatched`/`on_jam` default to logging at INFO/
        WARNING/INFO; pass your own callback to handle correlated/
        unmatched/jam-line events instead. Each is called with the site
        name as its first argument. `on_event`, if given, is called with
        `(site_name, role, topic, timestamp, event)` for every event that
        lands on a site's correlation line (ANPR/emergency-lane) — before
        it's known whether the correlator will pair or discard it;
        defaults to a no-op (the existing debug log at that point already
        covers it).

        `dispatcher`, if given, sees every parsed message before any site
        routing; its topics are subscribed too and stay subscribed across
        `reload`, whether or not a site still uses them. Register its
        handlers before `start()` — topics added later aren't subscribed.
        """
        self._client = client
        self._dispatcher = dispatcher or EventDispatcher()
        # Guards the site/topic/correlator tables: `reload` is typically
        # called from another thread than paho's network thread, which runs
        # every other entry point. Re-entrant so a callback may `reload`.
        self._lock = threading.RLock()
        self._on_pair = on_pair or self._log_pair
        self._on_unmatched = on_unmatched or self._log_unmatched
        self._on_jam = on_jam or self._log_jam
        self._on_event = on_event or (lambda *_args: None)
        self._sites: dict[str, Site] = {}
        self._topics: dict[str, _TopicConfig] = {}
        self._correlators: dict[str, EventCorrelator[Event]] = {}
        self._connected = False
        for site in sites:
            self._register_site(site)

        client.set_on_message(self._handle_message)
        client.set_on_connect(self._handle_connect)
        client.set_on_disconnect(self._handle_disconnect)

    def reload(self, sites: list[Site]) -> None:
        """Add/update/remove sites to match `sites`, in place.

        See detection_worker/ARCHITECTURE.md § Site config reload.
        `Site` is a plain `@dataclass`, so this is just `==`: a site
        that's unchanged (same name, same field values) is left
        completely alone — its `EventCorrelator` and any pending/
        unmatched events it's already buffered survive the reload. A
        site that's new, or whose fields changed at all, is unsubscribed
        (if it existed before) and re-registered from scratch — there's
        no partial update of a single field. A site that's gone is just
        unsubscribed and dropped.

        Safe to call from any thread: it waits for a message that's being
        handled to finish, and messages wait for it.
        """
        with self._lock:
            new_by_name = {site.name: site for site in sites}
            old_names = set(self._sites)
            new_names = set(new_by_name)

            for name in old_names - new_names:
                self._unregister_site(name)

            for name in old_names & new_names:
                if new_by_name[name] != self._sites[name]:
                    self._unregister_site(name)
                    self._register_site(new_by_name[name])

            for name in new_names - old_names:
                self._register_site(new_by_name[name])

    def _register_site(self, site: Site) -> None:
        self._sites[site.name] = site
        for topic, role, line_name, line_type, jam_name, jam_type in (
            (
                site.topic_bma,
                "bma",
                site.line_name_bma,
                site.line_type_bma,
                site.line_name_jam,
                site.line_type_jam,
            ),
            (
                site.topic_bca,
                "bca",
                site.line_name_bca,
                site.line_type_bca,
                None,
                "crossing_line",
            ),
        ):
            if topic in self._topics:
                raise ValueError(
                    f"topic {topic!r} is used by more than one site"
                )
            self._topics[topic] = (
                site.name,
                role,
                line_name,
                line_type,
                jam_name,
                jam_type,
            )
            if self._connected and topic not in self._dispatcher.topics:
                self._client.subscribe(topic)
        self._correlators[site.name] = EventCorrelator[Event](
            tolerance=site.tolerance,
            leading_source=site.leading_role,
            on_pair=lambda a, b, name=site.name: self._on_pair(name, a, b),
            on_unmatched=lambda m, name=site.name: self._on_unmatched(name, m),
            symmetric=site.symmetric_tolerance,
        )

    def _unregister_site(self, site_name: str) -> None:
        site = self._sites.pop(site_name)
        for topic in (site.topic_bma, site.topic_bca):
            del self._topics[topic]
            if self._connected and topic not in self._dispatcher.topics:
                self._client.unsubscribe(topic)
        del self._correlators[site_name]

    def start(self) -> None:
        """Connect the client and start its network loop.

        See `CorrelatedEventService.start` for why subscribing happens in
        `_handle_connect` rather than here, and why the reconnect delay
        is generous rather than paho's near-instant default.
        """
        self._client.set_reconnect_delay(min_delay=5, max_delay=30)
        self._client.connect()
        self._client.loop_start()

    def stop(self) -> None:
        """Stop the client's network loop and disconnect."""
        self._client.loop_stop()
        self._client.disconnect()

    def _handle_connect(self, rc: int) -> None:
        if rc != 0:
            logger.error("connection failed (rc=%s)", rc)
            return
        with self._lock:
            self._connected = True
            for topic in set(self._topics) | self._dispatcher.topics:
                self._client.subscribe(topic)

    def _handle_disconnect(self, rc: int) -> None:
        with self._lock:
            self._connected = False
        if rc != 0:
            logger.warning(
                "unexpectedly disconnected (rc=%s); reconnecting", rc
            )

    def _handle_message(self, topic: str, payload: bytes) -> None:
        with self._lock:
            self._handle_message_locked(topic, payload)

    def _handle_message_locked(self, topic: str, payload: bytes) -> None:
        site_topic = topic in self._topics
        if not site_topic and topic not in self._dispatcher.topics:
            raise ValueError(f"message on unexpected topic: {topic!r}")
        event = parse_event(payload)
        self._dispatcher.dispatch(topic, event)
        if site_topic:
            self._route_to_site(topic, event)

    def _route_to_site(self, topic: str, event: Event) -> None:
        site_name, role, line_name, line_type, jam_name, jam_type = (
            self._topics[topic]
        )
        logger.debug("%s: received event on %s: %r", site_name, topic, event)

        if self._route_to_correlator(
            site_name, role, topic, line_name, line_type, event
        ):
            return
        if self._route_to_jam(site_name, jam_name, jam_type, event):
            return

        logger.debug(
            "%s: ignoring %s event not on a configured line/zone",
            site_name,
            role,
        )

    def _route_to_correlator(
        self,
        site_name: str,
        role: str,
        topic: str,
        line_name: str,
        line_type: str,
        event: Event,
    ) -> bool:
        """Feed `event` to the correlator if it's on `role`'s line.

        Returns whether it was handled.
        """
        if not _matches_configured_line(event, line_type, line_name):
            return False
        timestamp = extract_timestamp(event)
        logger.debug(
            "%s: parsed event: role=%s timestamp=%s event=%r",
            site_name,
            role,
            timestamp,
            event,
        )
        self._on_event(site_name, role, topic, timestamp, event)
        self._correlators[site_name].add(role, timestamp, event)
        return True

    def _route_to_jam(
        self,
        site_name: str,
        jam_name: str | None,
        jam_type: str,
        event: Event,
    ) -> bool:
        """Hand `event` to `on_jam` if it's on the site's jam line.

        Returns whether it was handled.
        """
        if jam_name is None or not _matches_configured_line(
            event, jam_type, jam_name
        ):
            return False
        timestamp = extract_timestamp(event)
        logger.debug(
            "%s: parsed jam-line event: timestamp=%s event=%r",
            site_name,
            timestamp,
            event,
        )
        self._on_jam(site_name, timestamp, event)
        return True

    def _log_pair(
        self, site_name: str, a: Matched[Event], b: Matched[Event]
    ) -> None:
        logger.info(
            "%s: correlated pair: %s@%s <-> %s@%s",
            site_name,
            a.source,
            a.timestamp,
            b.source,
            b.timestamp,
        )

    def _log_unmatched(self, site_name: str, m: Matched[Event]) -> None:
        logger.warning(
            "%s: unmatched event from %s at %s",
            site_name,
            m.source,
            m.timestamp,
        )

    def _log_jam(
        self, site_name: str, timestamp: datetime, _event: Event
    ) -> None:
        logger.info("%s: jam-line event at %s", site_name, timestamp)
