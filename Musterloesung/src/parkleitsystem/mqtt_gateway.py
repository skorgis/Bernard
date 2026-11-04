"""One broker connection: BMA events in, LED commands out."""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from detection_worker.dispatch import EventDispatcher
from paho.mqtt.client import Client, ConnectFlags, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from parkleitsystem.config import LedSettings, MqttSettings
from parkleitsystem.events import handle_payload
from parkleitsystem.led_command import build_led_command

logger = logging.getLogger(__name__)

# QoS 1: the broker acknowledges receipt, so no event or command is lost
# on a short WLAN hiccup.
QOS_AT_LEAST_ONCE = 1


class MqttGateway:
    """Subscribes to BMA events and publishes LED commands.

    Implements the guide's `LedSwitch`. Use as a context manager: the
    connection is opened on enter and closed on exit; paho reconnects by
    itself in between.
    """

    def __init__(
        self,
        mqtt: MqttSettings,
        leds: LedSettings,
        dispatcher: EventDispatcher,
        *,
        username: str,
        password: str,
        utc_now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Prepare the connection; nothing is sent before `__enter__`."""
        self._mqtt = mqtt
        self._leds = leds
        self._dispatcher = dispatcher
        self._utc_now = utc_now
        self._client = Client(
            CallbackAPIVersion.VERSION2, client_id=mqtt.client_id
        )
        self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def __enter__(self) -> Self:
        """Connect and start paho's network thread."""
        logger.info("connecting to %s:%d", self._mqtt.host, self._mqtt.port)
        self._client.connect(self._mqtt.host, self._mqtt.port)
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

    def switch(self, contact: int, on: bool) -> None:
        """Latch LED `contact` on or off via bmc-interface."""
        command = build_led_command(
            target_uuid=self._leds.bma_id,
            team=self._leds.team,
            contact=contact,
            on=on,
            now=self._utc_now(),
        )
        logger.info("LED %d %s", contact, "on" if on else "off")
        self._client.publish(
            self._leds.topic, json.dumps(command), qos=QOS_AT_LEAST_ONCE
        )

    def _on_connect(
        self,
        client: Client,
        userdata: object,
        flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        if reason_code.is_failure:
            logger.error(
                "broker refused connection: %s (check MQTT_USER/MQTT_PASSWORD)",
                reason_code,
            )
            return
        # Subscribing here, not once after connect(), renews the
        # subscription after every automatic reconnect.
        client.subscribe(self._mqtt.event_topic, qos=QOS_AT_LEAST_ONCE)
        logger.info("subscribed to %s", self._mqtt.event_topic)

    def _on_message(
        self, client: Client, userdata: object, message: MQTTMessage
    ) -> None:
        handle_payload(self._dispatcher, message.topic, message.payload)
