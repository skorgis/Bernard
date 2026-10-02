"""Every tunable parameter in one place, plus the slider ranges for the GUI.

`TuningSettings` builds the pipeline the GUI runs, saves/loads itself as
JSON, and prints the equivalent Python code, so tuned values can be
copied straight into an application.
"""

import dataclasses
import json
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from picture_pipeline.image import Image
from picture_pipeline.keypoints import DetectorKind, KeypointDetector
from picture_pipeline.matching import LogoMatcher, MatcherKind
from picture_pipeline.pipeline import MultiLogoPipeline
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    PreprocessingStep,
    canny_edges,
    equalize_contrast,
    gaussian_blur,
    high_pass,
    resize_to_max_side,
    to_grayscale,
)


@dataclass(frozen=True)
class SliderSpec:
    """The range a numeric setting's slider covers."""

    field: str
    from_: float
    to: float
    resolution: float


SLIDERS: tuple[SliderSpec, ...] = (
    SliderSpec("max_features", 50, 5000, 50),
    SliderSpec("ratio", 0.5, 0.99, 0.01),
    SliderSpec("min_good_matches", 4, 100, 1),
    SliderSpec("min_inliers", 4, 100, 1),
    SliderSpec("ransac_threshold", 0.5, 20, 0.5),
    SliderSpec("max_side_ratio", 1.0, 5.0, 0.1),
    SliderSpec("frame_max_side", 0, 1920, 80),
    SliderSpec("frame_blur", 0, 15, 1),
    SliderSpec("clahe_clip_limit", 0.5, 8.0, 0.5),
    SliderSpec("logo_max_side", 0, 1000, 20),
    SliderSpec("max_instances", 1, 10, 1),
    SliderSpec("logo_blur", 0, 15, 1),
    SliderSpec("high_pass", 0, 51, 1),
    SliderSpec("canny_low", 0, 500, 5),
    SliderSpec("canny_high", 0, 500, 5),
)
_SLIDER_BY_FIELD = {slider.field: slider for slider in SLIDERS}

# Kernel-size fields OpenCV needs odd, with the smallest non-zero size.
_ODD_KERNEL_MINIMUM = {"frame_blur": 1, "logo_blur": 1, "high_pass": 3}

# A step factory with its arguments, or a plain step with `None` — the
# one description both `build_pipeline` and `to_python` are made from.
type _StepSpec = tuple[Callable[..., Any], tuple[Any, ...] | None]


