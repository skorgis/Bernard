"""Load `CorrelatedEventService` configuration from a JSON file."""

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal

from detection_worker.service.multi_site_service import Site
from detection_worker.transport.client import MqttConfig


@dataclass
class MultiSiteServiceConfig:
    """Everything needed to construct and run `MultiSiteCorrelatedService`.

    Unlike `ServiceConfig`/`load_config` below, this isn't loaded from a
    JSON file — it's built from Django settings by the management command
    that runs it.
    """

    mqtt: MqttConfig
    sites: list[Site]
    tolerance: timedelta


@dataclass
class ServiceConfig:
    """Everything needed to construct and run `CorrelatedEventService`."""

    mqtt: MqttConfig
    topic_a: str
    topic_b: str
    tolerance: timedelta
    leading_source: Literal["a", "b"]


def load_config(path: Path | str) -> ServiceConfig:
    """Read and parse a JSON config file into a `ServiceConfig`.

    Expected shape::

        {
          "broker_host": "mqtt.example.com",
          "broker_port": 1883,
          "client_id": "pannenstreifenbus",
          "broker_username": null,
          "broker_password": null,
          "topic_a": "bma/events",
          "topic_b": "bca/events",
          "tolerance_seconds": 1.0,
          "leading_source": "a"
        }

    `leading_source` ("a" or "b") says which topic's event occurs first
    for the same physical crossing; defaults to "a" if omitted.
    """
    data = json.loads(Path(path).read_text())
    mqtt_config = MqttConfig(
        broker_host=data["broker_host"],
        broker_port=data["broker_port"],
        client_id=data["client_id"],
        broker_username=data.get("broker_username"),
        broker_password=data.get("broker_password"),
    )
    return ServiceConfig(
        mqtt=mqtt_config,
        topic_a=data["topic_a"],
        topic_b=data["topic_b"],
        tolerance=timedelta(seconds=data["tolerance_seconds"]),
        leading_source=data.get("leading_source", "a"),
    )
