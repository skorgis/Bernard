"""Run the pipeline beside a live display without slowing it down.

Keypoint detection on an HD frame takes far longer than one camera frame
(~160 ms vs. 33 ms). `BackgroundAnalyzer` runs it in a thread on the
newest frame only, so the display keeps the camera's frame rate and the
results lag by at most one analysis. OpenCV releases the GIL while it
works, so the thread really runs in parallel.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from picture_pipeline.image import Image


class BackgroundAnalyzer[T]:
    """Analyzes the most recently submitted frame in a worker thread."""

    def __init__(self, analyze: Callable[[Image], T]) -> None:
        """Start the worker thread; it waits for the first `submit`."""
        self._analyze = analyze
        self._condition = threading.Condition()
        self._pending: Image | None = None
        self._result: T | None = None
        self._error: Exception | None = None
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run, name="background-analyzer", daemon=True
        )
        self._thread.start()

    @property
    def is_running(self) -> bool:
        """Whether the worker thread is still alive."""
        return self._thread.is_alive()

    def submit(self, frame: Image) -> None:
        """Queue `frame`, replacing any frame not yet picked up."""
        with self._condition:
            self._pending = frame
            self._condition.notify()

    def latest(self) -> T | None:
        """The newest result, or `None` before the first one.

        Re-raises the error if an analysis failed.
        """
        with self._condition:
            if self._error is not None:
                raise self._error
            return self._result

    def stop(self) -> None:
        """End the worker thread after its current analysis."""
        with self._condition:
            self._stopped = True
            self._condition.notify()
        self._thread.join()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._pending is not None or self._stopped
                )
                if self._stopped or self._pending is None:
                    return
                frame, self._pending = self._pending, None
            try:
                result = self._analyze(frame)
            except Exception as error:  # noqa: BLE001 - handed to `latest`
                with self._condition:
                    self._error = error
                return
            with self._condition:
                self._result = result


class FpsCounter:
    """Events per second over the last `window` calls to `tick`."""

    def __init__(
        self, window: int = 30, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Measure with `clock` (seconds), averaging over `window` ticks."""
        self._clock = clock
        self._ticks: deque[float] = deque(maxlen=window)

    def tick(self) -> None:
        """Record one event, e.g. a displayed frame."""
        self._ticks.append(self._clock())

    @property
    def fps(self) -> float:
        """The current rate; 0 until two ticks span some time."""
        if len(self._ticks) < 2:
            return 0.0
        span = self._ticks[-1] - self._ticks[0]
        return (len(self._ticks) - 1) / span if span > 0 else 0.0
