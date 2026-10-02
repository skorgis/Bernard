"""Find the cameras that can be opened with `cv2.VideoCapture(index)`."""

from dataclasses import dataclass
from pathlib import Path

import cv2

_LINUX_VIDEO_DEVICES = Path("/sys/class/video4linux")
_PROBE_COUNT = 5


@dataclass(frozen=True)
class Camera:
    """A capture device: the `cv2.VideoCapture` index and a readable name."""

    index: int
    name: str

    def __str__(self) -> str:
        """Dropdown label, e.g. `4: Anker PowerConf C200`."""
        return f"{self.index}: {self.name}"


def list_cameras(sysfs: Path = _LINUX_VIDEO_DEVICES) -> list[Camera]:
    """List cameras, with their names where the OS provides them.

    On Linux, each camera usually shows up as several `/dev/video*`
    nodes, of which only the one with sysfs `index` 0 delivers frames (the
    others carry metadata); only those are listed. Elsewhere, indices
    0-4 are probed by opening them.
    """
    if sysfs.is_dir():
        return _from_sysfs(sysfs)
    return _probe()


def _from_sysfs(sysfs: Path) -> list[Camera]:
    cameras = []
    for device in sysfs.glob("video*"):
        index_file = device / "index"
        if index_file.exists() and index_file.read_text().strip() != "0":
            continue
        name_file = device / "name"
        name = name_file.read_text().strip() if name_file.exists() else ""
        number = int(device.name.removeprefix("video"))
        cameras.append(Camera(number, name or f"Camera {number}"))
    return sorted(cameras, key=lambda camera: camera.index)


def _probe() -> list[Camera]:
    cameras = []
    for index in range(_PROBE_COUNT):
        capture = cv2.VideoCapture(index)
        if capture.isOpened():
            cameras.append(Camera(index, f"Camera {index}"))
        capture.release()
    return cameras
