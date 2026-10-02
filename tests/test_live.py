"""Tests for running the pipeline beside a live display."""

import threading
import time

import numpy as np
import pytest

from picture_pipeline.image import Image
from picture_pipeline.live import BackgroundAnalyzer, FpsCounter

_TIMEOUT = 2.0


def _frame(value: int) -> Image:
    return np.full((2, 2), value, dtype=np.uint8)


def _wait_for(condition) -> None:
    deadline = time.monotonic() + _TIMEOUT
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.001)


def test_no_result_before_the_first_frame_is_analyzed() -> None:
    """`latest` is `None` until something was analyzed."""
    analyzer = BackgroundAnalyzer(lambda frame: int(frame[0, 0]))
    try:
        assert analyzer.latest() is None
    finally:
        analyzer.stop()


def test_latest_returns_the_result_for_a_submitted_frame() -> None:
    """The analysis runs in the background and its result shows up."""
    analyzer = BackgroundAnalyzer(lambda frame: int(frame[0, 0]))
    try:
        analyzer.submit(_frame(7))
        _wait_for(lambda: analyzer.latest() == 7)
    finally:
        analyzer.stop()


def test_frames_submitted_while_busy_are_skipped_except_the_newest() -> None:
    """A slow analysis never falls behind: stale frames are dropped."""
    started = threading.Event()
    release = threading.Event()
    analyzed: list[int] = []

    def slow(frame: Image) -> int:
        started.set()
        release.wait(_TIMEOUT)
        analyzed.append(int(frame[0, 0]))
        return analyzed[-1]

    analyzer = BackgroundAnalyzer(slow)
    try:
        analyzer.submit(_frame(1))
        assert started.wait(_TIMEOUT)
        analyzer.submit(_frame(2))
        analyzer.submit(_frame(3))
        release.set()
        _wait_for(lambda: analyzer.latest() == 3)
    finally:
        analyzer.stop()

    assert analyzed == [1, 3]


def test_an_analysis_error_is_raised_by_latest() -> None:
    """A failing analysis doesn't die silently in its thread."""

    def broken(_image: Image) -> int:
        raise RuntimeError("detector exploded")

    analyzer = BackgroundAnalyzer(broken)
    try:
        analyzer.submit(_frame(1))
        with pytest.raises(RuntimeError, match="exploded"):
            _wait_for(lambda: analyzer.latest() is not None)
    finally:
        analyzer.stop()


def test_stop_ends_the_thread() -> None:
    """After `stop`, the worker thread is gone."""
    analyzer = BackgroundAnalyzer(lambda _image: 0)
    analyzer.stop()
    assert not analyzer.is_running


def test_fps_counter_measures_the_tick_rate() -> None:
    """Ten ticks 0.1 s apart are 10 per second."""
    now = [0.0]
    counter = FpsCounter(clock=lambda: now[0])
    for _ in range(10):
        now[0] += 0.1
        counter.tick()

    assert counter.fps == pytest.approx(10.0)


def test_fps_counter_is_zero_before_two_ticks() -> None:
    """A rate needs at least one interval."""
    counter = FpsCounter(clock=lambda: 0.0)
    counter.tick()
    assert counter.fps == 0.0
