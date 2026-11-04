"""The main loop: drive the blinking LED and, if installed, the sign."""

import time
from collections.abc import Callable
from typing import Protocol

from parkleitsystem.guide import ParkingGuide
from parkleitsystem.screens import Screen

# Loop period in seconds: well below the 0.5 s blink half period, so the
# blink rhythm looks steady, and still negligible CPU load.
REFRESH_S = 0.1


class ScreenSink(Protocol):
    """Something that shows the guide's screen, e.g. the entry sign."""

    def show(self, screen: Screen) -> None:
        """Show `screen`."""
        ...


def run_main_loop(
    guide: ParkingGuide,
    sign: ScreenSink | None,
    *,
    wait: Callable[[float], bool],
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Tick `guide` and update `sign` (if any) until `wait` returns True.

    `wait(timeout)` blocks for up to `timeout` seconds and returns True to
    stop, e.g. `threading.Event().wait`.
    """
    while True:
        now = clock()
        guide.tick(now=now)
        if sign is not None:
            sign.show(guide.screen(now=now))
        if wait(REFRESH_S):
            return
