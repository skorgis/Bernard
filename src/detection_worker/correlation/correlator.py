"""Correlate events from two MQTT sources by physical crossing order."""

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_MAX_PENDING_AGE = timedelta(minutes=5)
DEFAULT_MAX_PENDING = 10_000


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
    has moved past it at all (more than `tolerance` past it in
    `symmetric` mode). Matching and eviction alternate until neither makes
    progress, so evicting a stale head immediately reveals whether the new
    head now matches, rather than waiting for the next unrelated event to
    trigger another look.

    Stale leading heads are always evicted before stale trailing heads. A
    stale leading head can block the leading event that a trailing head
    would pair with; once it's gone, the new leading head either pairs
    with the trailing head or is provably too late for it. Evicting the
    trailing head first would lose that pair, depending only on which
    source happened to send first.

    Eviction is event-time driven rather than wall-clock: it only happens
    when `add` is called. Because a silent source never advances the
    watermark the other source's events wait on, two limits bound the
    buffers regardless:

    - `max_pending_age`: a pending event is evicted once it's more than
      this much older than the newest event from its *own* source — i.e.
      the other source is assumed never to lag by more than this.
    - `max_pending`: a hard cap on pending events per source; the oldest
      is evicted beyond it.

    Either can be `None` to disable it.
    """

    def __init__(
        self,
        tolerance: timedelta,
        leading_source: str,
        on_pair: Callable[[Matched[T], Matched[T]], None],
        on_unmatched: Callable[[Matched[T]], None],
        symmetric: bool = False,
        max_pending_age: timedelta | None = DEFAULT_MAX_PENDING_AGE,
        max_pending: int | None = DEFAULT_MAX_PENDING,
    ) -> None:
        """Create a correlator with the given `tolerance` and callbacks.

        `leading_source` is the name (as passed to `add`) of the source
        that's expected to cross first, e.g. `"bma"`. See the class
        docstring for what `symmetric`, `max_pending_age` and
        `max_pending` change.
        """
        if max_pending is not None and max_pending < 1:
            raise ValueError(f"max_pending must be at least 1: {max_pending}")
        if max_pending_age is not None and max_pending_age <= tolerance:
            raise ValueError(
                f"max_pending_age ({max_pending_age}) must exceed "
                f"tolerance ({tolerance})"
            )
        self._tolerance = tolerance
        self._leading_source = leading_source
        self._on_pair = on_pair
        self._on_unmatched = on_unmatched
        self._symmetric = symmetric
        self._max_pending_age = max_pending_age
        self._max_pending = max_pending
        self._pending: dict[str, deque[Matched[T]]] = {}
        self._watermarks: dict[str, datetime] = {}

    def add(self, source: str, timestamp: datetime, event: T) -> None:
        """Feed one event from `source` into the correlator."""
        self._pending.setdefault(source, deque()).append(
            Matched(source, timestamp, event)
        )
        self._watermarks[source] = max(
            self._watermarks.get(source, timestamp), timestamp
        )
        while (
            self._match_heads()
            or self._evict_one_stale_head()
            or self._evict_one_over_limit()
        ):
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
                leading_bucket.popleft()
                bucket.popleft()
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
        watermarks, leading source first (see the class docstring for
        why). Tries at most one eviction per call. Returns whether one
        was flushed.
        """
        for bucket_source, bucket in self._buckets_leading_first():
            if not bucket:
                continue
            cutoff = self._stale_cutoff(bucket_source)
            if cutoff is not None and bucket[0].timestamp < cutoff:
                self._evict(bucket, f"stale, cutoff={cutoff}")
                return True
        return False

    def _buckets_leading_first(self) -> list[tuple[str, deque[Matched[T]]]]:
        return sorted(
            self._pending.items(),
            key=lambda item: item[0] != self._leading_source,
        )

    def _stale_cutoff(self, bucket_source: str) -> datetime | None:
        """Timestamp before which `bucket_source`'s events can't match.

        A leading event (or any event in `symmetric` mode) can still pair
        with a trailing event up to `tolerance` later, so its cutoff is
        widened by `tolerance`; a trailing event can't pair with any
        later leading event at all. `None` until another source has sent.
        """
        other_watermarks = [
            watermark
            for source, watermark in self._watermarks.items()
            if source != bucket_source
        ]
        if not other_watermarks:
            return None
        other_watermark = min(other_watermarks)
        if self._symmetric or bucket_source == self._leading_source:
            return other_watermark - self._tolerance
        return other_watermark

    def _evict_one_over_limit(self) -> bool:
        """Flush one pending head beyond `max_pending`/`max_pending_age`.

        Returns whether one was flushed.
        """
        for source, bucket in self._pending.items():
            if not bucket:
                continue
            if (
                self._max_pending is not None
                and len(bucket) > self._max_pending
            ):
                logger.warning(
                    "%s has more than %d pending events; evicting the oldest",
                    source,
                    self._max_pending,
                )
                self._evict(bucket, "max_pending")
                return True
            if (
                self._max_pending_age is not None
                and bucket[0].timestamp
                < self._watermarks[source] - self._max_pending_age
            ):
                self._evict(bucket, "max_pending_age")
                return True
        return False

    def _evict(self, bucket: deque[Matched[T]], reason: str) -> None:
        head = bucket.popleft()
        logger.debug(
            "evicted as unmatched: %s@%s (%s)",
            head.source,
            head.timestamp,
            reason,
        )
        self._on_unmatched(head)
