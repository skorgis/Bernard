"""Frame in, "which logos are there, and where" out."""

from collections.abc import Mapping
from dataclasses import dataclass

from picture_pipeline.image import Image
from picture_pipeline.keypoints import Features, KeypointDetector
from picture_pipeline.matching import LogoMatcher, MatchResult
from picture_pipeline.preprocessing import (
    PreprocessingPipeline,
    default_preprocessing,
)

_SINGLE_LOGO = "logo"


@dataclass(frozen=True)
class FrameAnalysis:
    """Everything one frame produced: the input to matching and its results.

    `preprocessed` is the frame after frame preprocessing and `features`
    its keypoints — both in the coordinates the results refer to.
    `results` has one result per logo: its best copy, or why none was
    found. `instances` has every copy found per logo (possibly none),
    best first — up to the matcher's `max_instances`.
    """

    preprocessed: Image
    features: Features
    results: dict[str, MatchResult]
    instances: dict[str, list[MatchResult]]


class MultiLogoPipeline:
    """Preprocess -> detect keypoints -> match against several static logos.

    Each logo is preprocessed and its keypoints detected once, at
    construction; `preprocessed_logos` keeps the logos as the detector
    saw them, for display. Per frame, preprocessing and keypoint detection
    run once and the result is matched against every logo — the detection is the
    expensive part, so adding logos is cheap. Logos and frames have their
    own preprocessing but share one detector, since descriptors from
    different detectors can't be compared.
    """

    def __init__(
        self,
        logos: Mapping[str, Image],
        logo_preprocessing: PreprocessingPipeline | None = None,
        frame_preprocessing: PreprocessingPipeline | None = None,
        detector: KeypointDetector | None = None,
        matcher: LogoMatcher | None = None,
    ) -> None:
        """Prepare `logos`, a name -> image mapping.

        Defaults: grayscale + CLAHE on both sides, SIFT, ratio 0.75. Both
        preprocessings must still yield comparable images — e.g. both
        grayscale — or the descriptors won't match.
        """
        if not logos:
            raise ValueError("at least one logo is needed")
        self.frame_preprocessing = (
            frame_preprocessing or default_preprocessing()
        )
        self._detector = detector or KeypointDetector()
        self._matcher = matcher or LogoMatcher()
        logo_preprocessing = logo_preprocessing or default_preprocessing()
        self.preprocessed_logos: dict[str, Image] = {
            name: logo_preprocessing(logo) for name, logo in logos.items()
        }
        self.logo_features: dict[str, Features] = {
            name: self._detector.detect(logo)
            for name, logo in self.preprocessed_logos.items()
        }
        empty = [name for name, f in self.logo_features.items() if f.is_empty]
        if empty:
            raise ValueError(
                f"no keypoints found in logo(s) {', '.join(empty)}; "
                "a logo needs texture/corners"
            )

    def analyze(self, frame: Image) -> FrameAnalysis:
        """Look for every logo in `frame`.

        The results' `corners` are in the coordinates of the
        *preprocessed* frame, which equal the original frame's unless a
        frame step resized or cropped it. Resizing a logo doesn't affect
        them.
        """
        preprocessed = self.frame_preprocessing(frame)
        features = self._detector.detect(preprocessed)
        attempts = {
            name: self._matcher.match_all(logo, features)
            for name, logo in self.logo_features.items()
        }
        return FrameAnalysis(
            preprocessed,
            features,
            results={name: found[0] for name, found in attempts.items()},
            instances={
                name: [result for result in found if result.found]
                for name, found in attempts.items()
            },
        )


class LogoDetectionPipeline:
    """`MultiLogoPipeline` for the common case of exactly one logo."""

    def __init__(
        self,
        logo: Image,
        logo_preprocessing: PreprocessingPipeline | None = None,
        frame_preprocessing: PreprocessingPipeline | None = None,
        detector: KeypointDetector | None = None,
        matcher: LogoMatcher | None = None,
    ) -> None:
        """Prepare the logo; see `MultiLogoPipeline` for the arguments."""
        self._pipeline = MultiLogoPipeline(
            {_SINGLE_LOGO: logo},
            logo_preprocessing,
            frame_preprocessing,
            detector,
            matcher,
        )
        self.logo_features: Features = self._pipeline.logo_features[
            _SINGLE_LOGO
        ]

    def process(self, frame: Image) -> MatchResult:
        """Look for the logo in `frame`; see `MultiLogoPipeline.analyze`."""
        return self._pipeline.analyze(frame).results[_SINGLE_LOGO]
