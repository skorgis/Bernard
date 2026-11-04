"""Synthetic logos and frames for the picture pipeline tests."""

import cv2
import numpy as np
import numpy.typing as npt

from picture_pipeline.logo_finder import Image

FRAME_SHAPE = (480, 640)


def make_logo(size: int = 160, seed: int = 7) -> Image:
    """A textured, asymmetric symbol with plenty of corners to detect.

    Different seeds give different symbols.
    """
    rng = np.random.default_rng(seed)
    logo = np.full((size, size, 3), 255, dtype=np.uint8)
    for _ in range(25):
        color = tuple(int(c) for c in rng.integers(0, 200, 3))
        x1, y1, x2, y2 = (int(v) for v in rng.integers(0, size, 4))
        match int(rng.integers(0, 3)):
            case 0:
                cv2.rectangle(logo, (x1, y1), (x2, y2), color, -1)
            case 1:
                radius = int(rng.integers(5, size // 4))
                cv2.circle(logo, (x1, y1), radius, color, 2)
            case _:
                cv2.line(logo, (x1, y1), (x2, y2), color, 3)
    cv2.putText(
        logo, "BG", (20, size - 20), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4
    )
    cv2.rectangle(logo, (0, 0), (size - 1, size - 1), (0, 0, 0), 4)
    return logo


def make_background(seed: int = 1) -> Image:
    """Clutter without the logo: soft shapes plus mild noise."""
    rng = np.random.default_rng(seed)
    height, width = FRAME_SHAPE
    frame = np.full((height, width, 3), 180, dtype=np.uint8)
    for _ in range(40):
        color = tuple(int(c) for c in rng.integers(60, 230, 3))
        x, y = int(rng.integers(0, width)), int(rng.integers(0, height))
        w, h = int(rng.integers(20, 120)), int(rng.integers(20, 120))
        cv2.ellipse(
            frame,
            (x, y),
            (w // 2, h // 2),
            float(rng.integers(0, 180)),
            0,
            360,
            color,
            -1,
        )
    noise = rng.normal(0, 6, frame.shape)
    return np.clip(frame + noise, 0, 255).astype(np.uint8)


def place_logo(
    frame: Image,
    logo: Image,
    center: tuple[float, float],
    angle: float = 0.0,
    scale: float = 1.0,
) -> tuple[Image, npt.NDArray[np.float32]]:
    """Paste `logo` into a copy of `frame`; return it and the logo corners.

    The corners are the logo's outline in frame coordinates, in the order
    top-left, top-right, bottom-right, bottom-left of the unrotated logo.
    """
    logo_h, logo_w = logo.shape[:2]
    transform = cv2.getRotationMatrix2D((logo_w / 2, logo_h / 2), angle, scale)
    transform[:, 2] += np.array(center) - np.array([logo_w / 2, logo_h / 2])

    frame_h, frame_w = frame.shape[:2]
    warped = cv2.warpAffine(logo, transform, (frame_w, frame_h))
    mask = cv2.warpAffine(
        np.full((logo_h, logo_w), 255, dtype=np.uint8),
        transform,
        (frame_w, frame_h),
    )
    composed = frame.copy()
    composed[mask > 0] = warped[mask > 0]

    corners = np.array(
        [[0, 0], [logo_w, 0], [logo_w, logo_h], [0, logo_h]], dtype=np.float32
    )
    homogeneous = np.hstack([corners, np.ones((4, 1), dtype=np.float32)])
    return composed, (homogeneous @ transform.T).astype(np.float32)
