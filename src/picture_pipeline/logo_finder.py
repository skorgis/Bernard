"""Find known logos, e.g. a wheelchair symbol, in camera images.

How a logo is found, in four steps:

1. Keypoints: SIFT finds distinctive spots (corners, fine detail) in the
   logo and in the frame and describes each one with 128 numbers.
2. Matching: every logo keypoint looks for the two most similar keypoints
   in the frame.
3. Ratio test: a pair is kept only if the best partner is clearly more
   similar than the second best. Ambiguous pairs are mostly wrong.
4. Homography: the kept pairs must agree on one position, rotation and
   size of the logo. RANSAC finds the placement most pairs agree on; pairs
   that only look alike by chance don't fit it and are dropped. If enough
   pairs remain, the logo was found and its outline is drawn into the frame.

Logo and frame are both turned gray and contrast-equalized first, so that
lighting differences between them matter less.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

type Image = npt.NDArray[np.uint8]
"""An image as OpenCV uses it: `(h, w)` gray or `(h, w, 3)` BGR."""

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")

# Strongest keypoints SIFT keeps per image. More helps to find small logos
# in large frames, at the cost of speed.
SIFT_KEYPOINTS = 2000
# How far (in pixels) a pair may lie off the common placement and still
# count as agreeing with it.
RANSAC_THRESHOLD_PX = 5.0
# How much opposite sides of a found outline may differ in length. A real
# view of a flat logo stays close to a rectangle; chance matches give
# twisted or wildly stretched outlines, which this rejects.
MAX_SIDE_RATIO = 2.0
# Contrast equalization (CLAHE): OpenCV's usual strength and tile grid.
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILES = (8, 8)

GREEN = (0, 255, 0)


@dataclass(frozen=True)
class Detection:
    """Where a logo was found in a frame.

    `corners` are the logo's top-left, top-right, bottom-right and
    bottom-left corner in frame pixels (x, y), so they show its rotation.
    `matches` counts the keypoint pairs that agree on this placement: the
    more, the surer the detection.
    """

    corners: npt.NDArray[np.float32]
    matches: int

    @property
    def center(self) -> tuple[float, float]:
        """The middle of the logo in frame pixels (x, y)."""
        x, y = self.corners.mean(axis=0)
        return float(x), float(y)


type Keypoints = tuple[Sequence[cv2.KeyPoint], npt.NDArray[np.float32] | None]


class LogoFinder:
    """Looks for several logos at once in each frame.

    The settings are plain attributes, so they can be changed at any time,
    e.g. from sliders:

    - `ratio`: ratio test limit (0 to 1). Lower is stricter: fewer, but
      more reliable pairs.
    - `min_matches`: pairs that must agree before a logo counts as found.
      Raise it against false detections, lower it for small logos.
    - `frame_max_side`: shrink frames to this longer side before searching
      (0 = never). The biggest speed lever, but small logos get lost.
    """

    def __init__(
        self,
        logos: Mapping[str, Image],
        *,
        ratio: float = 0.75,
        min_matches: int = 10,
        frame_max_side: int = 0,
    ) -> None:
        """Prepare `logos` (name -> image) for searching.

        Raises `ValueError` if a logo has no keypoints: a plain shape
        without detail can't be found this way.
        """
        if not logos:
            raise ValueError("at least one logo is needed")
        self.ratio = ratio
        self.min_matches = min_matches
        self.frame_max_side = frame_max_side
        self._sift = cv2.SIFT.create(nfeatures=SIFT_KEYPOINTS)
        self._clahe = cv2.createCLAHE(CLAHE_CLIP_LIMIT, CLAHE_TILES)
        self._matcher = cv2.BFMatcher(cv2.NORM_L2)
        self._logos = {
            name: self._keypoints(logo) for name, logo in logos.items()
        }
        self._logo_sizes = {
            name: logo.shape[:2] for name, logo in logos.items()
        }
        plain = [
            name for name, (_, found) in self._logos.items() if found is None
        ]
        if plain:
            raise ValueError(
                f"no keypoints in logo(s) {', '.join(plain)}; "
                "a logo needs detail and corners"
            )

    def find(self, frame: Image) -> dict[str, Detection | None]:
        """Look for every logo in `frame`: its `Detection`, or `None`."""
        small, scale = _shrink(frame, self.frame_max_side)
        in_frame = self._keypoints(small)
        found = {}
        for name, in_logo in self._logos.items():
            detection = self._locate(in_logo, self._logo_sizes[name], in_frame)
            if detection is not None:
                # Back from the shrunk frame to the frame we were given.
                detection = Detection(
                    detection.corners / scale, detection.matches
                )
            found[name] = detection
        return found

    def _keypoints(self, image: Image) -> Keypoints:
        gray = (
            image
            if image.ndim == 2
            else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        )
        points, descriptors = self._sift.detectAndCompute(
            self._clahe.apply(gray), None
        )
        if descriptors is None:
            return points, None
        return points, np.asarray(descriptors, dtype=np.float32)

    def _locate(
        self, logo: Keypoints, logo_size: tuple[int, int], frame: Keypoints
    ) -> Detection | None:
        logo_points, logo_descriptors = logo
        frame_points, frame_descriptors = frame
        # knnMatch needs at least two frame keypoints to compare against.
        if (
            logo_descriptors is None
            or frame_descriptors is None
            or len(frame_points) < 2
        ):
            return None

        pairs = self._matcher.knnMatch(logo_descriptors, frame_descriptors, k=2)
        good = [
            best
            for best, second in (pair for pair in pairs if len(pair) == 2)
            if best.distance < self.ratio * second.distance
        ]
        if len(good) < self.min_matches:
            return None

        from_logo = np.array(
            [logo_points[m.queryIdx].pt for m in good], dtype=np.float32
        )
        to_frame = np.array(
            [frame_points[m.trainIdx].pt for m in good], dtype=np.float32
        )
        homography, agrees = cv2.findHomography(
            from_logo, to_frame, cv2.RANSAC, RANSAC_THRESHOLD_PX
        )
        if homography is None:
            return None
        matches = int(agrees.sum())
        corners = _outline_in_frame(homography, logo_size)
        if matches < self.min_matches or not _is_plausible(corners):
            return None
        return Detection(corners, matches)


def load_logos(folder: Path | str) -> dict[str, Image]:
    """Load every image in `folder` as a logo named after its file.

    `logos/rollstuhl.png` becomes the logo `"rollstuhl"`. Transparent
    pixels turn white: OpenCV would read them as black, and the edge
    between logo and black would produce keypoints that aren't in the logo.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"logo folder not found: {folder.resolve()}")
    logos = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in IMAGE_SUFFIXES:
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise ValueError(f"could not read image: {path}")
            logos[path.stem] = _to_bgr(image)
    if not logos:
        raise ValueError(
            f"no logo images in {folder.resolve()}; "
            f"expected files ending in {', '.join(IMAGE_SUFFIXES)}"
        )
    return logos


