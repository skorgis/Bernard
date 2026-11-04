"""Tests for tft_display, with luma's hardware classes replaced by fakes."""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tft_display import PngPreview, TftConfig, open_tft
from tft_display import tft as tft_module


class FakeDevice:
    """Records what open_tft passes to luma's st7735 class."""

    def __init__(self, serial: object, **kwargs: Any) -> None:
        """Remember the arguments."""
        self.serial = serial
        self.kwargs = kwargs
        self.size = (160, 128)
        self.cleaned_up = False

    def display(self, image: Image.Image) -> None:
        """Accept an image."""

    def cleanup(self) -> None:
        """Remember that the device was released."""
        self.cleaned_up = True


@pytest.fixture
def fake_luma(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace luma's spi and st7735 classes; collect their arguments."""
    created: dict[str, Any] = {}

    def fake_spi(**kwargs: Any) -> str:
        created["spi"] = kwargs
        return "serial"

    def fake_st7735(serial: object, **kwargs: Any) -> FakeDevice:
        created["device"] = FakeDevice(serial, **kwargs)
        return created["device"]

    monkeypatch.setattr(tft_module, "spi", fake_spi)
    monkeypatch.setattr(tft_module, "st7735", fake_st7735)
    return created


def test_landscape_is_160_wide() -> None:
    """Rotating by 90 degrees swaps width and height."""
    assert TftConfig(rotation=0).size == (160, 128)
    assert TftConfig(rotation=90).size == (128, 160)


def test_only_quarter_turns_are_possible() -> None:
    """Rotation works in quarter turns, as in luma."""
    with pytest.raises(ValueError, match="45"):
        TftConfig(rotation=45)


def test_open_tft_uses_joy_it_pins(fake_luma: dict[str, Any]) -> None:
    """DC and RES follow the Joy-IT manual, not luma's swapped defaults."""
    with open_tft(TftConfig()):
        pass

    assert fake_luma["spi"] == {
        "port": 0,
        "device": 0,
        "gpio_DC": 25,
        "gpio_RST": 24,
    }


def test_open_tft_passes_mounting_options(fake_luma: dict[str, Any]) -> None:
    """Rotation, offsets and colour order reach the luma device."""
    config = TftConfig(rotation=180, x_offset=1, y_offset=2, bgr=True)

    with open_tft(config):
        pass

    kwargs = fake_luma["device"].kwargs
    assert kwargs["rotate"] == 2
    assert (kwargs["h_offset"], kwargs["v_offset"]) == (1, 2)
    assert kwargs["bgr"] is True
    assert kwargs["inverse"] is False


def test_open_tft_claims_no_backlight_gpio(fake_luma: dict[str, Any]) -> None:
    """The RB-TFT1.8 has no backlight pin, so luma must not drive GPIO 18."""
    with open_tft(TftConfig()):
        pass

    backlight = fake_luma["device"].kwargs["backlight"]
    assert callable(backlight)
    backlight(True)  # must accept luma's on/off calls without hardware


def test_open_tft_cleans_up_after_an_error(fake_luma: dict[str, Any]) -> None:
    """The device is released even if the caller fails."""
    with pytest.raises(RuntimeError), open_tft(TftConfig()):
        raise RuntimeError

    assert fake_luma["device"].cleaned_up


def test_png_preview_writes_displayed_image(tmp_path: Path) -> None:
    """The preview saves exactly the image it was given."""
    target = tmp_path / "sign.png"
    preview = PngPreview(target, size=(160, 128))

    preview.display(Image.new("RGB", (160, 128), (0, 255, 0)))

    assert Image.open(target).getpixel((0, 0)) == (0, 255, 0)


def test_png_preview_rejects_wrong_size(tmp_path: Path) -> None:
    """Images must match the display size, as on the real TFT."""
    preview = PngPreview(tmp_path / "sign.png", size=(160, 128))

    with pytest.raises(ValueError, match="160x128"):
        preview.display(Image.new("RGB", (10, 10)))
