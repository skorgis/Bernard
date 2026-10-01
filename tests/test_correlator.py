"""Tests for `EventCorrelator`: pairing, eviction and buffer limits."""

from datetime import datetime, timedelta

import pytest

from detection_worker.correlation.correlator import EventCorrelator

T0 = datetime(2026, 10, 1, 12, 0, 0)
TOLERANCE = timedelta(seconds=1)

type Feed = list[tuple[str, float, str]]


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


class Recorder:
    """Collects the correlator's output as readable strings."""

    def __init__(self) -> None:
        """Start with no output."""
        self.output: list[str] = []

    def correlator(self, **options: object) -> EventCorrelator[str]:
        """Build a BMA-leading correlator that reports into `output`."""
        return EventCorrelator[str](
            tolerance=TOLERANCE,
            leading_source="bma",
            on_pair=lambda a, b: self.output.append(
                f"pair {a.event}<->{b.event}"
            ),
            on_unmatched=lambda m: self.output.append(f"unmatched {m.event}"),
            **options,  # type: ignore[arg-type]
        )


def _run(feed: Feed, **options: object) -> list[str]:
    recorder = Recorder()
    correlator = recorder.correlator(**options)
    for source, seconds, event in feed:
        correlator.add(source, _at(seconds), event)
    return recorder.output


# --- pairing ------------------------------------------------------------------


def test_pairs_trailing_event_within_tolerance() -> None:
    """A trailing event up to `tolerance` after the leading one pairs."""
    assert _run([("bma", 0, "L"), ("bca", 0.3, "T")]) == ["pair L<->T"]


def test_pairs_regardless_of_which_source_arrives_first() -> None:
    """Arrival order of a single pair doesn't matter."""
    assert _run([("bca", 0.3, "T"), ("bma", 0, "L")]) == ["pair L<->T"]


def test_pairs_fifo_on_both_sides() -> None:
    """Oldest pending leading event pairs with oldest pending trailing."""
    feed: Feed = [
        ("bma", 0.0, "L1"),
        ("bma", 0.2, "L2"),
        ("bca", 0.5, "T1"),
        ("bca", 0.7, "T2"),
    ]
    assert _run(feed) == ["pair L1<->T1", "pair L2<->T2"]


def test_strict_mode_rejects_trailing_event_before_leading() -> None:
    """Strict mode: a trailing event before the leading one is unmatched."""
    output = _run([("bma", 0.3, "L"), ("bca", 0, "T"), ("bca", 5, "T2")])
    assert "pair L<->T" not in output
    assert output[0] == "unmatched T"


def test_symmetric_mode_accepts_trailing_event_before_leading() -> None:
    """With `symmetric`, the trailing event may precede the leading one."""
    output = _run([("bma", 0.3, "L"), ("bca", 0, "T")], symmetric=True)
    assert output == ["pair L<->T"]


# --- eviction by the other source's watermark ---------------------------------


def test_evicts_leading_event_once_trailing_moves_past_tolerance() -> None:
    """A leading event is unmatched once trailing is beyond `tolerance`."""
    output = _run([("bma", 0, "L"), ("bca", 1.5, "T")])
    assert output == ["unmatched L"]


def test_keeps_leading_event_while_trailing_still_within_tolerance() -> None:
    """A leading event stays pending while a match is still possible."""
    assert _run([("bma", 0, "L"), ("bca", 0.9, "T"), ("bca", 0.95, "T2")]) == [
        "pair L<->T"
    ]


@pytest.mark.parametrize("symmetric", [False, True])
def test_result_does_not_depend_on_which_source_sent_first(
    symmetric: bool,
) -> None:
    """Regression: a stale leading head must not cost a trailing match.

    L1 is long stale, L2 is T1's real partner, L3 has already moved the
    leading watermark more than `tolerance` past T1 (so the bug shows in
    symmetric mode too). Evicting T1 before L1 used to lose the L2<->T1
    pair whenever the trailing source happened to send first.
    """
    tail: Feed = [
        ("bma", -5, "L1"),
        ("bma", 0.1, "L2"),
        ("bma", 1.5, "L3"),
        ("bca", 0.3, "T1"),
    ]
    trailing_first = _run([("bca", -10, "T0"), *tail], symmetric=symmetric)
    leading_first = _run(
        [("bma", -20, "L0"), ("bca", -10, "T0"), *tail], symmetric=symmetric
    )

    assert "pair L2<->T1" in trailing_first
    assert "pair L2<->T1" in leading_first
    assert "unmatched T1" not in trailing_first


# --- buffer limits ------------------------------------------------------------


def test_max_pending_age_evicts_while_partner_is_silent() -> None:
    """A silent partner no longer makes the other source's buffer grow."""
    feed: Feed = [("bma", 0, "L0"), ("bca", 0.3, "T0")]
    feed += [("bma", float(second), f"L{second}") for second in range(1, 101)]

    output = _run(feed, max_pending_age=timedelta(seconds=10))

    unmatched = [line for line in output if line.startswith("unmatched")]
    assert unmatched == [f"unmatched L{second}" for second in range(1, 90)]


def test_max_pending_age_applies_when_partner_never_sent() -> None:
    """Age eviction also works before the other source sent anything."""
    feed: Feed = [("bma", float(second), f"L{second}") for second in range(20)]

    output = _run(feed, max_pending_age=timedelta(seconds=10))

    assert output == [f"unmatched L{second}" for second in range(9)]


def test_caps_pending_events_per_source() -> None:
    """Beyond `max_pending`, the oldest pending event is evicted."""
    feed: Feed = [("bma", float(second), f"L{second}") for second in range(5)]

    output = _run(feed, max_pending=3, max_pending_age=None)

    assert output == ["unmatched L0", "unmatched L1"]


def test_limits_can_be_disabled() -> None:
    """`None` disables each limit, restoring purely watermark eviction."""
    feed: Feed = [("bma", float(second), f"L{second}") for second in range(50)]

    assert _run(feed, max_pending=None, max_pending_age=None) == []


@pytest.mark.parametrize(
    "options",
    [
        {"max_pending": 0},
        {"max_pending_age": timedelta(0)},
        {"max_pending_age": TOLERANCE},
    ],
    ids=["max_pending=0", "max_pending_age=0", "max_pending_age=tolerance"],
)
def test_rejects_limits_that_would_evict_matchable_events(
    options: dict[str, object],
) -> None:
    """Limits must leave room for at least one event within `tolerance`."""
    with pytest.raises(ValueError):
        Recorder().correlator(**options)
