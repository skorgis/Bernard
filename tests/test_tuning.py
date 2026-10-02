"""Tests for `TuningSettings`, the logic behind the slider GUI."""

import json
from pathlib import Path

import numpy as np
import pytest

from picture_pipeline.keypoints import DetectorKind
from picture_pipeline.matching import MatcherKind
from picture_pipeline.pipeline import MultiLogoPipeline
from picture_pipeline.tuning import SLIDERS, TuningSettings
from tests.picture_fixtures import make_background, make_logo, place_logo


@pytest.mark.parametrize("slider", SLIDERS, ids=lambda s: s.field)
def test_default_value_lies_within_slider_range(slider) -> None:
    """Every slider can show its default setting."""
    value = getattr(TuningSettings(), slider.field)
    assert slider.from_ <= value <= slider.to


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        ("ratio", 0.8, 0.8),
        ("max_features", 1234.6, 1235),
        ("min_inliers", 7.4, 7),
        ("frame_blur", 4, 5),
        ("frame_blur", 0, 0),
        ("logo_blur", 2, 3),
        ("high_pass", 6, 7),
        ("high_pass", 0, 0),
        ("canny", 1, True),
        ("max_instances", 3.4, 3),
        ("frame_max_side", 479.7, 480),
        ("detector", "orb", DetectorKind.ORB),
        ("matcher", "flann", MatcherKind.FLANN),
        ("clahe", 0, False),
    ],
)
def test_with_value_coerces_gui_input(
    field: str, raw: object, expected: object
) -> None:
    """Raw widget values become valid, correctly typed settings."""
    settings = TuningSettings().with_value(field, raw)
    assert getattr(settings, field) == expected


def test_with_value_rejects_unknown_field() -> None:
    """A typo in a field name fails loudly."""
    with pytest.raises(ValueError, match="unknown"):
        TuningSettings().with_value("rattio", 0.8)


def test_built_pipeline_finds_every_logo() -> None:
    """The settings build a pipeline that finds the logo by name."""
    logo = make_logo()
    frame, _ = place_logo(make_background(), logo, (320, 240), angle=20)

    pipeline = TuningSettings().build_pipeline({"bernard": logo})

    assert pipeline.analyze(frame).results["bernard"].found


@pytest.mark.parametrize("matcher", list(MatcherKind))
@pytest.mark.parametrize("detector", list(DetectorKind))
def test_every_detector_matcher_combination_works(
    detector: DetectorKind, matcher: MatcherKind
) -> None:
    """All dropdown combinations build and find an unrotated logo."""
    logo = make_logo()
    frame, _ = place_logo(make_background(), logo, (320, 240))
    settings = TuningSettings(detector=detector, matcher=matcher)

    result = settings.build_pipeline({"logo": logo}).analyze(frame)

    assert result.results["logo"].found


def test_frame_max_side_resizes_the_frame() -> None:
    """A frame size limit shows up in the analysis."""
    pipeline = TuningSettings(frame_max_side=320).build_pipeline(
        {"logo": make_logo()}
    )

    analysis = pipeline.analyze(make_background())

    assert analysis.preprocessed.shape == (240, 320)
    assert analysis.results["logo"].frame_shape == (240, 320)


def test_canny_turns_the_frame_into_an_edge_map() -> None:
    """With edges on, the extractor sees a binary image."""
    pipeline = TuningSettings(canny=True).build_pipeline({"logo": make_logo()})

    analysis = pipeline.analyze(make_background())

    assert set(np.unique(analysis.preprocessed)) <= {0, 255}


def test_frame_step_labels_name_each_step_with_its_arguments() -> None:
    """The labels describe the frame steps exactly as they run."""
    settings = TuningSettings(frame_blur=5, clahe=False, canny=True)

    assert settings.frame_step_labels() == [
        "to_grayscale",
        "gaussian_blur(5)",
        "canny_edges(50.0, 150.0)",
    ]


def test_frame_step_labels_match_the_built_stages() -> None:
    """One label per stage the built pipeline produces."""
    settings = TuningSettings(frame_max_side=320, high_pass=9)
    pipeline = settings.build_pipeline({"logo": make_logo()})

    stages = pipeline.frame_preprocessing.stages(make_background())

    assert len(stages) == len(settings.frame_step_labels())


def test_python_snippet_builds_an_equivalent_pipeline() -> None:
    """The printed code is valid and reproduces the tuned settings."""
    settings = TuningSettings(
        detector=DetectorKind.ORB,
        matcher=MatcherKind.FLANN,
        ratio=0.8,
        frame_max_side=320,
        frame_blur=3,
        logo_blur=3,
        high_pass=9,
        canny=True,
        max_instances=3,
        clahe=False,
        logo_max_side=120,
    )
    namespace: dict[str, object] = {"logos": {"logo": make_logo()}}

    exec(settings.to_python(), namespace)

    pipeline = namespace["pipeline"]
    assert isinstance(pipeline, MultiLogoPipeline)
    assert "max_instances=3" in settings.to_python()
    assert pipeline.logo_features["logo"].image_shape == (120, 120)
    assert pipeline.analyze(make_background()).preprocessed.shape == (240, 320)


def test_json_round_trip(tmp_path: Path) -> None:
    """Saved settings load back unchanged."""
    settings = TuningSettings(
        detector=DetectorKind.ORB, matcher=MatcherKind.FLANN, clahe=False
    )
    path = tmp_path / "settings.json"

    settings.save(path)

    assert json.loads(path.read_text())["detector"] == "orb"
    assert TuningSettings.load(path) == settings
