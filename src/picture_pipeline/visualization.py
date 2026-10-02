"""Draw results, keypoints and logos onto a frame, for viewing or saving."""

from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from picture_pipeline.image import Image
from picture_pipeline.keypoints import Features
from picture_pipeline.matching import MatchResult

type Color = tuple[int, int, int]

FOUND_COLOR: Color = (0, 255, 0)
NOT_FOUND_COLOR: Color = (0, 0, 255)
KEYPOINT_COLOR: Color = (0, 200, 255)
LOGO_COLORS: tuple[Color, ...] = (
    (0, 255, 0),
    (255, 128, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 0),
    (128, 0, 255),
)
"""Distinct BGR colors to tell several logos apart; cycle through them."""
_MAX_ASPECT_DEVIATION = 0.02
_CAPTION_HEIGHT = 18


def draw_detection(
    frame: Image,
    result: MatchResult,
    color: Color = FOUND_COLOR,
    thickness: int = 3,
    bounding_box: bool = False,
    show_status: bool = True,
    label: str | None = None,
) -> Image:
    """Return a BGR copy of `frame` with the detected logo marked.

    Draws the logo's outline (which follows its rotation), or with
    `bounding_box=True` the upright rectangle enclosing it, and `label`
    (e.g. the logo's name) above it. With `show_status`, a line in the
    top-left corner says whether the logo was found. `frame` is never
    modified.

    `frame` may be the original frame even if the frame preprocessing
    resized it: the outline is scaled from `result.frame_shape` to
    `frame`'s size. That's impossible after a step that changed the
    aspect ratio (e.g. a crop) — draw on the preprocessed frame then.
    """
    canvas = _bgr_copy(frame)
    if result.found and result.corners is not None:
        corners = _scale_to(result.corners, result.frame_shape, _shape(frame))
        points = np.round(corners).astype(np.int32).reshape(-1, 1, 2)
        if bounding_box:
            x, y, width, height = cv2.boundingRect(points)
            cv2.rectangle(
                canvas,
                (x, y),
                (x + width - 1, y + height - 1),
                color,
                thickness,
            )
        else:
            cv2.polylines(canvas, [points], True, color, thickness)
        if label:
            x, y = int(points[:, 0, 0].min()), int(points[:, 0, 1].min())
            cv2.putText(
                canvas,
                label,
                (x, max(y - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )
    if show_status:
        _draw_status(canvas, result, color)
    return canvas


def draw_keypoints(
    frame: Image, features: Features, color: Color = KEYPOINT_COLOR
) -> Image:
    """Return a BGR copy of `frame` with `features`' keypoints as circles.

    Like `draw_detection`, `frame` may be the original frame: keypoints
    are scaled from `features.image_shape` to `frame`'s size.
    """
    canvas = _bgr_copy(frame)
    if not features.keypoints:
        return canvas
    points = np.array([kp.pt for kp in features.keypoints], dtype=np.float32)
    scaled = _scale_to(points, features.image_shape, _shape(frame))
    for x, y in np.round(scaled).astype(np.int32):
        cv2.circle(canvas, (int(x), int(y)), 3, color, 1)
    return canvas


def draw_logo_insets(
    frame: Image,
    logos: Sequence[tuple[Image, Color]],
    max_side: int = 120,
    margin: int = 8,
    border: int = 2,
) -> Image:
    """Return a BGR copy of `frame` with each logo as a framed thumbnail.

    The thumbnails stack down the top-right corner, each inside a border
    of its color (use the color its outline is drawn in). They shrink
    with small frames; logos that no longer fit are left out.
    """
    canvas = _bgr_copy(frame)
    height, width = _shape(canvas)
    side = min(max_side, width // 4, height // 3)
    if side < 1:
        return canvas
    top = margin
    for logo, color in logos:
        thumbnail = _thumbnail(logo, side)
        thumb_height, thumb_width = _shape(thumbnail)
        bottom = top + thumb_height + 2 * border
        if bottom > height - margin:
            break
        left = width - margin - thumb_width - 2 * border
        right = left + thumb_width + 2 * border
        cv2.rectangle(canvas, (left, top), (right - 1, bottom - 1), color, -1)
        canvas[
            top + border : bottom - border, left + border : right - border
        ] = thumbnail
        top = bottom + margin
    return canvas


def draw_stage_strip(
    stages: Sequence[tuple[str, Image]],
    tile_width: int = 160,
    columns: int = 6,
) -> Image:
    """Tile labelled images, e.g. each preprocessing step's output.

    Every stage becomes a `tile_width`-wide thumbnail (aspect kept) with
    its label in a bar below, `columns` per row. Tiles share the first
    stage's height, so steps that resize show at the same size.
    """
    if not stages:
        raise ValueError("draw_stage_strip needs at least one stage")
    first_height, first_width = _shape(stages[0][1])
    image_height = max(round(tile_width * first_height / first_width), 1)
    tiles = [
        _stage_tile(label, image, tile_width, image_height)
        for label, image in stages
    ]
    blank = np.zeros_like(tiles[0])
    rows = [
        tiles[start : start + columns]
        for start in range(0, len(tiles), columns)
    ]
    if len(rows) > 1:
        rows[-1] += [blank] * (columns - len(rows[-1]))
    return np.vstack([np.hstack(row) for row in rows])


def _stage_tile(
    label: str, image: Image, width: int, image_height: int
) -> Image:
    resized = cv2.resize(
        image, (width, image_height), interpolation=cv2.INTER_AREA
    )
    picture = _bgr_copy(np.asarray(resized, dtype=np.uint8))
    caption = np.full((_CAPTION_HEIGHT, width, 3), 40, dtype=np.uint8)
    scale = 0.4
    while (
        scale > 0.2
        and cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
        > width - 6
    ):
        scale -= 0.05
    cv2.putText(
        caption,
        label,
        (3, _CAPTION_HEIGHT - 6),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    tile = np.vstack([picture, caption])
    cv2.rectangle(tile, (0, 0), (width - 1, tile.shape[0] - 1), (90, 90, 90))
    return tile


def _thumbnail(logo: Image, side: int) -> Image:
    height, width = _shape(logo)
    scale = side / max(height, width)
    size = (max(round(width * scale), 1), max(round(height * scale), 1))
    resized = cv2.resize(logo, size, interpolation=cv2.INTER_AREA)
    return _bgr_copy(np.asarray(resized, dtype=np.uint8))


def _bgr_copy(frame: Image) -> Image:
    if frame.ndim == 2:
        return np.asarray(
            cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR), dtype=np.uint8
        )
    return frame.copy()


def _scale_to(
    points: npt.NDArray[np.float32],
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> npt.NDArray[np.float32]:
    scale_y = target_shape[0] / source_shape[0]
    scale_x = target_shape[1] / source_shape[1]
    if abs(scale_x - scale_y) > _MAX_ASPECT_DEVIATION * max(scale_x, scale_y):
        raise ValueError(
            f"frame {target_shape} and result frame_shape {source_shape} "
            "differ in aspect ratio; the frame preprocessing must have "
            "cropped it, so draw on the preprocessed frame instead"
        )
    return points * np.array([scale_x, scale_y], dtype=np.float32)


def _draw_status(canvas: Image, result: MatchResult, color: Color) -> None:
    if result.found:
        text, text_color = f"logo found ({result.inliers} inliers)", color
    else:
        text, text_color = "logo not found", NOT_FOUND_COLOR
    cv2.putText(
        canvas, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2
    )


def _shape(image: Image) -> tuple[int, int]:
    return image.shape[0], image.shape[1]
