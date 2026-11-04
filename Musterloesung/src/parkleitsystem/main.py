"""Start the parking guidance system: `uv run parkleitsystem`."""

import argparse
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError
from tft_display import Display, PngPreview, TftConfig, open_tft

from parkleitsystem.config import Config, DisplaySettings, load_config
from parkleitsystem.mqtt_link import MqttLink
from parkleitsystem.parking import CarPark, Screen
from parkleitsystem.sign import Sign

logger = logging.getLogger(__name__)

# One round of the main loop, in seconds: well below the 0.5 s blink
# rhythm, so the blinking looks steady, and still no noticeable CPU load.
LOOP_S = 0.1
EXIT_CONFIG_ERROR = 2


class ScreenSink(Protocol):
    """Anything that shows the car park's screen, e.g. the `Sign`."""

    def show(self, screen: Screen) -> None:
        """Show `screen`."""
        ...


def main(argv: list[str] | None = None) -> int:
    """Run until Ctrl+C or SIGTERM (`docker stop`)."""
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    username = os.environ.get("MQTT_USER")
    password = os.environ.get("MQTT_PASSWORD")
    if not username or not password:
        logger.error("set MQTT_USER and MQTT_PASSWORD (broker login)")
        return EXIT_CONFIG_ERROR
    try:
        config = load_config(args.config)
    except (OSError, ValidationError) as err:
        logger.error("%s", err)
        return EXIT_CONFIG_ERROR
    run(config, username=username, password=password, preview=args.preview)
    return 0


def run(
    config: Config, *, username: str, password: str, preview: Path | None
) -> None:
    """Connect MQTT, car park and (optional) sign, then loop until stopped."""
    link = MqttLink(config, username=username, password=password)
    car_park = CarPark(
        config.parking_spaces(),
        link,
        guidance_s=config.entry.guidance_seconds,
    )
    link.forward_events_to(car_park)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    with _open_display(config.display, preview) as display, link:
        sign = Sign(display) if display is not None else None
        try:
            run_loop(car_park, sign, wait=stop.wait)
        except KeyboardInterrupt:
            logger.info("stopped")


def run_loop(
    car_park: CarPark,
    sign: ScreenSink | None,
    *,
    wait: Callable[[float], bool],
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Let the LED blink and update the sign until `wait` returns True.

    `wait(timeout)` blocks up to `timeout` seconds and returns True to stop,
    e.g. `threading.Event().wait`.
    """
    while True:
        now = clock()
        car_park.tick(now=now)
        if sign is not None:
            sign.show(car_park.screen(now=now))
        if wait(LOOP_S):
            return


def _open_display(
    settings: DisplaySettings, preview: Path | None
) -> AbstractContextManager[Display | None]:
    """The TFT, a PNG file instead (--preview), or None without a sign."""
    tft = TftConfig(
        rotation=settings.rotation,
        x_offset=settings.x_offset,
        y_offset=settings.y_offset,
        bgr=settings.bgr,
        invert=settings.invert,
    )
    if preview is not None:
        return nullcontext(PngPreview(preview, size=tft.size))
    if not settings.enabled:
        logger.info("no sign installed ([display] enabled = false)")
        return nullcontext(None)
    return open_tft(tft)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parking guidance: one LED per space, optional sign."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="TOML configuration (default: config.toml)",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        help="write the sign to this PNG file instead of the TFT",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
