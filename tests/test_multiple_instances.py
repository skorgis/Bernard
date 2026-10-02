"""Tests for finding several copies of one logo in a frame."""

import numpy as np
import pytest

from picture_pipeline.matching import LogoMatcher
from picture_pipeline.pipeline import FrameAnalysis, MultiLogoPipeline
from tests.picture_fixtures import make_background, make_logo, place_logo

CENTERS = ((110.0, 240.0), (320.0, 240.0), (530.0, 240.0))
CENTER_TOLERANCE_PX = 10.0


def _frame_with_copies(centers=CENTERS, seed: int = 1) -> np.ndarray:
    frame = make_background(seed)
    for center in centers:
        frame, _ = place_logo(frame, make_logo(100), center)
    return frame


def _analyze(frame: np.ndarray, max_instances: int = 5) -> FrameAnalysis:
    pipeline = MultiLogoPipeline(
        {"logo": make_logo(100)},
        matcher=LogoMatcher(max_instances=max_instances),
    )
    return pipeline.analyze(frame)


def _centers(analysis: FrameAnalysis) -> list[np.ndarray]:
    return [
        result.corners.mean(axis=0)
        for result in analysis.instances["logo"]
        if result.corners is not None
    ]


def test_finds_every_copy_at_its_own_position() -> None:
    """Three copies give three outlines, one around each copy."""
    analysis = _analyze(_frame_with_copies())

    found = _centers(analysis)

    assert len(found) == 3
    for expected in CENTERS:
        distances = [np.linalg.norm(c - expected) for c in found]
        assert min(distances) < CENTER_TOLERANCE_PX


def test_copies_are_ordered_best_first() -> None:
    """The copy with the most inliers comes first."""
    instances = _analyze(_frame_with_copies()).instances["logo"]

    inliers = [result.inliers for result in instances]
    assert inliers == sorted(inliers, reverse=True)


def test_a_single_copy_is_found_once() -> None:
    """Leftover matches of a found copy don't make a second one."""
    analysis = _analyze(_frame_with_copies(centers=[(320.0, 240.0)]))

    assert len(analysis.instances["logo"]) == 1


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_clutter_alone_yields_no_copy(seed: int) -> None:
    """Searching for more copies must not invent any."""
    analysis = _analyze(make_background(seed))

    assert analysis.instances["logo"] == []
    assert not analysis.results["logo"].found


def test_one_copy_is_found_even_when_several_are_visible() -> None:
    """Identical copies don't make the matches ambiguous."""
    analysis = _analyze(_frame_with_copies(), max_instances=1)

    assert analysis.results["logo"].found
    assert len(analysis.instances["logo"]) == 1


def test_result_is_the_best_copy() -> None:
    """`results` keeps one result per logo: the best copy."""
    analysis = _analyze(_frame_with_copies())

    assert analysis.results["logo"] is analysis.instances["logo"][0]


def test_rejects_max_instances_below_one() -> None:
    """At least one copy must be searched for."""
    with pytest.raises(ValueError, match="max_instances"):
        LogoMatcher(max_instances=0)
