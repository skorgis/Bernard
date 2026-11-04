from pathlib import Path

import pytest
from pydantic import ValidationError

from parkleitsystem.config import load_config
from parkleitsystem.domain import Side

EXAMPLE = Path(__file__).parents[1] / "config.example.toml"

MINIMAL = """
[leds]
bma_id = "bma-1"
team = "team-x"

[entry]
line_name = "Einfahrt"

[[spaces]]
roi_name = "P1"
side = "left"
led_contact = 1
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_example_config_is_valid() -> None:
    config = load_config(EXAMPLE)

    assert config.spaces
    assert config.mqtt.event_topic == "bma/events"


def test_defaults_fill_optional_sections(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, MINIMAL))

    assert config.mqtt.host == "localhost"
    assert config.leds.topic == "bmc_interface/tirol-hackathon/out"
    assert config.entry.direction == "in"
    assert config.display.rotation == 0


def test_spaces_become_domain_objects(tmp_path: Path) -> None:
    (space,) = load_config(write(tmp_path, MINIMAL)).parking_spaces()

    assert space.roi_name == "P1"
    assert space.side is Side.LEFT
    assert space.led_contact == 1


def test_shared_led_contact_is_rejected(tmp_path: Path) -> None:
    text = MINIMAL + '\n[[spaces]]\nroi_name = "P2"\nside = "right"\n'
    text += "led_contact = 1\n"

    with pytest.raises(ValidationError, match="LED contact 1"):
        load_config(write(tmp_path, text))


def test_led_contact_must_be_1_to_10(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="led_contact"):
        load_config(
            write(
                tmp_path, MINIMAL.replace("led_contact = 1", "led_contact = 11")
            )
        )


def test_typos_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="line_nme"):
        load_config(write(tmp_path, MINIMAL.replace("line_name", "line_nme")))
