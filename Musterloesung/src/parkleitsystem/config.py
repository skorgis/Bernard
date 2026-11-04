"""Validated program configuration, loaded from a TOML file.

Broker credentials are not part of it: they come from the environment
variables MQTT_USER and MQTT_PASSWORD, so the file can be committed.
"""

import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from parkleitsystem.domain import ParkingSpace, Side
from parkleitsystem.led_command import MAX_LED_CONTACT, MIN_LED_CONTACT

# Node id of BMA G-A2610-0007, also in every event under `node.id`.
HACKATHON_BMA_ID = "f6b51cd4-4469-4138-831a-b5cc471f9e45"


class _Section(BaseModel):
    # Unknown keys are an error, so a typo does not silently fall back to
    # a default.
    model_config = ConfigDict(extra="forbid", frozen=True)


class MqttSettings(_Section):
    """Broker connection and the topic the BMA publishes events on."""

    host: str = "localhost"
    port: int = 1883
    client_id: str = "parkleitsystem"
    event_topic: str = "bma/events"


class LedSettings(_Section):
    """Where LED commands go and who sends them."""

    topic: str = "bmc_interface/tirol-hackathon/out"
    bma_id: str = HACKATHON_BMA_ID
    team: str


class EntrySettings(_Section):
    """The crossing line at the car park entry."""

    line_name: str
    direction: Literal["in", "out"] = "in"
    guidance_seconds: float = Field(default=10.0, gt=0)
    vehicle_classes: list[str] = Field(
        default_factory=list,
        description="classes that get guidance; empty means every class",
    )


class DisplaySettings(_Section):
    """How the TFT is mounted; see tft_display.TftConfig."""

    rotation: Literal[0, 90, 180, 270] = 0
    x_offset: int = 0
    y_offset: int = 0
    bgr: bool = False
    invert: bool = False


class SpaceSettings(_Section):
    """One parking space: BMA zone name, side and LED contact."""

    roi_name: str = Field(min_length=1)
    side: Side
    led_contact: int = Field(ge=MIN_LED_CONTACT, le=MAX_LED_CONTACT)


class AppConfig(_Section):
    """The whole configuration file."""

    mqtt: MqttSettings = MqttSettings()
    leds: LedSettings
    entry: EntrySettings
    display: DisplaySettings = DisplaySettings()
    spaces: list[SpaceSettings] = Field(min_length=1)

    @model_validator(mode="after")
    def _spaces_are_distinct(self) -> Self:
        _require_unique([s.roi_name for s in self.spaces], "zone")
        _require_unique([s.led_contact for s in self.spaces], "LED contact")
        return self

    def parking_spaces(self) -> list[ParkingSpace]:
        """The configured spaces as domain objects."""
        return [
            ParkingSpace(s.roi_name, s.side, led_contact=s.led_contact)
            for s in self.spaces
        ]


def load_config(path: Path) -> AppConfig:
    """Read and validate the TOML file at `path`.

    Raises:
        pydantic.ValidationError: If the content is invalid.
    """
    with path.open("rb") as file:
        return AppConfig.model_validate(tomllib.load(file))


def _require_unique(values: list[str] | list[int], what: str) -> None:
    seen: set[str | int] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{what} {value} is used by two spaces")
        seen.add(value)