@dataclass(frozen=True)
class TuningSettings:
    """The parameters the GUI exposes; see the pipeline modules for each.

    `frame_max_side`/`logo_max_side`, `frame_blur`/`logo_blur` (low-pass)
    and `high_pass` of 0 turn that step off. `clahe`, `high_pass` and
    `canny` (edge filter) apply to logo and frames alike, so both stay
    comparable for the descriptors.
    """

    detector: DetectorKind = DetectorKind.SIFT
    matcher: MatcherKind = MatcherKind.BRUTE_FORCE
    max_features: int = 1000
    ratio: float = 0.75
    min_good_matches: int = 10
    min_inliers: int = 8
    ransac_threshold: float = 5.0
    max_side_ratio: float = 2.0
    max_instances: int = 5
    frame_max_side: int = 0
    frame_blur: int = 0
    clahe: bool = True
    clahe_clip_limit: float = 2.0
    logo_max_side: int = 0
    logo_blur: int = 0
    high_pass: int = 0
    canny: bool = False
    canny_low: float = 50.0
    canny_high: float = 150.0

    def with_value(self, field: str, raw: object) -> "TuningSettings":
        """Return a copy with `field` set from a raw widget value.

        Coerces to the field's type, clamps to the slider range, and makes
        kernel sizes odd as OpenCV requires.
        """
        field_type = _FIELD_TYPES.get(field)
        if field_type is None:
            raise ValueError(f"unknown setting: {field!r}")
        value = _coerce(field_type, raw)
        if field in _SLIDER_BY_FIELD:
            slider = _SLIDER_BY_FIELD[field]
            value = field_type(min(max(value, slider.from_), slider.to))
        if field in _ODD_KERNEL_MINIMUM and value:
            value = max(value | 1, _ODD_KERNEL_MINIMUM[field])
        return dataclasses.replace(self, **{field: value})

    def build_pipeline(self, logos: Mapping[str, Image]) -> MultiLogoPipeline:
        """Build the pipeline these settings describe for `logos`."""
        return MultiLogoPipeline(
            logos,
            logo_preprocessing=_build_steps(self._logo_steps()),
            frame_preprocessing=_build_steps(self._frame_steps()),
            detector=KeypointDetector(self.detector, self.max_features),
            matcher=LogoMatcher(**self._matcher_arguments()),
        )

    def to_python(self) -> str:
        """Code that builds the same pipeline from a `logos` dict."""
        matcher_arguments = ",\n        ".join(
            f"{name}={_literal(value)}"
            for name, value in self._matcher_arguments().items()
        )
        return f"""\
from picture_pipeline.keypoints import DetectorKind, KeypointDetector
from picture_pipeline.matching import LogoMatcher, MatcherKind
from picture_pipeline.pipeline import MultiLogoPipeline
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    canny_edges,
    equalize_contrast,
    gaussian_blur,
    high_pass,
    resize_to_max_side,
    to_grayscale,
)

pipeline = MultiLogoPipeline(
    logos,
    logo_preprocessing=PreprocessingPipeline({_render_steps(self._logo_steps())}),
    frame_preprocessing=PreprocessingPipeline({_render_steps(self._frame_steps())}),
    detector=KeypointDetector(
        {_literal(self.detector)}, max_features={self.max_features}
    ),
    matcher=LogoMatcher(
        {matcher_arguments},
    ),
)
"""

    def frame_step_labels(self) -> list[str]:
        """One label per frame step, e.g. `gaussian_blur(5)`, in order."""
        return [_render_step(spec) for spec in self._frame_steps()]

    def save(self, path: Path | str) -> None:
        """Write the settings as JSON."""
        Path(path).write_text(json.dumps(dataclasses.asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path | str) -> "TuningSettings":
        """Read settings written by `save`."""
        settings = cls()
        for field, raw in json.loads(Path(path).read_text()).items():
            settings = settings.with_value(field, raw)
        return settings

    def _frame_steps(self) -> list[_StepSpec]:
        steps: list[_StepSpec] = [(to_grayscale, None)]
        if self.frame_max_side:
            steps.append((resize_to_max_side, (self.frame_max_side,)))
        if self.frame_blur:
            steps.append((gaussian_blur, (self.frame_blur,)))
        return steps + self._shared_steps()

    def _logo_steps(self) -> list[_StepSpec]:
        steps: list[_StepSpec] = [(to_grayscale, None)]
        if self.logo_max_side:
            steps.append((resize_to_max_side, (self.logo_max_side,)))
        if self.logo_blur:
            steps.append((gaussian_blur, (self.logo_blur,)))
        return steps + self._shared_steps()

    def _shared_steps(self) -> list[_StepSpec]:
        """Steps both sides need, or their descriptors won't compare."""
        steps: list[_StepSpec] = []
        if self.clahe:
            steps.append((equalize_contrast, (self.clahe_clip_limit,)))
        if self.high_pass:
            steps.append((high_pass, (self.high_pass,)))
        if self.canny:
            steps.append((canny_edges, (self.canny_low, self.canny_high)))
        return steps

    def _matcher_arguments(self) -> dict[str, Any]:
        return {
            "ratio": self.ratio,
            "min_good_matches": self.min_good_matches,
            "min_inliers": self.min_inliers,
            "ransac_threshold": self.ransac_threshold,
            "max_side_ratio": self.max_side_ratio,
            "max_instances": self.max_instances,
            "matcher": self.matcher,
        }


_FIELD_TYPES: dict[str, type] = typing.get_type_hints(TuningSettings)


def _coerce(field_type: type, raw: object) -> Any:
    if issubclass(field_type, Enum):
        return field_type(raw)
    if field_type is bool:
        return bool(raw)
    if field_type is int:
        return round(float(typing.cast("float", raw)))
    return field_type(raw)


def _build_steps(specs: list[_StepSpec]) -> PreprocessingPipeline:
    steps: list[PreprocessingStep] = [
        step if args is None else step(*args) for step, args in specs
    ]
    return PreprocessingPipeline(steps)


def _render_steps(specs: list[_StepSpec]) -> str:
    return "[" + ", ".join(_render_step(spec) for spec in specs) + "]"


def _render_step(spec: _StepSpec) -> str:
    step, args = spec
    if args is None:
        return step.__name__
    return f"{step.__name__}({', '.join(_literal(a) for a in args)})"


def _literal(value: object) -> str:
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    return repr(value)
