"""Where frames come from: a camera, a video file or a still image."""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from picture_pipeline.cameras import Camera
from picture_pipeline.image import Image


class FrameSource(Protocol):
    """Something that delivers frames one at a time."""

    is_still: bool
    """Whether every `read` returns the same frame (a still image)."""

    def read(self) -> Image | None:
        """The next frame, or `None` if none could be read right now."""
        ...

    def release(self) -> None:
        """Free the underlying device or file."""
        ...


DEFAULT_CAMERA_RESOLUTION = (1920, 1080)
"""Asked for by default: OpenCV otherwise delivers only 640x480, where
small logos get too few pixels for keypoints."""


class CameraSource:
    """Frames from a camera, via `cv2.VideoCapture(index)`."""

    is_still = False

    def __init__(
        self,
        index: int,
        resolution: tuple[int, int] | None = DEFAULT_CAMERA_RESOLUTION,
    ) -> None:
        """Open camera `index`; raise if it can't be opened.

        `resolution` is `(width, height)` to request; the camera picks its
        nearest mode. `None` keeps the driver's default.
        """
        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            raise ValueError(f"camera {index} could not be opened")
        if resolution is not None:
            self._request_resolution(*resolution)

    def _request_resolution(self, width: int, height: int) -> None:
        # Uncompressed YUYV can't carry HD over USB, so most webcams offer
        # high resolutions only as MJPG.
        self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> Image | None:
        """The camera's latest frame, or `None` if it delivered none.

        A camera another program holds can report success with an empty
        frame; that counts as none too.
        """
        ok, frame = self._capture.read()
        if not ok or frame is None or frame.size == 0:
            return None
        return np.asarray(frame, dtype=np.uint8)

    def release(self) -> None:
        """Close the camera."""
        self._capture.release()


class FileSource:
    """Frames from an image (repeated) or a video (looped) file."""

    def __init__(self, path: Path | str) -> None:
        """Open `path` as an image, or failing that as a video."""
        path = Path(path)
        image = cv2.imread(str(path))
        self._capture: cv2.VideoCapture | None = None
        self._image: Image | None = None
        if image is not None:
            self._image = np.asarray(image, dtype=np.uint8)
        else:
            capture = cv2.VideoCapture(str(path))
            if not capture.isOpened() or not capture.read()[0]:
                raise ValueError(f"not a readable image or video: {path}")
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._capture = capture
        self.is_still = self._image is not None

    def read(self) -> Image | None:
        """The image again, or the video's next frame (from the start)."""
        if self._image is not None:
            return self._image
        assert self._capture is not None
        ok, frame = self._capture.read()
        if not ok:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._capture.read()
        return np.asarray(frame, dtype=np.uint8) if ok else None

    def release(self) -> None:
        """Close the video file, if any."""
        if self._capture is not None:
            self._capture.release()


def source_options(
    cameras: Sequence[Camera], file: Path | None = None
) -> dict[str, Callable[[], FrameSource]]:
    """Dropdown label -> function opening that source, file first.

    Sources are opened only when chosen, so listing them doesn't switch
    every camera on.
    """
    options: dict[str, Callable[[], FrameSource]] = {}
    if file is not None:
        options[f"Datei: {file.name}"] = lambda: FileSource(file)
    for camera in cameras:
        options[str(camera)] = lambda index=camera.index: CameraSource(index)
    return options
