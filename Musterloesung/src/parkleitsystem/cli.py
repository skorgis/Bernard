"""Command line entry point: wire configuration, MQTT, guide and sign."""

import argparse
import logging
import os
import signal
import sys
import threading
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from detection_worker.dispatch import EventDispatcher
from pydantic import ValidationError
from tft_display import Display, PngPreview, TftConfig, open_tft

from parkleitsystem.config import AppConfig, DisplaySettings, load_config
from parkleitsystem.domain import ParkingLot
from parkleitsystem.events import register_handlers
from parkleitsystem.guide import ParkingGuide
from parkleitsystem.mqtt_gateway import MqttGateway
from parkleitsystem.sign import run_sign

logger = logging.getLogger(__name__)

EXIT_CONFIG_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    """Run the parking guidance system until Ctrl+C or SIGTERM."""
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        config = load_config(args.config)
        username, password = _credentials()
    except (OSError, ValidationError, _MissingCredentialsError) as err:
        logger.error("%s", err)
        return EXIT_CONFIG_ERROR
    run(config, username=username, password=password, preview=args.preview)
    return 0


def run(
    config: AppConfig, *, username: str, password: str, preview: Path | None
) -> None:
    """Connect everything and drive the sign until a stop signal."""
    dispatcher = EventDispatcher()
    gateway = MqttGateway(
        config.mqtt,
        config.leds,
        dispatcher,
        username=username,
        password=password,
    )
    guide = ParkingGuide(
        ParkingLot(config.parking_spaces()),
        gateway,
        guidance_s=config.entry.guidance_seconds,
    )
    register_handlers(
        dispatcher,
        topic=config.mqtt.event_topic,
        entry=config.entry,
        space_names=[space.roi_name for space in config.spaces],
        guide=guide,
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    with _open_sign(config.display, preview) as display, gateway:
        try:
            run_sign(guide, display, wait=stop.wait)
        except KeyboardInterrupt:
            logger.info("stopped")


def _open_sign(
    settings: DisplaySettings, preview: Path | None
) -> AbstractContextManager[Display]:
    tft = TftConfig(
        rotation=settings.rotation,
        x_offset=settings.x_offset,
        y_offset=settings.y_offset,
        bgr=settings.bgr,
        invert=settings.invert,
    )
    if preview is not None:
        return nullcontext(PngPreview(preview, size=tft.size))
    return open_tft(tft)


class _MissingCredentialsError(Exception):
    """MQTT_USER or MQTT_PASSWORD is not set."""


def _credentials() -> tuple[str, str]:
    username = os.environ.get("MQTT_USER")
    password = os.environ.get("MQTT_PASSWORD")
    if not username or not password:
        raise _MissingCredentialsError(
            "set MQTT_USER and MQTT_PASSWORD (broker login from the "
            "supervisors)"
        )
    return username, password


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parking guidance: arrow on the TFT, one LED per space."
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
