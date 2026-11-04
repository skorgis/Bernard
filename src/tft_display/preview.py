"""A stand-in display that writes PNG files, for testing without a Pi."""

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class PngPreview:
    """Saves every shown image to `path`, overwriting the previous one."""

    def __init__(self, path: Path, *, size: tuple[int, int]) -> None:
        """Write images of `size` (width, height) to `path`."""
        self._path = path
        self._size = size

    @property
    def size(self) -> tuple[int, int]:
        """Width and height in pixels that `display` expects."""
        return self._size

    def display(self, image: Image.Image) -> None:
        """Save `image` as PNG."""
        if image.size != self._size:
            width, height = self._size
            raise ValueError(
                f"image is {image.size[0]}x{image.size[1]}, "
                f"display is {width}x{height}"
            )
        image.save(self._path)
        logger.info("sign updated: %s", self._path)
