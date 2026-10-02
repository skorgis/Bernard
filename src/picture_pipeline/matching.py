"""Decide whether a logo appears in a frame, and where.

Three filters, each stricter than the last:

1. kNN descriptor matching: each frame keypoint's two nearest logo
   keypoints. Searching from the frame side lets several copies of the
   logo all match: searched the other way, a logo keypoint's two nearest
   frame keypoints would be the same point on two copies, and stage 2
   would discard it as ambiguous.
2. Lowe's ratio test: keep a match only if the nearest is clearly better
   than the second nearest — ambiguous matches are mostly wrong.
3. RANSAC homography: the remaining matches must agree on one geometric
   placement of the logo. Matches that happen to look alike but sit in
   random places (clutter) don't, so they fall out as outliers.

`match_all` repeats stage 3 for further copies: it sets the found copy's
inliers, and every match inside its outline, aside and fits again.
"""

import dataclasses
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from picture_pipeline.keypoints import Features

_MIN_HOMOGRAPHY_POINTS = 4
_FLANN_INDEX_KDTREE = 1
_FLANN_INDEX_LSH = 6


class MatcherKind(StrEnum):
    """How nearest descriptors are searched for in stage 1.

    `BRUTE_FORCE` compares every pair: exact, and fast enough for a few
    thousand keypoints. `FLANN` uses an approximate index (a KD-tree for
    SIFT, LSH for ORB): faster with many keypoints, occasionally missing
    the true nearest neighbour.
    """

    BRUTE_FORCE = "brute_force"
    FLANN = "flann"


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching a logo against one frame.

    `corners` is the logo's outline in frame coordinates — 4 points,
    top-left, top-right, bottom-right, bottom-left of the logo — and
    `homography` maps logo to frame coordinates; both are `None` unless
    the logo was found. `frame_shape` is the `(height, width)` of the
    frame those coordinates refer to: the frame *after* preprocessing.
    """

    found: bool
    good_matches: int
    inliers: int
    frame_shape: tuple[int, int]
    homography: npt.NDArray[np.float64] | None = None
    corners: npt.NDArray[np.float32] | None = None


class LogoMatcher:
    """Matches logo features against frame features."""

    def __init__(
        self,
        ratio: float = 0.75,
        min_good_matches: int = 10,
        min_inliers: int = 8,
        ransac_threshold: float = 5.0,
        max_side_ratio: float = 2.0,
        matcher: MatcherKind = MatcherKind.BRUTE_FORCE,
        max_instances: int = 1,
    ) -> None:
        """Create a matcher.

        `ratio` is Lowe's ratio (lower is stricter). The logo counts as
        found when at least `min_good_matches` survive the ratio test and
        at least `min_inliers` of them fit one homography within
        `ransac_threshold` pixels, and its projected outline passes
        `is_plausible_outline` with `max_side_ratio`. `matcher` picks the
        nearest-neighbour search (see `MatcherKind`). `match_all` finds up
        to `max_instances` copies, each held to the same criteria.
        """
        if not 0 < ratio < 1:
            raise ValueError(f"ratio must be between 0 and 1: {ratio}")
        if min_inliers < _MIN_HOMOGRAPHY_POINTS:
            raise ValueError(
                f"min_inliers must be at least {_MIN_HOMOGRAPHY_POINTS}: "
                f"{min_inliers}"
            )
        if max_side_ratio < 1:
            raise ValueError(
                f"max_side_ratio must be at least 1: {max_side_ratio}"
            )
        if max_instances < 1:
            raise ValueError(
                f"max_instances must be at least 1: {max_instances}"
            )
        self._ratio = ratio
        self._min_good_matches = max(min_good_matches, min_inliers)
        self._min_inliers = min_inliers
        self._ransac_threshold = ransac_threshold
        self._max_side_ratio = max_side_ratio
        self._matcher_kind = matcher
        self._max_instances = max_instances

    def match(self, logo: Features, frame: Features) -> MatchResult:
        """Look for `logo` in `frame`: its best copy, or why there's none."""
        return self.match_all(logo, frame)[0]

    def match_all(self, logo: Features, frame: Features) -> list[MatchResult]:
        """Every copy of `logo` in `frame`, most inliers first.

        Up to `max_instances` copies. If there's none, the list holds the
        one failed attempt (`found=False`) with its match counts.
        """
        if logo.norm_type != frame.norm_type:
            raise ValueError(
                "logo and frame features come from different detector kinds"
            )
        if logo.descriptors is None or frame.descriptors is None:
            return [self._not_found(frame, good_matches=0)]

        remaining = self._ratio_test(
            logo.descriptors, frame.descriptors, logo.norm_type
        )
        good_matches = len(remaining)
        copies: list[MatchResult] = []
        while len(copies) < self._max_instances:
            if len(_best_per_logo_point(remaining)) < self._min_good_matches:
                break
            result, used = self._fit_copy(logo, frame, remaining)
            if not result.found:
                if not copies:
                    copies.append(_with_good_matches(result, good_matches))
                break
            copies.append(_with_good_matches(result, good_matches))
            remaining = _outside_copy(remaining, used, frame, result)
        if not copies:
            return [self._not_found(frame, good_matches)]
        return sorted(copies, key=lambda copy: copy.inliers, reverse=True)

    def _not_found(self, frame: Features, good_matches: int) -> MatchResult:
        return MatchResult(
            found=False,
            good_matches=good_matches,
            inliers=0,
            frame_shape=frame.image_shape,
        )

    def _ratio_test(
        self,
        logo_descriptors: npt.NDArray[Any],
        frame_descriptors: npt.NDArray[Any],
        norm_type: int,
    ) -> list[cv2.DMatch]:
        """Matches with `queryIdx` in the frame, `trainIdx` in the logo."""
        matcher = _create_matcher(self._matcher_kind, norm_type)
        candidates = matcher.knnMatch(frame_descriptors, logo_descriptors, k=2)
        return [
            pair[0]
            for pair in candidates
            if len(pair) == 2
            and pair[0].distance < self._ratio * pair[1].distance
        ]

    def _fit_copy(
        self, logo: Features, frame: Features, remaining: list[cv2.DMatch]
    ) -> tuple[MatchResult, set[int]]:
        """Fit one copy: its result and the frame keypoints supporting it.

        RANSAC on one match per logo keypoint gives a rough placement.
        Then every remaining match is checked against it, keeping per
        logo keypoint the one that fits best: this recovers correct
        matches the first pass passed over because another one looked
        closer. A least-squares fit on those refines the placement.
        """
        candidates = _best_per_logo_point(remaining)
        rough, _ = cv2.findHomography(
            _logo_points(logo, candidates),
            _frame_points(frame, candidates),
            # USAC: the same placements as classic RANSAC here, but it stops
            # far sooner when few matches belong to one copy (~9x faster).
            cv2.USAC_DEFAULT,
            self._ransac_threshold,
        )
        if rough is None:
            return self._not_found(frame, len(candidates)), set()
        rough = np.asarray(rough, dtype=np.float64)
        support = self._supporting(logo, frame, remaining, rough)
        homography = rough
        if len(support) >= _MIN_HOMOGRAPHY_POINTS:
            refined, _ = cv2.findHomography(
                _logo_points(logo, support), _frame_points(frame, support), 0
            )
            homography = rough if refined is None else refined

        inliers = len(support)
        corners = _project_outline(homography, logo.image_shape)
        if inliers < self._min_inliers or not is_plausible_outline(
            corners, self._max_side_ratio
        ):
            return MatchResult(
                found=False,
                good_matches=len(candidates),
                inliers=inliers,
                frame_shape=frame.image_shape,
            ), set()
        return MatchResult(
            found=True,
            good_matches=len(candidates),
            inliers=inliers,
            frame_shape=frame.image_shape,
            homography=np.asarray(homography, dtype=np.float64),
            corners=corners,
        ), {match.queryIdx for match in support}

    def _supporting(
        self,
        logo: Features,
        frame: Features,
        matches: list[cv2.DMatch],
        homography: npt.NDArray[np.float64],
    ) -> list[cv2.DMatch]:
        """Per logo keypoint, the match `homography` maps best.

        Only matches within `ransac_threshold` pixels count.
        """
        projected = cv2.perspectiveTransform(
            _logo_points(logo, matches), homography
        ).reshape(-1, 2)
        errors = np.linalg.norm(
            projected - _frame_points(frame, matches).reshape(-1, 2), axis=1
        )
        best: dict[int, tuple[float, cv2.DMatch]] = {}
        for match, error in zip(matches, errors, strict=True):
            if error > self._ransac_threshold:
                continue
            current = best.get(match.trainIdx)
            if current is None or error < current[0]:
                best[match.trainIdx] = (float(error), match)
        return [match for _, match in best.values()]


