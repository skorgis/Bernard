"""Switch a BMC contact (e.g. an LED) on the hackathon BMA via MQTT.

The command goes to the Mosquitto broker on the hackathon Raspberry Pi;
bmc-interface on the BMA picks it up over the LAN cable and switches the
contact. Broker credentials come from the same environment variables as in
the project README (MQTT_HOST is optional, default hackathon.local):

    export MQTT_USER=hackathon MQTT_PASSWORD=...

    uv run python examples/bmc_mqtt_switch.py --team team-1 --contact 3 --on
    uv run python examples/bmc_mqtt_switch.py --team team-1 --contact 3 --off
    uv run python examples/bmc_mqtt_switch.py --team team-1 --contact 3 \
        --on --duration 2

Without `--duration` the contact latches ("permanent"); with it, the contact
is pulsed ("normal") and bmc-interface switches it off again by itself.
See `doc/leds-per-mqtt.md` for the command format and limits.
"""

import argparse
import json
import logging
import os
import sys
import threading
import uuid
from datetime import UTC, datetime

from paho.mqtt.client import Client, ConnectFlags
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

logger = logging.getLogger(__name__)

# mDNS name of the hackathon Pi; its WLAN address comes from DHCP and changes.
DEFAULT_HOST = "hackathon.local"
# Node id of BMA G-A2610-0007, read from its urban_traffic_config.json.
DEFAULT_TARGET_UUID = "f6b51cd4-4469-4138-831a-b5cc471f9e45"
DEFAULT_PORT = 1883  # plain MQTT; the Pi broker has no TLS listener
CONNECT_TIMEOUT_S = 10
DEFAULT_TOPIC = "bmc_interface/tirol-hackathon/out"
# bmc-interface reserves contacts 11 (health check) and 12 (status output).
MAX_LED_CONTACT = 10
# QoS 1: the broker acknowledges receipt, so a sent command is not lost.
QOS_AT_LEAST_ONCE = 1


def build_command(
    *,
    target_uuid: str,
    source_uuid: str,
    contact: int,
    on: bool,
    duration_s: float | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build a bmc-interface command that switches one contact.

    Args:
        target_uuid: Node id of the BMA running bmc-interface.
        source_uuid: Sender id; bmc-interface rate-limits per sender.
        contact: Contact number 1..10.
        on: Target state.
        duration_s: Pulse length; only valid with `on=True`.
        now: Timestamp to send; defaults to the current UTC time.

    Raises:
        ValueError: On an invalid contact or duration combination.
    """
    if not 1 <= contact <= MAX_LED_CONTACT:
        raise ValueError(f"contact must be 1..{MAX_LED_CONTACT}, got {contact}")
    if duration_s is not None and (not on or duration_s <= 0):
        raise ValueError("duration requires --on and a positive value")

    entry: dict[str, object] = {
        "id": str(contact),
        "type": "permanent" if duration_s is None else "normal",
        "state": "ON" if on else "OFF",
    }
    if duration_s is not None:
        entry["duration"] = duration_s
    return {
        "command_id": str(uuid.uuid4()),
        "target_uuid": target_uuid,
        "source_uuid": source_uuid,
        "command": "ENABLE",
        "timestamp": (now or datetime.now(UTC)).isoformat(),
        "contacts": [entry],
    }


def publish(command: dict[str, object], args: argparse.Namespace) -> None:
    """Send `command` to the broker and wait for its acknowledgement."""
    client = Client(CallbackAPIVersion.VERSION2)
    client.username_pw_set(
        _require_env("MQTT_USER"), _require_env("MQTT_PASSWORD")
    )
    connack = _ConnackWaiter(client)
    client.connect(args.host, args.port)
    client.loop_start()
    try:
        connack.raise_unless_accepted()
        info = client.publish(
            args.topic, json.dumps(command), qos=QOS_AT_LEAST_ONCE
        )
        info.wait_for_publish(timeout=10)
        if not info.is_published():
            raise TimeoutError(
                f"Broker did not acknowledge within 10 s ({info.rc})"
            )
    finally:
        client.loop_stop()
        client.disconnect()


class _ConnackWaiter:
    """Waits for the broker's answer to CONNECT.

    `connect()` returns before the broker has checked the credentials; a
    rejected login only arrives later as CONNACK in the network thread.
    """

    def __init__(self, client: Client) -> None:
        self._answered = threading.Event()
        self._reason: ReasonCode | None = None
        client.on_connect = self._on_connect

    def _on_connect(
        self,
        client: Client,
        userdata: object,
        flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        self._reason = reason_code
        self._answered.set()

    def raise_unless_accepted(self) -> None:
        if not self._answered.wait(CONNECT_TIMEOUT_S):
            raise TimeoutError(
                f"No answer from broker within {CONNECT_TIMEOUT_S} s"
            )
        if self._reason is not None and self._reason.is_failure:
            raise ConnectionError(
                f"Broker refused connection: {self._reason} "
                "(check MQTT_USER/MQTT_PASSWORD)"
            )


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Environment variable {name} is not set")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Switch a BMC contact via MQTT."
    )
    parser.add_argument(
        "--contact", type=int, required=True, help=f"1..{MAX_LED_CONTACT}"
    )
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--on", action="store_true", dest="on")
    state.add_argument("--off", action="store_false", dest="on")
    parser.add_argument(
        "--duration", type=float, help="pulse length in seconds (with --on)"
    )
    parser.add_argument(
        "--team",
        required=True,
        help="your team name (source_uuid); the spam limit counts per team",
    )
    parser.add_argument(
        "--host", default=os.environ.get("MQTT_HOST", DEFAULT_HOST)
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument(
        "--bma", default=DEFAULT_TARGET_UUID, help="node id of the BMA"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Send one switch command."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        command = build_command(
            target_uuid=args.bma,
            source_uuid=args.team,
            contact=args.contact,
            on=args.on,
            duration_s=args.duration,
        )
    except ValueError as err:
        logger.error("%s", err)
        return 2
    publish(command, args)
    logger.info("Sent to %s: %s", args.topic, json.dumps(command))
    return 0


if __name__ == "__main__":
    sys.exit(main())
