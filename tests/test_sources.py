"""Tests for camera listing, logo loading and the new drawing helpers."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from picture_pipeline.cameras import Camera, list_cameras
from picture_pipeline.logo_loading import load_logos
from picture_pipeline.matching import MatchResult
from picture_pipeline.pipeline import MultiLogoPipeline
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    resize_to_max_side,
    to_grayscale,
)
from picture_pipeline.visualization import draw_detection, draw_keypoints
from tests.picture_fixtures import make_background, make_logo


def _fake_video_device(sysfs: Path, node: str, name: str, index: int) -> None:
    device = sysfs / node
    device.mkdir(parents=True)
    (device / "name").write_text(f"{name}\n")
    (device / "index").write_text(f"{index}\n")


def test_lists_only_capture_nodes_with_their_names(tmp_path: Path) -> None:
    """Metadata nodes (index > 0) of the same camera are skipped."""
    _fake_video_device(tmp_path, "video0", "Integrated Camera", 0)
    _fake_video_device(tmp_path, "video1", "Integrated Camera", 1)
    _fake_video_device(tmp_path, "video4", "Anker PowerConf C200", 0)
    _fake_video_device(tmp_path, "video5", "Anker PowerConf C200", 1)

    cameras = list_cameras(sysfs=tmp_path)

    assert cameras == [
        Camera(0, "Integrated Camera"),
        Camera(4, "Anker PowerConf C200"),
    ]


def test_camera_label_shows_number_and_name() -> None:
    """The dropdown entry identifies the device unambiguously."""
    assert str(Camera(4, "Anker PowerConf C200")) == "4: Anker PowerConf C200"


def test_loads_every_image_in_the_folder_by_file_stem(tmp_path: Path) -> None:
    """Each image becomes one logo, named after its file."""
    cv2.imwrite(str(tmp_path / "bernard.png"), make_logo())
    cv2.imwrite(str(tmp_path / "asfinag.jpg"), make_logo(120))
    (tmp_path / "notes.txt").write_text("not an image")

    logos = load_logos(tmp_path)

    assert sorted(logos) == ["asfinag", "bernard"]
    assert logos["bernard"].shape == (160, 160, 3)


def test_transparent_png_is_flattened_onto_white(tmp_path: Path) -> None:
    """Transparent pixels become white instead of black."""
    rgba = np.zeros((50, 50, 4), dtype=np.uint8)
    rgba[10:40, 10:40] = (0, 0, 255, 255)
    cv2.imwrite(str(tmp_path / "logo.png"), rgba)

    logo = load_logos(tmp_path)["logo"]

    assert logo.shape == (50, 50, 3)
    assert logo[0, 0].tolist() == [255, 255, 255]
    assert logo[25, 25].tolist() == [0, 0, 255]


def test_missing_folder_explains_what_to_do(tmp_path: Path) -> None:
    """A missing folder names the path that was expected."""
    with pytest.raises(FileNotFoundError, match="nope"):
        load_logos(tmp_path / "nope")


def test_empty_folder_explains_what_to_do(tmp_path: Path) -> None:
    """An empty folder says which formats are expected."""
    with pytest.raises(ValueError, match=r"\.png"):
        load_logos(tmp_path)


def test_draw_detection_writes_the_logo_name() -> None:
    """A label is written next to a found logo's outline."""
    black = np.zeros((480, 640, 3), dtype=np.uint8)
    result = MatchResult(
        found=True,
        good_matches=20,
        inliers=18,
        frame_shape=(480, 640),
        homography=np.eye(3),
        corners=np.array(
            [[200, 200], [300, 200], [300, 300], [200, 300]], dtype=np.float32
        ),
    )

    without = draw_detection(black, result, show_status=False)
    labelled = draw_detection(black, result, show_status=False, label="bernard")

    assert labelled[170:200, 200:320].any()
    assert not without[170:195, 200:320].any()


def test_draw_keypoints_scales_to_the_original_frame() -> None:
    """Keypoints from a half-size frame are drawn at original positions."""
    pipeline = MultiLogoPipeline(
        {"logo": make_logo()},
        frame_preprocessing=PreprocessingPipeline(
            [to_grayscale, resize_to_max_side(320)]
        ),
    )
    features = pipeline.analyze(make_background()).features
    black = np.zeros((480, 640, 3), dtype=np.uint8)

    canvas = draw_keypoints(black, features)

    x, y = features.keypoints[0].pt
    column, row = round(x * 2), round(y * 2)
    assert canvas[row - 3 : row + 4, column - 3 : column + 4].any()
