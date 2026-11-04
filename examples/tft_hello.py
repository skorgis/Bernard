"""Smallest possible example: draw an arrow and text on the RB-TFT1.8.

On the Raspberry Pi, with SPI enabled (see doc/tft-display.md):

    uv sync --extra pi
    uv run python examples/tft_hello.py

Uses luma.lcd directly, so you can see every setting. In your own program
`tft_display.open_tft()` does the same in one line.
"""

import time

from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from PIL import Image, ImageDraw, ImageFont

# Wiring from the Joy-IT manual. luma's defaults are DC=24 and RST=25,
# the other way round, so both must be given.
serial = spi(port=0, device=0, gpio_DC=25, gpio_RST=24)
# The RB-TFT1.8 has no backlight pin; a function that does nothing keeps
# luma from switching GPIO 18.
device = st7735(serial, width=160, height=128, backlight=lambda on: None)

# Draw on a Pillow image exactly the size of the display ...
image = Image.new("RGB", device.size, "black")
draw = ImageDraw.Draw(image)
draw.polygon(
    [(10, 30), (90, 30), (90, 10), (150, 50), (90, 90), (90, 70), (10, 70)],
    fill="green",
)
draw.text(
    (80, 110),
    "3 frei",
    fill="white",
    font=ImageFont.load_default(24),
    anchor="mm",  # anchor the text's middle at (80, 110)
)

# ... and send it to the display in one go.
device.display(image)
time.sleep(10)  # luma switches the display off when the program ends
