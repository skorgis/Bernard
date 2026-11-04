"""The broker connection: BMA events in, LED commands out."""

import json
import logging
import time
import zlib
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from bmc_leds import led_command
from detection_worker.data import parse_event
from paho.mqtt.client import Client, ConnectFlags, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from parkleitsystem.config import Config
from parkleitsystem.parking import CarPark

logger = logging.getLogger(__name__)

# QoS 1: the broker confirms receipt, so nothing is lost on a WLAN hiccup.
QOS_AT_LEAST_ONCE = 1

# What parse_event raises for broken input: bad JSON or zlib data
# (ValueError, zlib.error), missing fields (TypeError) or wrong nesting
# (KeyError, AttributeError).
_INVALID_EVENT = (ValueError, TypeError, KeyError, AttributeError, zlib.error)


def forward_message(
    payload: bytes, car_park: CarPark, *, entry_line: str, now: float
) -> None:
    """Pass one BMA event to `car_park`; log and skip invalid messages.

    parse_event also unpacks zlib-compressed events, which the BMA sends
    when compression is enabled for the data transmission.
    """
    try:
        event = parse_event(payload)
    except _INVALID_EVENT as err:
        logger.warning("skipping invalid event: %s", err)
        return

    # Exactly one kind of event is set per message, the others are None.
    zone = event.regionOfInterestEvent
    line = event.crossingLineEvent

    if zone and zone.state in ("occupied", "vacant"):
        car_park.space_reported(zone.roiName, occupied=zone.state == "occupied")

    if line and line.lineName == entry_line and line.direction == "in":
        logger.info("%s entering", line.class_)
        car_park.car_entered(now=now)


class MqttLink:
    """One connection to the broker; use it in a `with` block.

    Subscribes to the BMA events and forwards them to the car park, and
    switches LEDs for it (it is the car park's `Leds`).
    """

    def __init__(self, config: Config, *, username: str, password: str):
        """Prepare the connection; nothing is sent before `with`."""
        self._config = config
        self._car_park: CarPark | None = None
        self._client = Client(
            CallbackAPIVersion.VERSION2, client_id=config.mqtt.client_id
        )
        self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def forward_events_to(self, car_park: CarPark) -> None:
        """Send all following BMA events to `car_park`."""
        self._car_park = car_park

    def switch(self, led: int, on: bool) -> None:
        """Switch LED `led` on or off via bmc-interface on the BMA."""
        command = led_command(
            bma_id=self._config.leds.bma_id,
            team=self._config.leds.team,
            led=led,
            on=on,
            now=datetime.now(UTC),
        )
        logger.info("LED %d %s", led, "on" if on else "off")
        self._client.publish(
            self._config.leds.topic, json.dumps(command), qos=QOS_AT_LEAST_ONCE
        )

    def __enter__(self) -> Self:
        """Connect and start paho's network thread."""
        mqtt = self._config.mqtt
        logger.info("connecting to %s:%d", mqtt.host, mqtt.port)
        self._client.connect(mqtt.host, mqtt.port)
        self._client.loop_start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the network thread and disconnect."""
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(
        self,
        client: Client,
        userdata: object,
        flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        if reason_code.is_failure:
            logger.error("broker refused login: %s", reason_code)
            return
        # Subscribing here, not once after connect(), renews the
        # subscription after every automatic reconnect.
        client.subscribe(self._config.mqtt.event_topic, qos=QOS_AT_LEAST_ONCE)
        logger.info("subscribed to %s", self._config.mqtt.event_topic)

    def _on_message(
        self, client: Client, userdata: object, message: MQTTMessage
    ) -> None:
        if self._car_park is None:
            return
        forward_message(
            message.payload,
            self._car_park,
            entry_line=self._config.entry.line_name,
            now=time.monotonic(),
        )
