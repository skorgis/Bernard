"""Tests for finding logos in frames with `LogoFinder`."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from picture_pipeline.logo_finder import (
    Detection,
    LogoFinder,
    draw,
    load_logos,
)
from tests.picture_fixtures import make_background, make_logo, place_logo

# A found outline counts as correct if every corner is within this many
# pixels of the true one (logo side: 160 px).
CORNER_TOLERANCE_PX = 6.0


def corner_error(detection: Detection | None, expected: np.ndarray) -> float:
    """Largest distance between found and expected corners, in pixels."""
    assert detection is not None, "logo not found"
    return float(np.linalg.norm(detection.corners - expected, axis=1).max())


@pytest.mark.parametrize("angle", [0, 45, 135, 270])
@pytest.mark.parametrize("scale", [0.6, 1.0, 1.3])
def test_finds_logo_where_it_is(angle: float, scale: float) -> None:
    """The outline follows the logo's position, rotation and size."""
    logo = make_logo()
    frame, expected = place_logo(
        make_background(), logo, (320, 240), angle, scale
    )

    found = LogoFinder({"bg": logo}).find(frame)

    assert corner_error(found["bg"], expected) < CORNER_TOLERANCE_PX


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_finds_nothing_in_a_frame_without_the_logo(seed: int) -> None:
    """Clutter alone must not produce a detection."""
    finder = LogoFinder({"bg": make_logo()})

    assert finder.find(make_background(seed)) == {"bg": None}


def test_finds_several_logos_each_in_its_place() -> None:
    """Every logo is reported under its own name and position."""
    first, second = make_logo(seed=7), make_logo(seed=11)
    frame, first_corners = place_logo(
        make_background(), first, (160, 240), scale=0.8
    )
    frame, second_corners = place_logo(frame, second, (480, 240), scale=0.8)

    found = LogoFinder({"first": first, "second": second}).find(frame)

    assert corner_error(found["first"], first_corners) < CORNER_TOLERANCE_PX
    assert corner_error(found["second"], second_corners) < CORNER_TOLERANCE_PX


def test_corners_refer_to_the_original_frame_when_shrinking() -> None:
    """Shrinking the frame for speed must not move the reported corners."""
    logo = make_logo()
    frame, expected = place_logo(make_background(), logo, (320, 240))
    large = np.asarray(cv2.resize(frame, None, fx=2, fy=2), dtype=np.uint8)

    found = LogoFinder({"bg": logo}, frame_max_side=640).find(large)

    # Twice the tolerance: the frame is twice as large.
    assert corner_error(found["bg"], expected * 2) < 2 * CORNER_TOLERANCE_PX


def test_detection_center_is_the_middle_of_the_outline() -> None:
    """`center` is where to point at the logo, e.g. for a parking space."""
    logo = make_logo()
    frame, _ = place_logo(make_background(), logo, (300, 200), angle=30)

    detection = LogoFinder({"bg": logo}).find(frame)["bg"]

    assert detection is not None
    assert detection.center == pytest.approx((300, 200), abs=3)


def test_too_few_matches_count_as_not_found() -> None:
    """`min_matches` is the strictness: above the matches found, no logo."""
    logo = make_logo()
    frame, _ = place_logo(make_background(), logo, (320, 240))
    finder = LogoFinder({"bg": logo})
    detection = finder.find(frame)["bg"]
    assert detection is not None

    finder.min_matches = detection.matches + 1

    assert finder.find(frame) == {"bg": None}


def test_logo_without_texture_is_rejected() -> None:
    """A plain logo has no keypoints, so it could never be found."""
    plain = np.full((100, 100, 3), 255, dtype=np.uint8)

    with pytest.raises(ValueError, match="plain"):
        LogoFinder({"plain": plain})


def test_needs_at_least_one_logo() -> None:
    """Without logos there is nothing to look for."""
    with pytest.raises(ValueError, match="logo"):
        LogoFinder({})


def test_load_logos_names_images_by_file_name(tmp_path: Path) -> None:
    """Each image file becomes a BGR logo named after the file."""
    cv2.imwrite(str(tmp_path / "rollstuhl.png"), make_logo())
    (tmp_path / "notes.txt").write_text("not an image")

    logos = load_logos(tmp_path)

    assert list(logos) == ["rollstuhl"]
    assert logos["rollstuhl"].shape == (160, 160, 3)


def test_load_logos_turns_transparency_white(tmp_path: Path) -> None:
    """Transparent PNG pixels would otherwise read as black."""
    transparent = np.zeros((10, 10, 4), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "logo.png"), transparent)

    logo = load_logos(tmp_path)["logo"]

    assert (logo == 255).all()


def test_load_logos_reports_missing_folder(tmp_path: Path) -> None:
    """A wrong folder name must not look like 'no logos found'."""
    with pytest.raises(FileNotFoundError):
        load_logos(tmp_path / "missing")


def test_load_logos_reports_folder_without_images(tmp_path: Path) -> None:
    """An empty folder is an error, not an empty result."""
    with pytest.raises(ValueError, match="no logo images"):
        load_logos(tmp_path)


def test_draw_marks_found_logos_on_a_copy() -> None:
    """The frame itself stays unchanged; only the copy gets the outline."""
    logo = make_logo()
    frame, _ = place_logo(make_background(), logo, (320, 240))
    original = frame.copy()
    found = LogoFinder({"bg": logo}).find(frame)

    marked = draw(frame, found)

    assert np.array_equal(frame, original)
    assert not np.array_equal(marked, frame)


def test_draw_leaves_frame_alone_when_nothing_was_found() -> None:
    """Missing logos draw nothing."""
    frame = make_background()

    assert np.array_equal(draw(frame, {"bg": None}), frame)
