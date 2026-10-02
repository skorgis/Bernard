"""Tests for the picture pipeline's preprocessing steps."""

import numpy as np
import pytest

from picture_pipeline.image import Image
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    canny_edges,
    default_preprocessing,
    equalize_contrast,
    gaussian_blur,
    high_pass,
    resize_to_max_side,
    to_grayscale,
)
from tests.picture_fixtures import make_background


def test_to_grayscale_turns_bgr_into_one_channel() -> None:
    """A 3-channel frame becomes a 2-D grayscale image of the same size."""
    gray = to_grayscale(make_background())
    assert gray.shape == (480, 640)
    assert gray.dtype == np.uint8


def test_to_grayscale_leaves_grayscale_untouched() -> None:
    """An image that is already grayscale passes through unchanged."""
    gray = np.zeros((10, 20), dtype=np.uint8)
    assert to_grayscale(gray) is gray


def test_resize_to_max_side_keeps_aspect_ratio() -> None:
    """The longer side is scaled to `max_side`, the other proportionally."""
    resized = resize_to_max_side(320)(make_background())
    assert resized.shape[:2] == (240, 320)


def test_resize_to_max_side_never_upscales() -> None:
    """An image already smaller than `max_side` is returned as is."""
    small = np.zeros((100, 50), dtype=np.uint8)
    assert resize_to_max_side(320)(small) is small


def test_resize_rejects_non_positive_max_side() -> None:
    """`max_side` must be positive."""
    with pytest.raises(ValueError):
        resize_to_max_side(0)


def test_gaussian_blur_rejects_even_kernel() -> None:
    """OpenCV needs an odd kernel size, so an even one fails early."""
    with pytest.raises(ValueError):
        gaussian_blur(4)


def test_gaussian_blur_keeps_shape() -> None:
    """Blurring changes pixel values, not the image size."""
    frame = make_background()
    assert gaussian_blur(5)(frame).shape == frame.shape


def _white_square() -> Image:
    image = np.zeros((40, 40), dtype=np.uint8)
    image[10:30, 10:30] = 255
    return image


def test_high_pass_turns_flat_image_mid_gray() -> None:
    """Without detail there is nothing to keep: every pixel becomes 128."""
    flat = np.full((20, 20), 77, dtype=np.uint8)
    assert np.all(high_pass(5)(flat) == 128)


def test_high_pass_keeps_sharp_edges() -> None:
    """Fine detail survives: the square's border departs from mid-gray."""
    filtered = high_pass(5)(_white_square())
    assert filtered.shape == (40, 40)
    assert filtered.dtype == np.uint8
    assert filtered[10, 20] > 128 > filtered[9, 20]


@pytest.mark.parametrize("kernel_size", [0, 1, 4])
def test_high_pass_rejects_invalid_kernel(kernel_size: int) -> None:
    """The kernel must be odd and at least 3, or nothing passes through."""
    with pytest.raises(ValueError):
        high_pass(kernel_size)


def test_canny_edges_marks_only_the_border() -> None:
    """The output is a binary map with edges on the square's outline."""
    edges = canny_edges(50, 150)(_white_square())
    assert set(np.unique(edges)) == {0, 255}
    assert edges[20, 20] == 0
    assert edges[0, 0] == 0
    assert edges[8:12, 20].max() == 255


@pytest.mark.parametrize(("low", "high"), [(150, 50), (-1, 50)])
def test_canny_edges_rejects_invalid_thresholds(
    low: float, high: float
) -> None:
    """Thresholds must be non-negative with low <= high."""
    with pytest.raises(ValueError):
        canny_edges(low, high)


def test_equalize_contrast_requires_grayscale() -> None:
    """CLAHE works on one channel; a color image is a usage error."""
    with pytest.raises(ValueError, match="grayscale"):
        equalize_contrast()(make_background())


def test_pipeline_applies_steps_in_order() -> None:
    """Each step receives the previous step's output."""
    calls: list[str] = []

    def step(name: str):
        def apply(image: Image) -> Image:
            calls.append(name)
            return image

        return apply

    PreprocessingPipeline([step("first"), step("second")])(make_background())

    assert calls == ["first", "second"]


def test_stages_returns_every_step_output_in_order() -> None:
    """One image per step; the last one is what the pipeline returns."""
    frame = make_background()
    pipeline = PreprocessingPipeline([to_grayscale, resize_to_max_side(320)])

    stages = pipeline.stages(frame)

    assert [stage.shape for stage in stages] == [(480, 640), (240, 320)]
    assert np.array_equal(stages[-1], pipeline(frame))


def test_stages_of_empty_pipeline_is_empty() -> None:
    """Without steps there are no intermediate results."""
    assert PreprocessingPipeline().stages(make_background()) == []


def test_empty_pipeline_returns_input() -> None:
    """A pipeline without steps is the identity."""
    frame = make_background()
    assert PreprocessingPipeline()(frame) is frame


def test_default_preprocessing_produces_grayscale() -> None:
    """The default pipeline yields a 2-D uint8 image for the detectors."""
    result = default_preprocessing()(make_background())
    assert result.ndim == 2
    assert result.dtype == np.uint8
