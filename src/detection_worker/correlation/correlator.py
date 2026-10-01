"""Correlate events from two MQTT sources by physical crossing order."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class Matched[T]:
    """A single event as seen by the correlator, tagged with its source."""

    source: str
    timestamp: datetime
    event: T


class EventCorrelator[T]:
    """Pairs events from two sources whose timestamps are close together.

    One source is configured as `leading_source` — the one whose device
    physically sits earlier on the road, so its event for a given vehicle
    is expected to occur at or before the other source's ("trailing")
    event for the same vehicle. The oldest still-pending leading event is
    paired with the oldest still-pending trailing event (FIFO on both
    sides, not "nearest timestamp") whenever the trailing one's timestamp
    is within `tolerance` of the leading one's.

    By default (`symmetric=False`) the trailing event must be at or after
    the leading one (`0 <= delay <= tolerance`) — appropriate when the
    physical crossing order is reliable. Set `symmetric=True` to instead
    accept `-tolerance <= delay <= tolerance`, allowing the trailing event
    to arrive up to `tolerance` *before* the leading one too — useful when
    the two devices' measurement points/fields of view can make the
    reported order jitter by a few milliseconds even for the same
    physical pass. This raises the risk of pairing two different vehicles
    when one source (typically the rarer one) misses a reading, so only
    enable it where that trade-off is acceptable for the site.

    Buffers unmatched events per source. A pending event is flushed to
    `on_unmatched` once it can no longer possibly be matched: a pending
    leading event once the trailing source has moved more than
    `tolerance` past it; a pending trailing event once the leading source
    has moved past it at all. Matching and eviction alternate until
    neither makes progress, so evicting a stale head immediately reveals
    whether the new head now matches, rather than waiting for the next
    unrelated event to trigger another look.

    Eviction is event-time driven rather than wall-clock: it only happens
    when `add` is called, so a source that stops sending entirely will leave
    its still-pending events unflushed until the other source sends again.
    A pending event's eviction is driven only by the watermarks of *other*
    sources, so the result never depends on the arrival order of events
    from the same source as the pending event.
    """

    def __init__(
        self,
        tolerance: timedelta,
        leading_source: str,
        on_pair: Callable[[Matched[T], Matched[T]], None],
        on_unmatched: Callable[[Matched[T]], None],
        symmetric: bool = False,
    ) -> None:
        """Create a correlator with the given `tolerance` and callbacks.

        `leading_source` is the name (as passed to `add`) of the source
        that's expected to cross first, e.g. `"bma"`. See the class
        docstring for what `symmetric` changes.
        """
        self._tolerance = tolerance
        self._leading_source = leading_source
        self._on_pair = on_pair
        self._on_unmatched = on_unmatched
        self._symmetric = symmetric
        self._pending: dict[str, list[Matched[T]]] = {}
        self._watermarks: dict[str, datetime] = {}

    def add(self, source: str, timestamp: datetime, event: T) -> None:
        """Feed one event from `source` into the correlator."""
        self._pending.setdefault(source, []).append(
            Matched(source, timestamp, event)
        )
        self._watermarks[source] = max(
            self._watermarks.get(source, timestamp), timestamp
        )
        while self._match_heads() or self._evict_one_stale_head():
            pass

    def _match_heads(self) -> bool:
        """Pair the leading bucket's head with one trailing bucket's head.

        Tries at most one pairing per call: the oldest still-pending
        leading event against the oldest still-pending event of each
        other source in turn, returning as soon as one is within
        tolerance. Returns whether a pairing was made.
        """
        leading_bucket = self._pending.get(self._leading_source)
        if not leading_bucket:
            return False
        for other_source, bucket in self._pending.items():
            if other_source == self._leading_source or not bucket:
                continue
            leading, trailing = leading_bucket[0], bucket[0]
            delay = trailing.timestamp - leading.timestamp
            lower_bound = -self._tolerance if self._symmetric else timedelta(0)
            if lower_bound <= delay <= self._tolerance:
                leading_bucket.pop(0)
                bucket.pop(0)
                logger.debug(
                    "matched: %s@%s <-> %s@%s (within tolerance=%s)",
                    leading.source,
                    leading.timestamp,
                    trailing.source,
                    trailing.timestamp,
                    self._tolerance,
                )
                self._on_pair(leading, trailing)
                return True
        return False

    def _evict_one_stale_head(self) -> bool:
        """Flush one pending head that can no longer possibly be matched.

        Checks each source's bucket head against the other sources'
        watermarks (see `add`) to see if it's provably stale — see the
        cutoff comment below for the leading/trailing distinction (moot in
        `symmetric` mode, where both sides use the widened cutoff). Tries
        at most one eviction per call. Returns whether one was flushed.
        """
        for bucket_source, bucket in self._pending.items():
            if not bucket:
                continue
            other_watermarks = [
                watermark
                for source, watermark in self._watermarks.items()
                if source != bucket_source
            ]
            if not other_watermarks:
                continue
            other_watermark = min(other_watermarks)
            cutoff = (
                other_watermark - self._tolerance
                if self._symmetric or bucket_source == self._leading_source
                else other_watermark
            )
            head = bucket[0]
            if head.timestamp < cutoff:
                bucket.pop(0)
                logger.debug(
                    "evicted as unmatched: %s@%s (cutoff=%s)",
                    head.source,
                    head.timestamp,
                    cutoff,
                )
                self._on_unmatched(head)
                return True
        return False
