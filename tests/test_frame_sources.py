"""Tests for the GUI's frame sources (cameras via a fake `VideoCapture`)."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from picture_pipeline import frame_sources
from picture_pipeline.cameras import Camera
from picture_pipeline.frame_sources import FileSource, source_options
from tests.picture_fixtures import make_background


def test_image_file_delivers_the_same_frame_every_time(tmp_path: Path) -> None:
    """A still image is a source that never runs out."""
    path = tmp_path / "frame.png"
    cv2.imwrite(str(path), make_background())
    source = FileSource(path)

    first, second = source.read(), source.read()

    assert first is not None and second is not None
    assert np.array_equal(first, second)
    assert source.is_still


def _write_video(path: Path, frame_count: int) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter.fourcc(*"MJPG"), 10, (64, 48)
    )
    for value in range(frame_count):
        writer.write(np.full((48, 64, 3), value * 40, dtype=np.uint8))
    writer.release()


def test_video_file_loops_at_the_end(tmp_path: Path) -> None:
    """A video starts over instead of running out while tuning."""
    path = tmp_path / "clip.avi"
    _write_video(path, frame_count=3)
    source = FileSource(path)

    frames = [source.read() for _ in range(5)]

    first, _, _, after_loop, _ = frames
    assert all(frame is not None for frame in frames)
    assert first is not None and after_loop is not None
    assert not source.is_still
    assert np.array_equal(first, after_loop)
    source.release()


def test_unreadable_file_is_rejected(tmp_path: Path) -> None:
    """A path that's neither image nor video fails with its name."""
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    with pytest.raises(ValueError, match="notes.txt"):
        FileSource(path)


def test_source_options_list_file_first_then_cameras(tmp_path: Path) -> None:
    """The dropdown offers the given file, then each camera, by label."""
    path = tmp_path / "frame.png"
    cv2.imwrite(str(path), make_background())

    options = source_options(
        [Camera(0, "Integrated"), Camera(4, "Anker")], path
    )

    assert list(options) == ["Datei: frame.png", "0: Integrated", "4: Anker"]


class _FakeCapture:
    """Stands in for `cv2.VideoCapture` and records what was requested."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.requested: dict[int, float] = {}
        self.next_read: tuple[bool, np.ndarray | None] = (False, None)

    def isOpened(self) -> bool:  # noqa: N802 - mirrors OpenCV's name
        return True

    def set(self, prop: int, value: float) -> bool:
        self.requested[prop] = value
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self.next_read

    def release(self) -> None:
        pass


def _open_fake_camera(
    monkeypatch: pytest.MonkeyPatch, **kwargs
) -> tuple[frame_sources.CameraSource, _FakeCapture]:
    captures: list[_FakeCapture] = []

    def fake_capture(index: int) -> _FakeCapture:
        captures.append(_FakeCapture(index))
        return captures[-1]

    monkeypatch.setattr(frame_sources.cv2, "VideoCapture", fake_capture)
    camera = frame_sources.CameraSource(3, **kwargs)
    return camera, captures[0]


def test_camera_requests_full_hd_mjpg_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a request, OpenCV would deliver only 640x480."""
    _, capture = _open_fake_camera(monkeypatch)

    assert capture.requested[cv2.CAP_PROP_FRAME_WIDTH] == 1920
    assert capture.requested[cv2.CAP_PROP_FRAME_HEIGHT] == 1080
    assert capture.requested[cv2.CAP_PROP_FOURCC] == cv2.VideoWriter.fourcc(
        *"MJPG"
    )


def test_camera_resolution_none_keeps_the_driver_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`resolution=None` asks the camera for nothing."""
    _, capture = _open_fake_camera(monkeypatch, resolution=None)

    assert capture.requested == {}


def test_camera_turns_an_empty_frame_into_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A busy camera can report success with an empty frame; that's none."""
    camera, capture = _open_fake_camera(monkeypatch)
    capture.next_read = (True, np.empty((0, 0, 3), dtype=np.uint8))

    assert camera.read() is None


def test_camera_returns_a_delivered_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real frame comes through as a uint8 image."""
    camera, capture = _open_fake_camera(monkeypatch)
    capture.next_read = (True, np.zeros((4, 6, 3), dtype=np.uint8))

    frame = camera.read()

    assert frame is not None
    assert frame.shape == (4, 6, 3)
