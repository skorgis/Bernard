"""Load every logo image in a folder."""

from pathlib import Path

import cv2
import numpy as np

from picture_pipeline.image import Image

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def load_logos(folder: Path | str) -> dict[str, Image]:
    """Load each image in `folder` as a BGR logo, named by its file stem.

    Transparent pixels (PNG alpha) are flattened onto white: left as they
    are, OpenCV would read them as black, and the hard edge between the
    logo and that black would produce keypoints that aren't in the logo.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"logo folder not found: {folder.resolve()}")
    logos = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError(f"could not read image: {path}")
        logos[path.stem] = _to_bgr(np.asarray(image, dtype=np.uint8))
    if not logos:
        raise ValueError(
            f"no logo images in {folder.resolve()}; "
            f"expected files ending in {', '.join(IMAGE_SUFFIXES)}"
        )
    return logos


def _to_bgr(image: Image) -> Image:
    if image.ndim == 2:
        return np.asarray(
            cv2.cvtColor(image, cv2.COLOR_GRAY2BGR), dtype=np.uint8
        )
    if image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255
        white = np.full_like(image[:, :, :3], 255, dtype=np.float32)
        blended = image[:, :, :3] * alpha + white * (1 - alpha)
        return np.round(blended).astype(np.uint8)
    return image
