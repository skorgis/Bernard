from pathlib import Path

import pytest
from pydantic import ValidationError

from parkleitsystem.config import load_config
from parkleitsystem.parking import Side

EXAMPLE = Path(__file__).parents[1] / "config.example.toml"

MINIMAL = """
[leds]
team = "team-x"

[entry]
line_name = "Einfahrt"

[[spaces]]
name = "P1"
side = "left"
led = 1
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_example_config_is_valid() -> None:
    config = load_config(EXAMPLE)

    assert len(config.spaces) == 10
    assert config.mqtt.event_topic == "bma/events"


def test_defaults_fill_optional_sections(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, MINIMAL))

    assert config.mqtt.host == "localhost"
    assert config.leds.topic == "bmc_interface/tirol-hackathon/out"
    assert config.entry.guidance_seconds == 10
    assert config.display.enabled is True


def test_spaces_are_read(tmp_path: Path) -> None:
    (space,) = load_config(write(tmp_path, MINIMAL)).spaces

    assert space.name == "P1"
    assert space.side is Side.LEFT
    assert space.led == 1


def test_sign_can_be_switched_off(tmp_path: Path) -> None:
    text = MINIMAL + "\n[display]\nenabled = false\n"

    assert load_config(write(tmp_path, text)).display.enabled is False


def test_shared_led_is_rejected(tmp_path: Path) -> None:
    text = MINIMAL + '\n[[spaces]]\nname = "P2"\nside = "right"\nled = 1\n'

    with pytest.raises(ValidationError, match="LED 1"):
        load_config(write(tmp_path, text))


def test_led_must_be_1_to_10(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="led"):
        load_config(write(tmp_path, MINIMAL.replace("led = 1", "led = 11")))


def test_typos_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="line_nme"):
        load_config(write(tmp_path, MINIMAL.replace("line_name", "line_nme")))
