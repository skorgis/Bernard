from datetime import UTC, datetime

import pytest

from parkleitsystem.led_command import build_led_command

NOW = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)


def build(contact: int = 3, *, on: bool = True) -> dict[str, object]:
    return build_led_command(
        target_uuid="bma-1", team="team-x", contact=contact, on=on, now=NOW
    )


def test_command_latches_contact_on() -> None:
    command = build(on=True)

    assert command["command"] == "ENABLE"
    assert command["target_uuid"] == "bma-1"
    assert command["source_uuid"] == "team-x"
    assert command["contacts"] == [
        {"id": "3", "type": "permanent", "state": "ON"}
    ]


def test_command_switches_contact_off() -> None:
    assert build(on=False)["contacts"] == [
        {"id": "3", "type": "permanent", "state": "OFF"}
    ]


def test_timestamp_uses_utc_offset_not_z() -> None:
    # bmc-interface silently drops timestamps ending in "Z".
    assert build()["timestamp"] == "2026-11-02T09:30:00+00:00"


def test_every_command_gets_a_new_id() -> None:
    assert build()["command_id"] != build()["command_id"]


@pytest.mark.parametrize("contact", [0, 11])
def test_contact_outside_led_range_is_rejected(contact: int) -> None:
    with pytest.raises(ValueError, match=r"1\.\.10"):
        build(contact)
