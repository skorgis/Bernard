"""Tests for `MultiLogoPipeline` and the FLANN matcher option."""

import cv2
import numpy as np
import pytest

from picture_pipeline.keypoints import DetectorKind, KeypointDetector
from picture_pipeline.matching import LogoMatcher, MatcherKind
from picture_pipeline.pipeline import LogoDetectionPipeline, MultiLogoPipeline
from tests.picture_fixtures import make_background, make_logo, place_logo


def _other_logo() -> np.ndarray:
    """A second, clearly different logo: a checkerboard with a cross."""
    logo = np.full((140, 140, 3), 255, dtype=np.uint8)
    for row in range(7):
        for col in range(7):
            if (row + col) % 2:
                logo[row * 20 : row * 20 + 20, col * 20 : col * 20 + 20] = (
                    40,
                    90,
                    200,
                )
    cv2.line(logo, (0, 0), (139, 139), (0, 0, 0), 6)
    cv2.circle(logo, (100, 40), 25, (0, 160, 0), 5)
    return logo


def test_reports_each_logo_separately() -> None:
    """Only the logo that's actually in the frame is found."""
    frame, _ = place_logo(make_background(), make_logo(), (320, 240))
    pipeline = MultiLogoPipeline(
        {"bernard": make_logo(), "other": _other_logo()}
    )

    results = pipeline.analyze(frame).results

    assert results["bernard"].found
    assert not results["other"].found


def test_finds_two_logos_in_one_frame() -> None:
    """Several logos in the same frame are all found."""
    frame, _ = place_logo(make_background(), make_logo(), (180, 200))
    frame, _ = place_logo(frame, _other_logo(), (480, 260), angle=15)
    pipeline = MultiLogoPipeline(
        {"bernard": make_logo(), "other": _other_logo()}
    )

    results = pipeline.analyze(frame).results

    assert results["bernard"].found
    assert results["other"].found


def test_frame_is_processed_once_for_all_logos() -> None:
    """Keypoints of a frame are detected once, not once per logo."""
    calls: list[tuple[int, ...]] = []

    class CountingDetector(KeypointDetector):
        def detect(self, image, mask=None):
            calls.append(image.shape)
            return super().detect(image, mask)

    pipeline = MultiLogoPipeline(
        {"a": make_logo(), "b": _other_logo(), "c": make_logo(120)},
        detector=CountingDetector(),
    )
    calls.clear()

    pipeline.analyze(make_background())

    assert len(calls) == 1


def test_rejects_empty_logo_set() -> None:
    """Without logos there's nothing to look for."""
    with pytest.raises(ValueError, match="logo"):
        MultiLogoPipeline({})


def test_names_the_logo_without_keypoints() -> None:
    """A blank logo is reported by name."""
    blank = np.full((100, 100, 3), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="blank"):
        MultiLogoPipeline({"good": make_logo(), "blank": blank})


def test_single_logo_pipeline_still_works() -> None:
    """`LogoDetectionPipeline` keeps its interface on top of the multi one."""
    frame, _ = place_logo(make_background(), make_logo(), (320, 240))
    assert LogoDetectionPipeline(make_logo()).process(frame).found


@pytest.mark.parametrize("kind", list(DetectorKind))
def test_flann_matcher_finds_the_logo(kind: DetectorKind) -> None:
    """FLANN (KD-tree for SIFT, LSH for ORB) finds the logo too."""
    frame, _ = place_logo(make_background(), make_logo(), (320, 240))
    pipeline = LogoDetectionPipeline(
        make_logo(),
        detector=KeypointDetector(kind),
        matcher=LogoMatcher(matcher=MatcherKind.FLANN),
    )

    assert pipeline.process(frame).found


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flann_matcher_has_no_false_positives(seed: int) -> None:
    """FLANN's approximate search doesn't invent the logo in clutter."""
    pipeline = LogoDetectionPipeline(
        make_logo(), matcher=LogoMatcher(matcher=MatcherKind.FLANN)
    )

    assert not pipeline.process(make_background(seed)).found


def test_keeps_the_preprocessed_logos_for_display() -> None:
    """The logos as the extractor saw them, keyed by name."""
    pipeline = MultiLogoPipeline({"bernard": make_logo()})

    preprocessed = pipeline.preprocessed_logos["bernard"]

    assert preprocessed.ndim == 2
    assert preprocessed.shape == pipeline.logo_features["bernard"].image_shape


def test_analysis_uses_the_exposed_frame_preprocessing() -> None:
    """`frame_preprocessing` is the pipeline `analyze` runs on frames."""
    pipeline = MultiLogoPipeline({"bernard": make_logo()})
    frame = make_background()

    expected = pipeline.frame_preprocessing(frame)

    assert np.array_equal(pipeline.analyze(frame).preprocessed, expected)
