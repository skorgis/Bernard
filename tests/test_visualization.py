"""Tests for the drawing functions."""

from collections.abc import Sequence

import numpy as np
import pytest

from picture_pipeline.matching import MatchResult
from picture_pipeline.pipeline import LogoDetectionPipeline
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    equalize_contrast,
    resize_to_max_side,
    to_grayscale,
)
from picture_pipeline.visualization import (
    draw_detection,
    draw_logo_insets,
    draw_stage_strip,
)
from tests.picture_fixtures import make_background, make_logo, place_logo

GREEN = (0, 255, 0)


def _found(
    corners: Sequence[Sequence[float]],
    frame_shape: tuple[int, int] = (480, 640),
) -> MatchResult:
    return MatchResult(
        found=True,
        good_matches=20,
        inliers=18,
        frame_shape=frame_shape,
        homography=np.eye(3),
        corners=np.array(corners, dtype=np.float32),
    )


def _not_found() -> MatchResult:
    return MatchResult(
        found=False, good_matches=3, inliers=0, frame_shape=(480, 640)
    )


def _is_green(pixel: np.ndarray) -> bool:
    return tuple(int(c) for c in pixel) == GREEN


_SQUARE = [[100, 100], [200, 100], [200, 200], [100, 200]]
_BLACK = np.zeros((480, 640, 3), dtype=np.uint8)


def test_draws_outline_through_the_corners() -> None:
    """The logo outline is drawn along the result's corners."""
    canvas = draw_detection(_BLACK, _found(_SQUARE), show_status=False)

    assert _is_green(canvas[100, 150])  # top edge
    assert _is_green(canvas[150, 200])  # right edge
    assert not _is_green(canvas[150, 150])  # inside stays untouched


def test_returns_a_copy_and_leaves_the_frame_alone() -> None:
    """Drawing never modifies the caller's frame."""
    frame = _BLACK.copy()

    canvas = draw_detection(frame, _found(_SQUARE))

    assert canvas is not frame
    assert not frame.any()


def test_draws_nothing_when_not_found() -> None:
    """Without a detection (and without status), the copy is unchanged."""
    canvas = draw_detection(_BLACK, _not_found(), show_status=False)

    assert np.array_equal(canvas, _BLACK)


@pytest.mark.parametrize("result", [_found(_SQUARE), _not_found()])
def test_status_line_is_drawn_in_the_top_left(result: MatchResult) -> None:
    """The status text marks the top-left corner, found or not."""
    canvas = draw_detection(_BLACK, result)

    assert canvas[:40, :320].any()


def test_bounding_box_is_axis_aligned_around_a_rotated_outline() -> None:
    """`bounding_box=True` draws the upright rectangle enclosing the logo."""
    diamond = [[150, 100], [200, 150], [150, 200], [100, 150]]

    canvas = draw_detection(
        _BLACK, _found(diamond), bounding_box=True, show_status=False
    )

    assert _is_green(canvas[100, 100])  # bounding box corner
    assert _is_green(canvas[200, 200])
    assert not _is_green(canvas[150, 125])  # diamond edge isn't drawn


def test_grayscale_frame_gives_color_output() -> None:
    """A grayscale frame is converted so the colored outline is visible."""
    gray = np.zeros((480, 640), dtype=np.uint8)

    canvas = draw_detection(gray, _found(_SQUARE), show_status=False)

    assert canvas.shape == (480, 640, 3)
    assert _is_green(canvas[100, 150])


def test_scales_outline_from_a_resized_frame_to_the_original() -> None:
    """Corners from a half-size preprocessed frame map onto the original."""
    half = _found([[50, 50], [100, 50], [100, 100], [50, 100]], (240, 320))

    canvas = draw_detection(_BLACK, half, show_status=False)

    assert _is_green(canvas[100, 150])
    assert _is_green(canvas[150, 200])


def test_rejects_frame_whose_aspect_ratio_was_changed() -> None:
    """A cropped preprocessed frame can't be mapped back by scaling."""
    cropped = _found(_SQUARE, frame_shape=(300, 640))

    with pytest.raises(ValueError, match="aspect"):
        draw_detection(_BLACK, cropped)


