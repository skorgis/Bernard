"""Read and check config.toml.

The broker login is not in the file but in the environment variables
MQTT_USER and MQTT_PASSWORD, so the file can be shared safely.
"""

import tomllib
from pathlib import Path
from typing import Literal, Self

from bmc_leds import FIRST_LED, HACKATHON_BMA_ID, LAST_LED, LED_TOPIC
from pydantic import BaseModel, ConfigDict, Field, model_validator

from parkleitsystem.parking import Side, Space


class _Section(BaseModel):
    # A typo in a key is an error instead of a silently ignored setting.
    model_config = ConfigDict(extra="forbid", frozen=True)


class MqttSettings(_Section):
    """Broker connection and the topic the BMA publishes its events on."""

    host: str = "localhost"
    port: int = 1883
    client_id: str = "parkleitsystem"
    event_topic: str = "bma/events"


class LedSettings(_Section):
    """Where LED commands go and who sends them."""

    topic: str = LED_TOPIC
    bma_id: str = HACKATHON_BMA_ID
    team: str  # bmc-interface counts its spam limit per team


class EntrySettings(_Section):
    """The crossing line at the entry."""

    line_name: str
    guidance_seconds: float = Field(default=10, gt=0)


class DisplaySettings(_Section):
    """Whether a TFT sign is installed and how it is mounted."""

    enabled: bool = True
    rotation: Literal[0, 90, 180, 270] = 0
    x_offset: int = 0
    y_offset: int = 0
    bgr: bool = False
    invert: bool = False


class SpaceSettings(_Section):
    """One parking space: BMA zone name, side and LED contact (1-10)."""

    name: str = Field(min_length=1)
    side: Side
    led: int = Field(ge=FIRST_LED, le=LAST_LED)


class Config(_Section):
    """The whole config.toml."""

    mqtt: MqttSettings = MqttSettings()
    leds: LedSettings
    entry: EntrySettings
    display: DisplaySettings = DisplaySettings()
    spaces: list[SpaceSettings] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicates(self) -> Self:
        _require_unique("zone", [s.name for s in self.spaces])
        _require_unique("LED", [s.led for s in self.spaces])
        return self

    def parking_spaces(self) -> list[Space]:
        """The configured spaces, in configured order."""
        return [Space(s.name, s.side, s.led) for s in self.spaces]


def load_config(path: Path) -> Config:
    """Read and check the TOML file at `path`.

    Raises:
        pydantic.ValidationError: If the content is invalid.
    """
    with path.open("rb") as file:
        return Config.model_validate(tomllib.load(file))


def _require_unique(what: str, values: list[str] | list[int]) -> None:
    seen: set[str | int] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{what} {value} is used twice")
        seen.add(value)
