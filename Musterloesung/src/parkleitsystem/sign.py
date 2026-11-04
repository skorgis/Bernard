"""The entry sign: draw a screen on the TFT when it changes."""

import logging

from tft_display import Display

from parkleitsystem.rendering import render
from parkleitsystem.screens import Screen

logger = logging.getLogger(__name__)


class Sign:
    """Shows screens on a display, redrawing only when the screen changes.

    Redrawing only on change avoids flicker and sending 40 kB over SPI on
    every loop iteration.
    """

    def __init__(self, display: Display) -> None:
        """Draw on `display`."""
        self._display = display
        self._shown: Screen | None = None

    def show(self, screen: Screen) -> None:
        """Display `screen` unless it is already shown."""
        if screen == self._shown:
            return
        logger.info("sign: %s", screen)
        self._display.display(render(screen, self._display.size))
        self._shown = screen
