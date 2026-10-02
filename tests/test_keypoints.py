"""Tests for `KeypointDetector`."""

import cv2
import numpy as np
import pytest

from picture_pipeline.keypoints import DetectorKind, KeypointDetector
from picture_pipeline.preprocessing import to_grayscale
from tests.picture_fixtures import make_logo


@pytest.mark.parametrize(
    ("kind", "norm_type"),
    [(DetectorKind.SIFT, cv2.NORM_L2), (DetectorKind.ORB, cv2.NORM_HAMMING)],
)
def test_detects_features_with_matching_norm(
    kind: DetectorKind, norm_type: int
) -> None:
    """Each detector finds keypoints and reports its descriptor distance."""
    features = KeypointDetector(kind).detect(to_grayscale(make_logo()))

    assert not features.is_empty
    assert features.descriptors is not None
    assert len(features.keypoints) == len(features.descriptors)
    assert features.norm_type == norm_type


def test_remembers_shape_of_the_source_image() -> None:
    """The matcher needs the logo's size to project its outline."""
    features = KeypointDetector().detect(to_grayscale(make_logo(160)))
    assert features.image_shape == (160, 160)


def test_blank_image_gives_empty_features() -> None:
    """No texture means no keypoints and no descriptors, not an error."""
    features = KeypointDetector().detect(np.zeros((100, 100), dtype=np.uint8))

    assert features.is_empty
    assert features.keypoints == ()
    assert features.descriptors is None


@pytest.mark.parametrize("kind", list(DetectorKind))
def test_max_features_limits_keypoints(kind: DetectorKind) -> None:
    """`max_features` caps how many keypoints a detector keeps."""
    features = KeypointDetector(kind, max_features=20).detect(
        to_grayscale(make_logo())
    )
    assert 0 < len(features.keypoints) <= 20


def test_rejects_non_positive_max_features() -> None:
    """`max_features` must be positive."""
    with pytest.raises(ValueError):
        KeypointDetector(max_features=0)