def draw(frame: Image, detections: Mapping[str, Detection | None]) -> Image:
    """A copy of `frame` with the outline and name of every found logo."""
    canvas = (
        frame.copy()
        if frame.ndim == 3
        else np.asarray(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR), dtype=np.uint8)
    )
    for name, detection in detections.items():
        if detection is None:
            continue
        outline = np.round(detection.corners).astype(np.int32)
        cv2.polylines(
            canvas, [outline], isClosed=True, color=GREEN, thickness=3
        )
        x, y = outline.min(axis=0)
        cv2.putText(
            canvas,
            name,
            (int(x), max(int(y) - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            GREEN,
            2,
        )
    return canvas


def _shrink(frame: Image, max_side: int) -> tuple[Image, float]:
    """`frame` shrunk to `max_side` (never enlarged), and the scale used."""
    longer = max(frame.shape[:2])
    if max_side <= 0 or longer <= max_side:
        return frame, 1.0
    scale = max_side / longer
    small = cv2.resize(
        frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
    )
    return np.asarray(small, dtype=np.uint8), scale


def _outline_in_frame(
    homography: Any, logo_size: tuple[int, int]
) -> npt.NDArray[np.float32]:
    height, width = logo_size
    corners = np.array(
        [[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32
    )
    projected = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), homography)
    return np.asarray(projected, dtype=np.float32).reshape(4, 2)


def _is_plausible(corners: npt.NDArray[np.float32]) -> bool:
    """Whether `corners` could be a flat logo seen by a camera.

    It must be convex, have some area, and opposite sides may differ by at
    most `MAX_SIDE_RATIO` (perspective shortens them somewhat).
    """
    if not cv2.isContourConvex(corners) or cv2.contourArea(corners) <= 1:
        return False
    sides = [
        float(np.linalg.norm(corners[i] - corners[(i + 1) % 4]))
        for i in range(4)
    ]
    return all(
        max(a, b) <= MAX_SIDE_RATIO * min(a, b)
        for a, b in ((sides[0], sides[2]), (sides[1], sides[3]))
    )


def _to_bgr(image: cv2.typing.MatLike) -> Image:
    if image.ndim == 2:
        return np.asarray(
            cv2.cvtColor(image, cv2.COLOR_GRAY2BGR), dtype=np.uint8
        )
    if image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255
        on_white = image[:, :, :3] * alpha + 255 * (1 - alpha)
        return np.round(on_white).astype(np.uint8)
    return np.asarray(image, dtype=np.uint8)
