"""Tests for the bmc_leds LED command builder."""

from datetime import UTC, datetime

import pytest

from bmc_leds import led_command

NOW = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)


def build(
    led: int = 3, *, on: bool = True, duration_s: float | None = None
) -> dict[str, object]:
    """Command for LED `led` with fixed BMA, team and time."""
    return led_command(
        bma_id="bma-1",
        team="team-x",
        led=led,
        on=on,
        duration_s=duration_s,
        now=NOW,
    )


def test_command_switches_led_permanently_on_and_off() -> None:
    """Without a duration the LED stays as switched."""
    assert build(on=True)["contacts"] == [
        {"id": "3", "type": "permanent", "state": "ON"}
    ]
    assert build(on=False)["contacts"] == [
        {"id": "3", "type": "permanent", "state": "OFF"}
    ]


def test_duration_gives_a_short_pulse() -> None:
    """A duration turns the command into a pulse."""
    assert build(duration_s=2)["contacts"] == [
        {"id": "3", "type": "normal", "state": "ON", "duration": 2}
    ]


def test_command_names_bma_and_team() -> None:
    """BMA and team end up in target_uuid and source_uuid."""
    command = build()

    assert command["command"] == "ENABLE"
    assert command["target_uuid"] == "bma-1"
    assert command["source_uuid"] == "team-x"


def test_timestamp_uses_utc_offset_not_z() -> None:
    """The timestamp ends in +00:00, never in Z."""
    # bmc-interface silently drops timestamps ending in "Z".
    assert build()["timestamp"] == "2026-11-02T09:30:00+00:00"


def test_timestamp_defaults_to_now() -> None:
    """Without `now` the current UTC time is used."""
    before = datetime.now(UTC)

    command = led_command(bma_id="bma-1", team="team-x", led=3, on=True)

    sent = datetime.fromisoformat(str(command["timestamp"]))
    assert before <= sent <= datetime.now(UTC)


def test_every_command_gets_a_new_id() -> None:
    """Each command has its own command_id."""
    assert build()["command_id"] != build()["command_id"]


@pytest.mark.parametrize("led", [0, 11])
def test_led_outside_1_to_10_is_rejected(led: int) -> None:
    """Contacts 11 and 12 are reserved by bmc-interface."""
    with pytest.raises(ValueError, match=r"1\.\.10"):
        build(led)


@pytest.mark.parametrize(
    ("on", "duration_s"), [(False, 2.0), (True, 0.0)], ids=["off", "zero"]
)
def test_pulse_needs_on_and_a_positive_duration(
    on: bool, duration_s: float
) -> None:
    """A pulse must switch on and last longer than 0 s."""
    with pytest.raises(ValueError, match="duration"):
        build(on=on, duration_s=duration_s)
