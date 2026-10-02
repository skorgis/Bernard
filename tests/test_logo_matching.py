"""Tests for `LogoMatcher` and the end-to-end `LogoDetectionPipeline`."""

import numpy as np
import numpy.typing as npt
import pytest

from picture_pipeline.image import Image
from picture_pipeline.keypoints import DetectorKind, KeypointDetector
from picture_pipeline.matching import (
    LogoMatcher,
    MatchResult,
    is_plausible_outline,
)
from picture_pipeline.pipeline import LogoDetectionPipeline
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    equalize_contrast,
    resize_to_max_side,
    to_grayscale,
)
from tests.picture_fixtures import make_background, make_logo, place_logo

CORNER_TOLERANCE_PX = 6.0


def _assert_corners_close(
    result: MatchResult, expected: npt.NDArray[np.float32]
) -> None:
    assert result.corners is not None
    assert np.abs(result.corners - expected).max() < CORNER_TOLERANCE_PX


@pytest.mark.parametrize("kind", list(DetectorKind))
def test_finds_logo_pasted_into_frame(kind: DetectorKind) -> None:
    """The logo is found, and its outline lands where it was pasted."""
    logo = make_logo()
    frame, expected = place_logo(make_background(), logo, center=(400, 250))
    pipeline = LogoDetectionPipeline(logo, detector=KeypointDetector(kind))

    result = pipeline.process(frame)

    assert result.found
    _assert_corners_close(result, expected)


_SIFT = LogoDetectionPipeline(make_logo())
_ORB = LogoDetectionPipeline(
    make_logo(), detector=KeypointDetector(DetectorKind.ORB)
)
_ANGLES = [0, 15, 30, 45, 60, 90, 135, 180]


@pytest.mark.parametrize("angle", _ANGLES)
@pytest.mark.parametrize("scale", [1.0, 0.8, 0.6, 0.5])
def test_sift_locates_rotated_and_scaled_logo(
    angle: float, scale: float
) -> None:
    """SIFT finds the logo and its true outline across rotations/scales."""
    frame, expected = place_logo(
        make_background(), make_logo(), (320, 240), angle, scale
    )

    result = _SIFT.process(frame)

    assert result.found
    _assert_corners_close(result, expected)


@pytest.mark.parametrize("angle", _ANGLES)
def test_orb_locates_rotated_logo_at_full_scale(angle: float) -> None:
    """ORB, including logo-edge keypoints, locates a full-size logo."""
    frame, expected = place_logo(
        make_background(), make_logo(), (320, 240), angle
    )

    result = _ORB.process(frame)

    assert result.found
    _assert_corners_close(result, expected)


_SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]


@pytest.mark.parametrize(
    ("corners", "plausible"),
    [
        (_SQUARE, True),
        ([[0, 0], [100, 0], [80, 60], [20, 60]], True),
        ([[0, 0], [100, 100], [100, 0], [0, 100]], False),
        ([[0, 0], [100, 0], [200, 0], [300, 0]], False),
        ([[0, 0], [300, 0], [200, 50], [100, 50]], False),
    ],
    ids=["square", "mild-perspective", "bow-tie", "collapsed", "side-ratio-3"],
)
def test_is_plausible_outline(
    corners: list[list[float]], plausible: bool
) -> None:
    """Twisted, collapsed or heavily distorted outlines are rejected."""
    outline = np.array(corners, dtype=np.float32)
    assert is_plausible_outline(outline, max_side_ratio=2.0) is plausible


@pytest.mark.parametrize("kind", list(DetectorKind))
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_does_not_find_logo_in_frame_without_it(
    kind: DetectorKind, seed: int
) -> None:
    """Clutter alone must not be reported as the logo."""
    pipeline = LogoDetectionPipeline(
        make_logo(), detector=KeypointDetector(kind)
    )

    result = pipeline.process(make_background(seed))

    assert not result.found
    assert result.corners is None


def test_not_found_when_frame_has_no_features() -> None:
    """A featureless frame is a clean 'not found', not an error."""
    pipeline = LogoDetectionPipeline(make_logo())

    result = pipeline.process(np.full((480, 640, 3), 128, dtype=np.uint8))

    assert not result.found
    assert result.good_matches == 0


def test_rejects_logo_without_features() -> None:
    """A logo with no keypoints can never be matched, so fail early."""
    with pytest.raises(ValueError, match="keypoints"):
        LogoDetectionPipeline(np.full((100, 100, 3), 255, dtype=np.uint8))


def test_rejects_features_from_different_detectors() -> None:
    """SIFT and ORB descriptors can't be compared with each other."""
    logo = to_grayscale(make_logo())
    sift = KeypointDetector(DetectorKind.SIFT).detect(logo)
    orb = KeypointDetector(DetectorKind.ORB).detect(logo)

    with pytest.raises(ValueError, match="detector"):
        LogoMatcher().match(sift, orb)


@pytest.mark.parametrize("ratio", [0.0, 1.0, 1.5])
def test_rejects_ratio_outside_open_unit_interval(ratio: float) -> None:
    """Lowe's ratio must be strictly between 0 and 1."""
    with pytest.raises(ValueError):
        LogoMatcher(ratio=ratio)


def test_rejects_max_side_ratio_below_one() -> None:
    """Opposite sides can't be required to differ by less than nothing."""
    with pytest.raises(ValueError):
        LogoMatcher(max_side_ratio=0.9)


def test_rejects_min_inliers_below_homography_minimum() -> None:
    """A homography needs at least 4 point pairs."""
    with pytest.raises(ValueError):
        LogoMatcher(min_inliers=3)


def test_logo_features_are_extracted_once() -> None:
    """The static logo is processed at construction, not per frame."""
    pipeline = LogoDetectionPipeline(make_logo())
    features = pipeline.logo_features

    pipeline.process(make_background())

    assert pipeline.logo_features is features


def _recording(seen: list[tuple[int, ...]]) -> PreprocessingPipeline:
    def record(image: Image) -> Image:
        seen.append(image.shape)
        return image

    return PreprocessingPipeline([record, to_grayscale, equalize_contrast()])


def test_logo_and_frame_use_their_own_preprocessing() -> None:
    """The logo pipeline sees only the logo, the frame pipeline each frame."""
    logo_seen: list[tuple[int, ...]] = []
    frame_seen: list[tuple[int, ...]] = []
    pipeline = LogoDetectionPipeline(
        make_logo(160),
        logo_preprocessing=_recording(logo_seen),
        frame_preprocessing=_recording(frame_seen),
    )

    pipeline.process(make_background())
    pipeline.process(make_background(2))

    assert logo_seen == [(160, 160, 3)]
    assert frame_seen == [(480, 640, 3), (480, 640, 3)]


def test_resizing_only_the_logo_still_locates_it_in_frame() -> None:
    """A shrunk logo is still found, and outlined in frame coordinates."""
    logo = make_logo(160)
    frame, expected = place_logo(
        make_background(), logo, (320, 240), angle=20, scale=0.6
    )
    pipeline = LogoDetectionPipeline(
        logo,
        logo_preprocessing=PreprocessingPipeline(
            [to_grayscale, equalize_contrast(), resize_to_max_side(100)]
        ),
    )

    result = pipeline.process(frame)

    assert pipeline.logo_features.image_shape == (100, 100)
    assert result.found
    _assert_corners_close(result, expected)