def _logo_points(
    logo: Features, matches: list[cv2.DMatch]
) -> npt.NDArray[np.float32]:
    return np.array(
        [logo.keypoints[m.trainIdx].pt for m in matches], dtype=np.float32
    ).reshape(-1, 1, 2)


def _frame_points(
    frame: Features, matches: list[cv2.DMatch]
) -> npt.NDArray[np.float32]:
    return np.array(
        [frame.keypoints[m.queryIdx].pt for m in matches], dtype=np.float32
    ).reshape(-1, 1, 2)


def _with_good_matches(result: MatchResult, good_matches: int) -> MatchResult:
    """Report all ratio-test survivors, not only those left for this copy."""
    return dataclasses.replace(result, good_matches=good_matches)


def _best_per_logo_point(matches: list[cv2.DMatch]) -> list[cv2.DMatch]:
    """The closest match for each logo keypoint.

    Several copies need several frame points per logo point, but one fit
    must use each logo point once, or duplicates inflate the inliers and
    skew the homography. The others wait for the next copy's fit.
    """
    best: dict[int, cv2.DMatch] = {}
    for match in matches:
        current = best.get(match.trainIdx)
        if current is None or match.distance < current.distance:
            best[match.trainIdx] = match
    return list(best.values())


def _outside_copy(
    matches: list[cv2.DMatch],
    used: set[int],
    frame: Features,
    copy: MatchResult,
) -> list[cv2.DMatch]:
    """The `matches` left for further copies once `copy` is found.

    Drops those `used` by `copy` (frame keypoint indices) and those inside
    its outline: the outliers inside it would otherwise form a second,
    overlapping copy.
    """
    assert copy.corners is not None
    outline = copy.corners.reshape(-1, 1, 2)
    return [
        match
        for match in matches
        if match.queryIdx not in used
        and cv2.pointPolygonTest(
            outline, frame.keypoints[match.queryIdx].pt, False
        )
        < 0
    ]


