"""`detection-worker` command: run `CorrelatedEventService` from a JSON file."""

import argparse
import logging
import signal
import sys
from collections.abc import Callable
from pathlib import Path

from detection_worker.config import ServiceConfig, load_config
from detection_worker.service.correlated_service import CorrelatedEventService
from detection_worker.transport.client import Client, MqttClient

_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list to parse. Defaults to `sys.argv[1:]`.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Correlate events from two MQTT topics."
    )
    parser.add_argument(
        "config", type=Path, help="Path to the JSON service config."
    )
    parser.add_argument(
        "--log-level", choices=_LOG_LEVELS, default="INFO", help="Log level."
    )
    return parser.parse_args(argv)


def run(
    config: ServiceConfig, client: MqttClient, wait: Callable[[], None]
) -> None:
    """Run the service on `client` until `wait` returns or is interrupted.

    Ctrl+C ends the run cleanly; the client is always stopped and
    disconnected, whatever ends `wait`.
    """
    service = CorrelatedEventService(
        client=client,
        topic_a=config.topic_a,
        topic_b=config.topic_b,
        tolerance=config.tolerance,
        leading_source=config.leading_source,
    )
    service.start()
    try:
        wait()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


def main(argv: list[str] | None = None) -> None:
    """Run the command-line interface.

    Args:
        argv: Argument list to parse. Defaults to `sys.argv[1:]`.
    """
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    client = Client(config.mqtt)
    if args.log_level == "DEBUG":
        client.enable_debug_logging()
    # Turn SIGTERM (e.g. `docker stop`) into SystemExit so `run` disconnects.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    run(config, client, signal.pause)


if __name__ == "__main__":
    main()
