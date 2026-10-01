"""An in-memory `MqttClient` for service tests."""

from collections.abc import Callable


class FakeClient:
    """Records the calls a service makes on its MQTT client."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[str] = []
        self.on_connect: Callable[[int], None] | None = None
        self.on_message: Callable[[str, bytes], None] | None = None

    def set_on_message(self, handler: Callable[[str, bytes], None]) -> None:
        """Remember the message handler so tests can deliver messages."""
        self.on_message = handler

    def set_on_connect(self, handler: Callable[[int], None]) -> None:
        """Remember the connect handler so tests can simulate a CONNACK."""
        self.on_connect = handler

    def set_on_disconnect(self, handler: Callable[[int], None]) -> None:
        """Ignore the disconnect handler."""

    def connect(self) -> None:
        """Record the call."""
        self.calls.append("connect")

    def subscribe(self, topic: str, qos: int = 1) -> None:
        """Record the subscribed topic."""
        self.calls.append(f"subscribe:{topic}")

    def unsubscribe(self, topic: str) -> None:
        """Record the unsubscribed topic."""
        self.calls.append(f"unsubscribe:{topic}")

    def loop_start(self) -> None:
        """Record the call."""
        self.calls.append("loop_start")

    def loop_stop(self) -> None:
        """Record the call."""
        self.calls.append("loop_stop")

    def disconnect(self) -> None:
        """Record the call."""
        self.calls.append("disconnect")

    def enable_debug_logging(self) -> None:
        """Record the call."""
        self.calls.append("enable_debug_logging")

    def set_reconnect_delay(self, min_delay: int, max_delay: int) -> None:
        """Ignore the reconnect backoff."""