def test_end_to_end_outline_matches_the_pasted_logo() -> None:
    """With a resizing frame pipeline, the outline lands on the real logo."""
    logo = make_logo()
    frame, expected = place_logo(make_background(), logo, (320, 240))
    pipeline = LogoDetectionPipeline(
        logo,
        frame_preprocessing=PreprocessingPipeline(
            [to_grayscale, resize_to_max_side(480), equalize_contrast()]
        ),
    )

    result = pipeline.process(frame)
    canvas = draw_detection(frame, result, show_status=False)

    assert result.found
    assert result.frame_shape == (360, 480)
    x, y = expected[0]  # logo's top-left corner in the original frame
    patch = canvas[int(y) - 3 : int(y) + 4, int(x) - 3 : int(x) + 4]
    assert any(_is_green(pixel) for row in patch for pixel in row)


def test_logo_insets_frame_each_logo_top_right_in_its_color() -> None:
    """Each logo appears in the top-right corner inside a colored border."""
    frame = make_background()
    blue = (255, 0, 0)

    canvas = draw_logo_insets(
        frame, [(make_logo(), GREEN), (make_logo(), blue)]
    )

    right_strip = canvas[:, -200:]
    assert np.all(right_strip == GREEN, axis=2).any()
    assert np.all(right_strip == blue, axis=2).any()
    assert np.array_equal(canvas[:, :300], frame[:, :300])


def test_logo_insets_leave_the_frame_untouched() -> None:
    """Like the other drawing functions, the input is copied."""
    frame = make_background()
    original = frame.copy()

    draw_logo_insets(frame, [(make_logo(), GREEN)])

    assert np.array_equal(frame, original)


def test_logo_insets_accept_grayscale_logo_and_frame() -> None:
    """Preprocessed (grayscale) images are drawn in color."""
    frame = np.zeros((240, 320), dtype=np.uint8)
    logo = np.full((50, 80), 200, dtype=np.uint8)

    canvas = draw_logo_insets(frame, [(logo, GREEN)])

    assert canvas.shape == (240, 320, 3)
    assert np.all(canvas == GREEN, axis=2).any()


def test_logo_insets_skip_logos_that_do_not_fit() -> None:
    """More logos than the frame's height holds are left out, no error."""
    frame = np.zeros((100, 400, 3), dtype=np.uint8)
    colors = [(0, 0, 255), (255, 0, 0), (0, 255, 255)]

    canvas = draw_logo_insets(frame, [(make_logo(), color) for color in colors])

    assert np.all(canvas == colors[0], axis=2).any()
    assert not np.all(canvas == colors[-1], axis=2).any()


def test_stage_strip_tiles_stages_as_small_thumbnails() -> None:
    """Five stages at four per row: two rows of `tile_width`-wide tiles."""
    gray = np.full((480, 640), 200, dtype=np.uint8)
    stages = [(f"step {n}", gray) for n in range(5)]

    strip = draw_stage_strip(stages, tile_width=100, columns=4)

    assert strip.ndim == 3
    assert strip.shape[1] == 400
    single_row = draw_stage_strip(stages[:4], tile_width=100, columns=4)
    assert strip.shape[0] == 2 * single_row.shape[0]


def test_stage_strip_is_only_as_wide_as_its_stages() -> None:
    """Fewer stages than columns don't leave empty tiles."""
    gray = np.zeros((480, 640), dtype=np.uint8)

    strip = draw_stage_strip([("a", gray), ("b", gray)], tile_width=160)

    assert strip.shape[1] == 320


def test_stage_strip_mixes_color_and_grayscale_stages() -> None:
    """The input is color, later stages grayscale; both get drawn."""
    stages = [
        ("input", make_background()),
        ("gray", np.zeros((480, 640), np.uint8)),
    ]

    strip = draw_stage_strip(stages, tile_width=160)

    assert strip[:, :160].std() > strip[:, 160:].std()


def test_stage_strip_needs_a_stage() -> None:
    """There is always at least the input to show."""
    with pytest.raises(ValueError):
        draw_stage_strip([])