def _create_matcher(kind: MatcherKind, norm_type: int) -> cv2.DescriptorMatcher:
    if kind is MatcherKind.BRUTE_FORCE:
        return cv2.BFMatcher(norm_type)
    index: cv2.typing.IndexParams
    if norm_type == cv2.NORM_L2:
        index = {"algorithm": _FLANN_INDEX_KDTREE, "trees": 5}
    else:
        index = {
            "algorithm": _FLANN_INDEX_LSH,
            "table_number": 6,
            "key_size": 12,
            "multi_probe_level": 1,
        }
    return cv2.FlannBasedMatcher(index, {"checks": 50})


def _project_outline(
    homography: Any, shape: tuple[int, int]
) -> npt.NDArray[np.float32]:
    height, width = shape
    outline = np.array(
        [[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32
    )
    projected = cv2.perspectiveTransform(outline.reshape(-1, 1, 2), homography)
    return np.asarray(projected, dtype=np.float32).reshape(4, 2)


def is_plausible_outline(
    corners: npt.NDArray[np.float32], max_side_ratio: float
) -> bool:
    """Whether `corners` could be a flat logo seen by a camera.

    RANSAC can fit a homography to a few chance inliers, or to inliers
    clustered in one part of the logo, that projects the logo's outline
    into a twisted, collapsed or wildly stretched shape. A real view is a
    convex quadrilateral with some area whose opposite sides differ in
    length by at most `max_side_ratio` (perspective makes them differ
    somewhat; pure rotation/scale keeps them equal).
    """
    contour = corners.reshape(-1, 1, 2)
    if not cv2.isContourConvex(contour) or cv2.contourArea(contour) <= 1:
        return False
    sides = [
        float(np.linalg.norm(corners[i] - corners[(i + 1) % 4]))
        for i in range(4)
    ]
    return all(
        max(a, b) <= max_side_ratio * min(a, b)
        for a, b in ((sides[0], sides[2]), (sides[1], sides[3]))
    )
