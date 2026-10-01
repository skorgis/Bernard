"""Tests for the `detection-worker` command-line entry point."""

from datetime import timedelta
from pathlib import Path

import pytest

from detection_worker.cli import parse_args, run
from detection_worker.config import ServiceConfig
from detection_worker.transport.client import MqttConfig
from tests.fake_mqtt_client import FakeClient


def _config() -> ServiceConfig:
    return ServiceConfig(
        mqtt=MqttConfig("localhost", 1883, "test"),
        topic_a="bma/events",
        topic_b="bca/events",
        tolerance=timedelta(seconds=1),
        leading_source="a",
    )


def test_parse_args_reads_config_path_and_defaults_log_level() -> None:
    """parse_args() reads the config path; log level defaults to INFO."""
    args = parse_args(["worker.json"])
    assert args.config == Path("worker.json")
    assert args.log_level == "INFO"


def test_parse_args_reads_log_level() -> None:
    """parse_args() accepts an explicit --log-level."""
    args = parse_args(["worker.json", "--log-level", "DEBUG"])
    assert args.log_level == "DEBUG"


def test_run_subscribes_both_topics_on_connect() -> None:
    """run() subscribes to both configured topics once connected."""
    client = FakeClient()

    def wait() -> None:
        assert client.on_connect is not None
        client.on_connect(0)

    run(_config(), client, wait)

    assert "subscribe:bma/events" in client.calls
    assert "subscribe:bca/events" in client.calls


def test_run_starts_then_stops_client() -> None:
    """run() connects and starts the loop, then stops and disconnects."""
    client = FakeClient()
    run(_config(), client, wait=lambda: None)
    assert client.calls == ["connect", "loop_start", "loop_stop", "disconnect"]


def test_run_stops_client_on_keyboard_interrupt() -> None:
    """run() treats Ctrl+C as a clean shutdown and still disconnects."""
    client = FakeClient()

    def wait() -> None:
        raise KeyboardInterrupt

    run(_config(), client, wait)
    assert client.calls[-2:] == ["loop_stop", "disconnect"]


def test_run_stops_client_on_system_exit() -> None:
    """run() disconnects on SIGTERM-triggered SystemExit, then re-raises."""
    client = FakeClient()

    def wait() -> None:
        raise SystemExit(0)

    with pytest.raises(SystemExit):
        run(_config(), client, wait)
    assert client.calls[-2:] == ["loop_stop", "disconnect"]
