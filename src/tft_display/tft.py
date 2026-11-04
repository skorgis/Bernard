"""Open the Joy-IT RB-TFT1.8 (ST7735, 160x128) via luma.lcd.

Wiring per the Joy-IT manual: SCL -> GPIO 11 (SCLK), SDA -> GPIO 10 (MOSI),
CS -> GPIO 8 (CE0), RS/DC -> GPIO 25, RES -> GPIO 24, VCC -> 3.3 V.
On the Pi, luma drives GPIO through rpi-lgpio, which also works on the
Raspberry Pi 5 (install with `uv sync --extra pi`).
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from luma.core.interface.serial import spi
from luma.lcd.device import st7735

from tft_display.display import Display

# Panel size in luma's default (landscape) orientation.
WIDTH = 160
HEIGHT = 128
DEGREES_PER_LUMA_STEP = 90  # luma's `rotate` counts quarter turns


@dataclass(frozen=True, slots=True)
class TftConfig:
    """Where the display is connected and how it is mounted.

    `x_offset`/`y_offset` shift the picture by whole pixels; some panels
    need 1-2, visible as a coloured line at one edge. Set `bgr` if red and
    blue are swapped, `invert` if all colours are inverted.
    """

    spi_port: int = 0
    spi_device: int = 0  # 0 = chip select CE0 (GPIO 8)
    # luma's defaults are DC=24, RST=25: the reverse of the Joy-IT wiring.
    dc_gpio: int = 25
    reset_gpio: int = 24
    rotation: int = 0  # degrees clockwise; 0 = landscape, pins on the left
    x_offset: int = 0
    y_offset: int = 0
    bgr: bool = False
    invert: bool = False

    def __post_init__(self) -> None:
        """Reject rotations luma cannot do."""
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError(
                f"rotation must be 0, 90, 180 or 270, got {self.rotation}"
            )

    @property
    def size(self) -> tuple[int, int]:
        """Width and height after rotation."""
        if self.rotation in (90, 270):
            return HEIGHT, WIDTH
        return WIDTH, HEIGHT


@contextmanager
def open_tft(config: TftConfig | None = None) -> Generator[Display]:
    """Initialise the TFT; release SPI and GPIO when the block ends.

    Raises:
        luma.core.error.DeviceNotFoundError: If SPI is not enabled.
    """
    config = config or TftConfig()
    serial = spi(
        port=config.spi_port,
        device=config.spi_device,
        gpio_DC=config.dc_gpio,
        gpio_RST=config.reset_gpio,
    )
    device = st7735(
        serial,
        width=WIDTH,
        height=HEIGHT,
        rotate=config.rotation // DEGREES_PER_LUMA_STEP,
        h_offset=config.x_offset,
        v_offset=config.y_offset,
        bgr=config.bgr,
        inverse=config.invert,
        backlight=_no_backlight,
    )
    try:
        yield device
    finally:
        device.cleanup()


def _no_backlight(on: bool) -> None:
    """Backlight control that does nothing.

    The RB-TFT1.8's backlight is hard-wired to VCC. Passing this keeps luma
    from claiming GPIO 18 for a backlight that does not exist.
    """
