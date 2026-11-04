"""Build commands that switch the LEDs on the hackathon BMA via MQTT.

Publish the returned dict as JSON on `LED_TOPIC`; bmc-interface on the BMA
then switches the contact. Format and rules: doc/leds-per-mqtt.md.

    import json
    from bmc_leds import LED_TOPIC, led_command

    command = led_command(team="team-1", led=3, on=True)
    client.publish(LED_TOPIC, json.dumps(command), qos=1)
"""

import uuid
from datetime import UTC, datetime

LED_TOPIC = "bmc_interface/tirol-hackathon/out"
# Node id of BMA G-A2610-0007; every BMA event carries it under `node.id`.
HACKATHON_BMA_ID = "f6b51cd4-4469-4138-831a-b5cc471f9e45"
# bmc-interface reserves contacts 11 (health check) and 12 (status output).
FIRST_LED, LAST_LED = 1, 10

__all__ = [
    "FIRST_LED",
    "HACKATHON_BMA_ID",
    "LAST_LED",
    "LED_TOPIC",
    "led_command",
]


def led_command(
    *,
    team: str,
    led: int,
    on: bool,
    duration_s: float | None = None,
    bma_id: str = HACKATHON_BMA_ID,
    now: datetime | None = None,
) -> dict[str, object]:
    """Command that switches LED `led` (1..10) on or off.

    Args:
        team: Your team name (`source_uuid`); the spam limit counts per team.
        led: BMC contact 1..10.
        on: Target state.
        duration_s: With `on=True`: switch on for this many seconds only.
            Without: the LED stays as it is until the next command.
        bma_id: Node id of the BMA running bmc-interface.
        now: Send time in UTC; defaults to now. bmc-interface drops
            commands older than 5 s, so never reuse an event's timestamp.

    Raises:
        ValueError: If `led` is not 1..10 or the pulse is invalid.
    """
    if not FIRST_LED <= led <= LAST_LED:
        raise ValueError(f"LED must be {FIRST_LED}..{LAST_LED}, got {led}")
    contact: dict[str, object] = {
        "id": str(led),
        "type": "permanent",
        "state": "ON" if on else "OFF",
    }
    if duration_s is not None:
        if not on or duration_s <= 0:
            raise ValueError("a pulse duration needs on=True and a value > 0")
        contact.update(type="normal", duration=duration_s)
    return {
        "command_id": str(uuid.uuid4()),
        "target_uuid": bma_id,
        "source_uuid": team,
        "command": "ENABLE",
        # isoformat() of a UTC datetime ends in "+00:00"; bmc-interface
        # does not accept "Z".
        "timestamp": (now or datetime.now(UTC)).isoformat(),
        "contacts": [contact],
    }
