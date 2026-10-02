"""Tests for the window-independent parts of the tuner GUI."""

import numpy as np

from picture_pipeline.gui import (
    logo_status_lines,
    render,
    stage_strip,
    status_text,
)
from picture_pipeline.tuning import TuningSettings
from picture_pipeline.visualization import LOGO_COLORS
from tests.picture_fixtures import make_background, make_logo, place_logo


def _analysis(frame_max_side: int = 0):
    frame, _ = place_logo(make_background(), make_logo(), (320, 240))
    pipeline = TuningSettings(frame_max_side=frame_max_side).build_pipeline(
        {"bernard": make_logo(), "other": make_logo(100)[:, ::-1].copy()}
    )
    return frame, pipeline.analyze(frame)


def test_render_shows_each_logo_as_an_inset() -> None:
    """With logos given, they appear top right, framed in their color."""
    frame, analysis = _analysis()
    logos = {"bernard": make_logo(), "other": make_logo(100)}

    plain = render(frame, analysis, False, False, False)
    with_insets = render(frame, analysis, False, False, False, logos)

    right_strip = with_insets[:, -200:]
    assert not np.array_equal(right_strip, plain[:, -200:])
    assert _contains_color(right_strip, LOGO_COLORS[1])


def _contains_color(image: np.ndarray, color: tuple[int, int, int]) -> bool:
    return bool(np.all(image == color, axis=2).any())


def test_render_marks_each_found_logo_in_its_own_color() -> None:
    """The found logo is outlined in the first palette color."""
    frame, analysis = _analysis()

    canvas = render(frame, analysis, False, False, False)

    assert canvas.shape == frame.shape
    assert _contains_color(canvas, LOGO_COLORS[0])


def test_render_can_show_the_preprocessed_frame() -> None:
    """The preprocessed view has the preprocessed frame's size, in color."""
    frame, analysis = _analysis(frame_max_side=320)

    canvas = render(frame, analysis, True, False, False)

    assert canvas.shape == (240, 320, 3)


def test_status_text_lists_every_logo() -> None:
    """Each logo gets a line with its state and match counts."""
    _, analysis = _analysis()

    text = status_text(analysis, seconds=0.05)

    assert "20.0 FPS" in text
    assert "bernard: gefunden" in text
    assert "other: nicht gefunden" in text


def test_stage_strip_shows_the_input_and_every_frame_step() -> None:
    """One small thumbnail for the input plus one per frame step."""
    frame = make_background()
    settings = TuningSettings(frame_blur=5, canny=True)
    pipeline = settings.build_pipeline({"logo": make_logo()})

    strip = stage_strip(frame, pipeline, settings.frame_step_labels())

    tiles = 1 + len(settings.frame_step_labels())
    assert strip.shape[1] == tiles * 160
    assert strip.shape[0] < frame.shape[0]


def test_stage_strip_shrinks_tiles_to_keep_every_step_in_one_row() -> None:
    """Many steps get narrower thumbnails instead of a second row."""
    frame = make_background()
    settings = TuningSettings(
        frame_max_side=480, frame_blur=5, high_pass=15, canny=True
    )
    pipeline = settings.build_pipeline({"logo": make_logo()})

    strip = stage_strip(frame, pipeline, settings.frame_step_labels())

    tiles = 1 + len(settings.frame_step_labels())
    assert tiles * 160 > 960
    assert strip.shape[1] <= 960
    assert strip.shape[0] < 160


def test_logo_status_lines_are_ascii_one_per_logo() -> None:
    """OpenCV can draw them: plain ASCII, with state and match counts."""
    _, analysis = _analysis()

    lines = logo_status_lines(analysis)

    assert len(lines) == 2
    assert lines[0].startswith("bernard: gefunden (")
    assert lines[1].startswith("other: nicht gefunden (")
    assert all(line.isascii() for line in lines)


def _three_copies_analysis():
    frame = make_background()
    for x in (110, 320, 530):
        frame, _ = place_logo(frame, make_logo(100), (x, 240))
    pipeline = TuningSettings(max_instances=5).build_pipeline(
        {"logo": make_logo(100)}
    )
    return frame, pipeline.analyze(frame)


def test_render_outlines_every_copy() -> None:
    """Each found copy gets its own outline in the logo's color."""
    frame, analysis = _three_copies_analysis()

    canvas = render(frame, analysis, False, False, False)

    for x in (110, 320, 530):
        region = canvas[150:330, x - 70 : x + 70]
        assert _contains_color(region, LOGO_COLORS[0])


def test_status_line_counts_the_copies() -> None:
    """With several copies the line says how many."""
    _, analysis = _three_copies_analysis()

    assert logo_status_lines(analysis)[0].startswith("logo: 3x gefunden")
