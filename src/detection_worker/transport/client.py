"""A thin wrapper around paho-mqtt's client."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from paho.mqtt.client import Client as _PahoClient
from paho.mqtt.client import MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger(__name__)


@dataclass
class MqttConfig:
    """Connection settings for one MQTT broker."""

    broker_host: str
    broker_port: int
    client_id: str
    broker_username: str | None = None
    broker_password: str | None = None
    use_tls: bool = False


class MqttClient(Protocol):
    """The subset of `Client` that consumers of MQTT messages need."""

    def set_on_message(self, handler: Callable[[str, bytes], None]) -> None:
        """Register `handler(topic, payload)`, called for every message."""
        ...

    def set_on_connect(self, handler: Callable[[int], None]) -> None:
        """Register `handler(rc)`, called on (re)connect; rc 0 means success."""
        ...

    def set_on_disconnect(self, handler: Callable[[int], None]) -> None:
        """Register `handler(rc)`, called on disconnect.

        rc 0 means the disconnect was requested by this client (via
        `disconnect()`); non-zero means the broker/network dropped the
        connection unexpectedly, which paho's background loop
        (`loop_start`) will then silently try to reconnect from.
        """
        ...

    def connect(self) -> None:
        """Connect to the configured broker."""
        ...

    def subscribe(self, topic: str, qos: int = 1) -> None:
        """Subscribe to `topic` at the given QoS."""
        ...

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from `topic`."""
        ...

    def loop_start(self) -> None:
        """Start the network loop in a background thread."""
        ...

    def loop_stop(self) -> None:
        """Stop the background network loop started by `loop_start`."""
        ...

    def disconnect(self) -> None:
        """Disconnect from the broker."""
        ...

    def enable_debug_logging(self) -> None:
        """Log paho's own low-level socket/TLS events via `logging`.

        Useful for diagnosing an `on_disconnect` rc whose cause isn't
        obvious from the rc alone — paho logs the underlying error (e.g. a
        TLS alert, or the OS-level socket error) right before it.
        """
        ...

    def set_reconnect_delay(self, min_delay: int, max_delay: int) -> None:
        """Set the reconnect backoff, in seconds.

        Exponential between `min_delay` and `max_delay`, applied by paho
        between automatic reconnects after an unexpected disconnect.
        Useful when a broker-side resource tied to this client's identity
        (e.g. a queue/session keyed by a fixed client id) needs time to be
        released before a new connection reusing that identity can
        succeed — reconnecting too fast can otherwise collide with it,
        causing a rapid disconnect/reconnect loop.
        """
        ...


class Client:
    """A single MQTT connection, wired to one `on_message` handler."""

    def __init__(self, config: MqttConfig) -> None:
        """Create the underlying paho client from `config`."""
        self._config = config
        self._on_message: Callable[[str, bytes], None] | None = None
        self._on_connect: Callable[[int], None] | None = None
        self._on_disconnect: Callable[[int], None] | None = None
        self._client = _PahoClient(
            CallbackAPIVersion.VERSION1, config.client_id
        )
        self._client.on_message = self._handle_message
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        if config.use_tls:
            self._client.tls_set()
        if config.broker_username:
            self._client.username_pw_set(
                config.broker_username, config.broker_password
            )

    def set_on_message(self, handler: Callable[[str, bytes], None]) -> None:
        """Register `handler(topic, payload)`, called for every message."""
        self._on_message = handler

    def set_on_connect(self, handler: Callable[[int], None]) -> None:
        """Register `handler(rc)`, called on (re)connect; rc 0 means success."""
        self._on_connect = handler

    def set_on_disconnect(self, handler: Callable[[int], None]) -> None:
        """Register `handler(rc)`, called on disconnect.

        rc 0 means the disconnect was requested by this client (via
        `disconnect()`); non-zero means the broker/network dropped the
        connection unexpectedly, which paho's background loop
        (`loop_start`) will then silently try to reconnect from.
        """
        self._on_disconnect = handler

    def connect(self) -> None:
        """Connect to the broker configured in `MqttConfig`."""
        self._client.connect(self._config.broker_host, self._config.broker_port)

    def subscribe(self, topic: str, qos: int = 1) -> None:
        """Subscribe to `topic` at the given QoS."""
        self._client.subscribe(topic, qos)

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from `topic`."""
        self._client.unsubscribe(topic)

    def loop_start(self) -> None:
        """Start the network loop in a background thread."""
        self._client.loop_start()

    def loop_stop(self) -> None:
        """Stop the background network loop started by `loop_start`."""
        self._client.loop_stop()

    def disconnect(self) -> None:
        """Disconnect from the broker."""
        self._client.disconnect()

    def enable_debug_logging(self) -> None:
        """Log paho's own low-level socket/TLS events via `logging`.

        Useful for diagnosing an `on_disconnect` rc whose cause isn't
        obvious from the rc alone — paho logs the underlying error (e.g. a
        TLS alert, or the OS-level socket error) right before it.
        """
        self._client.enable_logger()

    def set_reconnect_delay(self, min_delay: int, max_delay: int) -> None:
        """Set the reconnect backoff, in seconds.

        Exponential between `min_delay` and `max_delay`, applied by paho
        between automatic reconnects after an unexpected disconnect.
        Useful when a broker-side resource tied to this client's identity
        (e.g. a queue/session keyed by a fixed client id) needs time to be
        released before a new connection reusing that identity can
        succeed — reconnecting too fast can otherwise collide with it,
        causing a rapid disconnect/reconnect loop.
        """
        self._client.reconnect_delay_set(
            min_delay=min_delay, max_delay=max_delay
        )

    def _handle_message(self, _client, _userdata, message: MQTTMessage) -> None:
        logger.debug(
            "raw message received: topic=%s payload=%d bytes: %r",
            message.topic,
            len(message.payload),
            message.payload,
        )
        if self._on_message is None:
            return
        # paho re-raises callback exceptions out of its network loop, which
        # kills `loop_start`'s thread for good — so one bad message would
        # silently stop all further delivery.
        try:
            self._on_message(message.topic, message.payload)
        except Exception:
            logger.exception(
                "failed to handle message on %s; skipping it", message.topic
            )

    def _handle_connect(self, _client, _userdata, _flags, rc: int) -> None:
        if self._on_connect is not None:
            self._on_connect(rc)

    def _handle_disconnect(self, _client, _userdata, rc: int) -> None:
        if self._on_disconnect is not None:
            self._on_disconnect(rc)
