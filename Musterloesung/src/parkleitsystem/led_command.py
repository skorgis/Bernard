"""bmc-interface command that latches one LED (see doc/leds-per-mqtt.md)."""

import uuid
from datetime import datetime

# bmc-interface reserves contacts 11 (health check) and 12 (status output).
MIN_LED_CONTACT = 1
MAX_LED_CONTACT = 10


def build_led_command(
    *, target_uuid: str, team: str, contact: int, on: bool, now: datetime
) -> dict[str, object]:
    """Command switching `contact` permanently on or off.

    Args:
        target_uuid: Node id of the BMA running bmc-interface.
        team: Sender name (`source_uuid`); the spam limit counts per team.
        contact: LED contact 1..10.
        on: Target state.
        now: Send time, timezone-aware UTC. bmc-interface drops commands
            older than 5 s, so never reuse an event's timestamp.

    Raises:
        ValueError: If `contact` is not an LED contact.
    """
    if not MIN_LED_CONTACT <= contact <= MAX_LED_CONTACT:
        raise ValueError(
            f"contact must be {MIN_LED_CONTACT}..{MAX_LED_CONTACT}, "
            f"got {contact}"
        )
    return {
        "command_id": str(uuid.uuid4()),
        "target_uuid": target_uuid,
        "source_uuid": team,
        "command": "ENABLE",
        # isoformat() of an aware UTC datetime ends in "+00:00", the only
        # suffix bmc-interface accepts.
        "timestamp": now.isoformat(),
        "contacts": [
            {
                "id": str(contact),
                "type": "permanent",
                "state": "ON" if on else "OFF",
            }
        ],
    }
