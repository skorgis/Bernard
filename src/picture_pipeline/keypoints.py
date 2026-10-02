"""Keypoint detection, used identically for the logo and for each frame.

Descriptors are only comparable when they come from the same algorithm,
so one `KeypointDetector` instance should serve both sides of a match.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from picture_pipeline.image import Image


class DetectorKind(StrEnum):
    """The keypoint algorithms available.

    AKAZE and BRISK come from `opencv-contrib-python` (`cv2.xfeatures2d`).
    """

    SIFT = "sift"
    ORB = "orb"
    AKAZE = "akaze"
    BRISK = "brisk"


@dataclass(frozen=True)
class _DetectorSpec:
    create: Callable[[int], Any]
    norm_type: int


_SPECS: dict[DetectorKind, _DetectorSpec] = {
    DetectorKind.SIFT: _DetectorSpec(
        create=lambda n: cv2.SIFT.create(nfeatures=n),
        norm_type=cv2.NORM_L2,
    ),
    # ORB drops keypoints within `edgeThreshold` px of the image border
    # (default 31). On a small logo that discards most of its area and
    # leaves keypoints clustered in the middle, which makes the homography
    # extrapolate badly; 15 keeps the logo's edges.
    DetectorKind.ORB: _DetectorSpec(
        create=lambda n: cv2.ORB.create(
            nfeatures=n, edgeThreshold=15, patchSize=15
        ),
        norm_type=cv2.NORM_HAMMING,
    ),
    DetectorKind.AKAZE: _DetectorSpec(
        create=lambda n: cv2.xfeatures2d.AKAZE.create(max_points=n),
        norm_type=cv2.NORM_HAMMING,
    ),
    # BRISK has no keypoint limit of its own; `detect` keeps the
    # `max_features` strongest instead.
    DetectorKind.BRISK: _DetectorSpec(
        create=lambda _n: cv2.xfeatures2d.BRISK.create(),
        norm_type=cv2.NORM_HAMMING,
    ),
}


@dataclass(frozen=True)
class Features:
    """Keypoints and descriptors of one image.

    `descriptors` has one row per keypoint, or is `None` when nothing was
    found. `norm_type` is the OpenCV distance that compares these
    descriptors (L2 for SIFT, Hamming for ORB). `image_shape` is the
    `(height, width)` of the image they came from.
    """

    keypoints: tuple[cv2.KeyPoint, ...]
    descriptors: npt.NDArray[Any] | None
    norm_type: int
    image_shape: tuple[int, int]

    @property
    def is_empty(self) -> bool:
        """Whether no keypoint was found."""
        return self.descriptors is None


class KeypointDetector:
    """Finds keypoints and computes their descriptors with one algorithm."""

    def __init__(
        self, kind: DetectorKind = DetectorKind.SIFT, max_features: int = 1000
    ) -> None:
        """Create a detector of `kind` keeping the `max_features` best."""
        if max_features <= 0:
            raise ValueError(f"max_features must be positive: {max_features}")
        spec = _SPECS[kind]
        self.kind = kind
        self._detector = spec.create(max_features)
        self._norm_type = spec.norm_type
        self._max_features = max_features

    def detect(self, image: Image, mask: Image | None = None) -> Features:
        """Detect keypoints in `image`, optionally only where `mask` > 0."""
        keypoints, descriptors = self._detector.detectAndCompute(image, mask)
        # SIFT can return a few more than `nfeatures` when several
        # keypoints tie on response, so trim to keep the limit exact.
        ranked = sorted(
            range(len(keypoints)), key=lambda i: -keypoints[i].response
        )[: self._max_features]
        kept = tuple(keypoints[i] for i in ranked)
        if descriptors is None or not kept:
            return Features((), None, self._norm_type, _shape(image))
        return Features(
            kept,
            np.asarray(descriptors)[ranked],
            self._norm_type,
            _shape(image),
        )


def _shape(image: Image) -> tuple[int, int]:
    return image.shape[0], image.shape[1]
