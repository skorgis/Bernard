"""Preprocessing: an ordered chain of `image -> image` steps.

The logo and the frames each get their own pipeline, but both must
reach the keypoint detector in a comparable form (e.g. both grayscale),
or their descriptors won't match.
"""

from collections.abc import Callable, Sequence

import cv2
import numpy as np

from picture_pipeline.image import Image

type PreprocessingStep = Callable[[Image], Image]


class PreprocessingPipeline:
    """Applies its steps in order, each to the previous step's output."""

    def __init__(self, steps: Sequence[PreprocessingStep] = ()) -> None:
        """Create a pipeline from `steps`; no steps means identity."""
        self._steps = tuple(steps)

    def __call__(self, image: Image) -> Image:
        """Run every step on `image` and return the result."""
        for step in self._steps:
            image = step(image)
        return image

    def stages(self, image: Image) -> list[Image]:
        """Every step's output, in order, to see how each changes `image`."""
        outputs = []
        for step in self._steps:
            image = step(image)
            outputs.append(image)
        return outputs


def to_grayscale(image: Image) -> Image:
    """Convert a BGR image to grayscale; leave grayscale images alone."""
    if image.ndim == 2:
        return image
    return np.asarray(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), dtype=np.uint8)


def resize_to_max_side(max_side: int) -> PreprocessingStep:
    """Shrink images whose longer side exceeds `max_side`, keeping aspect.

    Smaller images are never upscaled: that would only invent pixels.
    Fewer pixels make detection faster, at the cost of small details.
    """
    if max_side <= 0:
        raise ValueError(f"max_side must be positive: {max_side}")

    def resize(image: Image) -> Image:
        height, width = image.shape[:2]
        longer = max(height, width)
        if longer <= max_side:
            return image
        scale = max_side / longer
        size = (round(width * scale), round(height * scale))
        resized = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
        return np.asarray(resized, dtype=np.uint8)

    return resize


def _require_odd_kernel(kernel_size: int, minimum: int = 1) -> None:
    if kernel_size < minimum or kernel_size % 2 == 0:
        raise ValueError(
            f"kernel_size must be an odd number >= {minimum}: {kernel_size}"
        )


def gaussian_blur(kernel_size: int = 3) -> PreprocessingStep:
    """Low-pass filter: smooth sensor noise and other fine detail.

    Noise otherwise produces spurious keypoints. A larger kernel removes
    coarser detail.
    """
    _require_odd_kernel(kernel_size)

    def blur(image: Image) -> Image:
        blurred = cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
        return np.asarray(blurred, dtype=np.uint8)

    return blur


def high_pass(kernel_size: int = 9) -> PreprocessingStep:
    """High-pass filter: keep fine detail, drop smooth shading.

    Subtracts a Gaussian-blurred copy and centers the result on mid-gray
    (128 = no detail), so it stays a `uint8` image. Removes gradual
    lighting changes; `kernel_size` sets the coarsest detail kept.
    """
    _require_odd_kernel(kernel_size, minimum=3)

    def filter_(image: Image) -> Image:
        blurred = cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
        detail = cv2.addWeighted(image, 1.0, blurred, -1.0, 128)
        return np.asarray(detail, dtype=np.uint8)

    return filter_


def canny_edges(
    low_threshold: float = 50.0, high_threshold: float = 150.0
) -> PreprocessingStep:
    """Edge filter: a binary map (0/255) of the Canny edges.

    Gradients above `high_threshold` start an edge, and those above
    `low_threshold` continue one. Makes matching depend on outlines only,
    not on color or fill, at the cost of the texture inside them.
    """
    if not 0 <= low_threshold <= high_threshold:
        raise ValueError(
            "thresholds must satisfy 0 <= low <= high: "
            f"{low_threshold}, {high_threshold}"
        )

    def edges(image: Image) -> Image:
        detected = cv2.Canny(image, low_threshold, high_threshold)
        return np.asarray(detected, dtype=np.uint8)

    return edges


def equalize_contrast(
    clip_limit: float = 2.0, tile_grid_size: int = 8
) -> PreprocessingStep:
    """Local contrast equalization (CLAHE) on a grayscale image.

    Evens out lighting differences between logo and frame (shadows,
    backlight), which keypoint descriptors are sensitive to.
    """
    clahe = cv2.createCLAHE(
        clipLimit=clip_limit, tileGridSize=(tile_grid_size, tile_grid_size)
    )

    def equalize(image: Image) -> Image:
        if image.ndim != 2:
            raise ValueError(
                "equalize_contrast needs a grayscale image; "
                "put to_grayscale before it"
            )
        return np.asarray(clahe.apply(image), dtype=np.uint8)

    return equalize


def default_preprocessing() -> PreprocessingPipeline:
    """Grayscale plus contrast equalization: a good start for logos."""
    return PreprocessingPipeline([to_grayscale, equalize_contrast()])
