"""The interface every sign output (luma TFT device or preview) implements.

luma devices satisfy it as they are: they have `size` and `display()`.
"""

from typing import Protocol

from PIL import Image


class Display(Protocol):
    """Shows full-screen Pillow images."""

    @property
    def size(self) -> tuple[int, int]:
        """Width and height in pixels that `display` expects."""
        ...

    def display(self, image: Image.Image) -> None:
        """Replace the whole screen with `image` (must match `size`)."""
        ...
