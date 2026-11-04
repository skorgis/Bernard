"""The display loop: keep the TFT in line with the guide's screen."""

import logging
import time
from collections.abc import Callable

from tft_display import Display

from parkleitsystem.guide import ParkingGuide
from parkleitsystem.rendering import render
from parkleitsystem.screens import Screen

logger = logging.getLogger(__name__)

# How often the screen is checked, in seconds: fast enough that a car sees
# its arrow at once, slow enough to cost no noticeable CPU.
REFRESH_S = 0.2


def run_sign(
    guide: ParkingGuide,
    display: Display,
    *,
    wait: Callable[[float], bool],
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Redraw `display` whenever the screen changes, until `wait` is True.

    `wait(timeout)` blocks for up to `timeout` seconds and returns True to
    stop, e.g. `threading.Event().wait`. Redrawing only on change avoids
    flicker and sending 40 kB over SPI five times a second.
    """
    shown: Screen | None = None
    while True:
        screen = guide.screen(now=clock())
        if screen != shown:
            logger.info("sign: %s", screen)
            display.display(render(screen, display.size))
            shown = screen
        if wait(REFRESH_S):
            return
