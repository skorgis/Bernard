"""A Tkinter window to tune the logo pipeline live.

Dropdowns pick the frame source, the keypoint extractor and the matcher;
sliders set every numeric parameter; the frame updates as you drag. The
pipeline is rebuilt whenever a setting changes, which is cheap: only the
logos are re-processed.
"""

import time
import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from tkinter import ttk

import cv2
import numpy as np

from picture_pipeline.frame_sources import FrameSource
from picture_pipeline.image import Image
from picture_pipeline.keypoints import DetectorKind
from picture_pipeline.matching import MatcherKind
from picture_pipeline.pipeline import FrameAnalysis, MultiLogoPipeline
from picture_pipeline.tuning import SLIDERS, TuningSettings
from picture_pipeline.visualization import (
    LOGO_COLORS,
    draw_detection,
    draw_keypoints,
    draw_logo_insets,
    draw_stage_strip,
)

_DISPLAY_MAX_WIDTH = 960
_STAGE_TILE_WIDTH = 160
_TICK_MS = 15
_DETECTOR_LABELS = {kind: kind.name for kind in DetectorKind}
_MATCHER_LABELS = {
    MatcherKind.BRUTE_FORCE: "Brute-Force",
    MatcherKind.FLANN: "FLANN",
}


def render(
    frame: Image,
    analysis: FrameAnalysis,
    show_preprocessed: bool,
    show_keypoints: bool,
    bounding_box: bool,
    logos: Mapping[str, Image] | None = None,
) -> Image:
    """Draw keypoints and the outline of every copy found, per logo color.

    With `logos`, each also appears as a thumbnail framed in that color.
    """
    canvas = analysis.preprocessed if show_preprocessed else frame
    if show_keypoints:
        canvas = draw_keypoints(canvas, analysis.features)
    colors = {
        name: LOGO_COLORS[number % len(LOGO_COLORS)]
        for number, name in enumerate(analysis.results)
    }
    for name, copies in analysis.instances.items():
        for copy in copies:
            canvas = draw_detection(
                canvas,
                copy,
                color=colors[name],
                bounding_box=bounding_box,
                show_status=False,
                label=name,
            )
    if logos:
        canvas = draw_logo_insets(
            canvas, [(logo, colors[name]) for name, logo in logos.items()]
        )
    return canvas


def stage_strip(
    frame: Image, pipeline: MultiLogoPipeline, labels: Sequence[str]
) -> Image:
    """Small thumbnails of the frame and of each frame step's output.

    `labels` name the steps of `pipeline`'s frame preprocessing, in order.
    All thumbnails fit one row of the display; many steps make them
    narrower.
    """
    stages = [
        ("Eingabe", frame),
        *zip(labels, pipeline.frame_preprocessing.stages(frame), strict=True),
    ]
    return draw_stage_strip(
        stages,
        tile_width=min(_STAGE_TILE_WIDTH, _DISPLAY_MAX_WIDTH // len(stages)),
        columns=len(stages),
    )


def status_text(analysis: FrameAnalysis, seconds: float) -> str:
    """Timing, keypoint count and one line per logo."""
    lines = [
        f"{1 / seconds:.1f} FPS ({seconds * 1000:.0f} ms), "
        f"{len(analysis.features.keypoints)} Keypoints im Frame"
    ]
    return "\n".join(lines + logo_status_lines(analysis))


def logo_status_lines(analysis: FrameAnalysis) -> list[str]:
    """Per logo: how many copies, with match counts. ASCII, for `putText`.

    Without a copy, the inliers are those of the failed attempt.
    """
    lines = []
    for name, result in analysis.results.items():
        copies = analysis.instances[name]
        if len(copies) > 1:
            state = f"{len(copies)}x gefunden"
        else:
            state = "gefunden" if copies else "nicht gefunden"
        inliers = "/".join(str(c.inliers) for c in copies) or result.inliers
        lines.append(
            f"{name}: {state} ({result.good_matches} Matches, {inliers} Inlier)"
        )
    return lines


class LogoTunerApp:
    """The tuner window: image on the left, controls on the right."""

    def __init__(
        self,
        root: tk.Tk,
        logos: Mapping[str, Image],
        sources: Mapping[str, Callable[[], FrameSource]],
        settings: TuningSettings,
        settings_path: Path,
    ) -> None:
        """Build the window and start showing the first source."""
        if not sources:
            raise ValueError("no frame source: no camera found, no file given")
        self._root = root
        self._logos = logos
        self._sources = sources
        self._settings = settings
        self._settings_path = settings_path
        self._source: FrameSource | None = None
        self._pipeline: MultiLogoPipeline | None = None
        self._pipeline_settings: TuningSettings | None = None
        self._dirty = True
        self._stage_labels: list[str] = []
        self._photos: dict[ttk.Label, tk.PhotoImage] = {}
        self._show_keypoints = tk.BooleanVar(value=False)
        self._show_preprocessed = tk.BooleanVar(value=False)
        self._bounding_box = tk.BooleanVar(value=False)
        self._show_stages = tk.BooleanVar(value=False)

        self._build_widgets()
        self._select_source(next(iter(sources)))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(_TICK_MS, self._tick)

    def close(self) -> None:
        """Release the source and close the window."""
        if self._source is not None:
            self._source.release()
        self._root.destroy()

    def _build_widgets(self) -> None:
        self._image_label = ttk.Label(self._root)
        self._image_label.grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        self._stages_label = ttk.Label(self._root)
        controls = ttk.Frame(self._root, padding=8)
        controls.grid(row=0, column=1, sticky="n")
        sliders = ttk.Frame(self._root, padding=8)
        sliders.grid(row=0, column=2, sticky="n")

        self._add_combobox(
            controls, "Quelle", list(self._sources), self._select_source
        )
        self._detector_box = self._add_combobox(
            controls,
            "Keypoint-Extraktor",
            list(_DETECTOR_LABELS.values()),
            lambda label: self._set(
                "detector", _key_for(_DETECTOR_LABELS, label)
            ),
        )
        self._matcher_box = self._add_combobox(
            controls,
            "Matcher",
            list(_MATCHER_LABELS.values()),
            lambda label: self._set(
                "matcher", _key_for(_MATCHER_LABELS, label)
            ),
        )

        self._clahe = tk.BooleanVar()
        ttk.Checkbutton(
            controls,
            text="Kontrastausgleich (CLAHE)",
            variable=self._clahe,
            command=lambda: self._set("clahe", self._clahe.get()),
        ).pack(anchor="w", pady=(8, 0))
        self._canny = tk.BooleanVar()
        ttk.Checkbutton(
            controls,
            text="Kantenfilter (Canny)",
            variable=self._canny,
            command=lambda: self._set("canny", self._canny.get()),
        ).pack(anchor="w")
        for text, variable in (
            ("Keypoints anzeigen", self._show_keypoints),
            ("Vorverarbeitetes Bild zeigen", self._show_preprocessed),
            ("Bounding Box statt Umriss", self._bounding_box),
            ("Vorverarbeitungsschritte zeigen", self._show_stages),
        ):
            ttk.Checkbutton(
                controls, text=text, variable=variable, command=self._mark_dirty
            ).pack(anchor="w")

        ttk.Button(
            controls, text="Einstellungen speichern", command=self._save
        ).pack(fill="x", pady=(12, 0))
        ttk.Button(
            controls, text="Standardwerte", command=self._reset_to_defaults
        ).pack(fill="x", pady=(4, 0))
        self._status = ttk.Label(controls, justify="left", wraplength=300)
        self._status.pack(anchor="w", pady=(12, 0))
        self._message = ttk.Label(
            controls, justify="left", wraplength=300, foreground="#b00"
        )
        self._message.pack(anchor="w", pady=(8, 0))

        self._scales: dict[str, tk.Scale] = {}
        for spec in SLIDERS:
            scale = tk.Scale(
                sliders,
                label=spec.field,
                from_=spec.from_,
                to=spec.to,
                resolution=spec.resolution,
                orient="horizontal",
                length=260,
            )
            scale.configure(
                command=lambda value, field=spec.field: self._set(field, value)
            )
            scale.pack(anchor="w")
            self._scales[spec.field] = scale
        self._show_settings()

    def _add_combobox(
        self,
        parent: ttk.Frame,
        title: str,
        values: list[str],
        on_select: Callable[[str], None],
    ) -> ttk.Combobox:
        ttk.Label(parent, text=title).pack(anchor="w")
        box = ttk.Combobox(parent, values=values, state="readonly", width=34)
        box.set(values[0])
        box.bind("<<ComboboxSelected>>", lambda _event: on_select(box.get()))
        box.pack(anchor="w", pady=(0, 6))
        return box

    def _show_settings(self) -> None:
        """Make every settings widget display `self._settings`."""
        self._detector_box.set(_DETECTOR_LABELS[self._settings.detector])
        self._matcher_box.set(_MATCHER_LABELS[self._settings.matcher])
        self._clahe.set(self._settings.clahe)
        self._canny.set(self._settings.canny)
        for field, scale in self._scales.items():
            scale.set(getattr(self._settings, field))

    def _reset_to_defaults(self) -> None:
        self._settings = TuningSettings()
        self._show_settings()
        self._mark_dirty()

    def _set(self, field: str, raw: object) -> None:
        self._settings = self._settings.with_value(field, raw)
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _select_source(self, label: str) -> None:
        if self._source is not None:
            self._source.release()
            self._source = None
        try:
            self._source = self._sources[label]()
            self._message.configure(text="")
        except ValueError as error:
            self._message.configure(text=str(error))
        self._mark_dirty()

    def _tick(self) -> None:
        try:
            self._update_frame()
        finally:
            self._root.after(_TICK_MS, self._tick)

    def _update_frame(self) -> None:
        if self._source is None:
            return
        if self._source.is_still and not self._dirty:
            return
        frame = self._source.read()
        if frame is None:
            return
        self._dirty = False
        pipeline = self._current_pipeline()
        if pipeline is None:
            return
        start = time.perf_counter()
        analysis = pipeline.analyze(frame)
        elapsed = time.perf_counter() - start
        show_preprocessed = self._show_preprocessed.get()
        self._show(
            self._image_label,
            render(
                frame,
                analysis,
                show_preprocessed,
                self._show_keypoints.get(),
                self._bounding_box.get(),
                pipeline.preprocessed_logos
                if show_preprocessed
                else self._logos,
            ),
        )
        self._show_stage_strip(frame, pipeline)
        self._status.configure(text=status_text(analysis, elapsed))

    def _show_stage_strip(
        self, frame: Image, pipeline: MultiLogoPipeline
    ) -> None:
        if not self._show_stages.get():
            self._stages_label.grid_remove()
            return
        self._stages_label.grid(row=1, column=0, sticky="nw", padx=8)
        self._show(
            self._stages_label,
            stage_strip(frame, pipeline, self._stage_labels),
        )

    def _current_pipeline(self) -> MultiLogoPipeline | None:
        if self._pipeline_settings != self._settings:
            self._pipeline_settings = self._settings
            try:
                self._pipeline = self._settings.build_pipeline(self._logos)
                self._stage_labels = self._settings.frame_step_labels()
                self._message.configure(text="")
            except ValueError as error:
                self._message.configure(text=f"Einstellung ungültig: {error}")
        return self._pipeline

    def _show(self, label: ttk.Label, image: Image) -> None:
        height, width = image.shape[:2]
        if width > _DISPLAY_MAX_WIDTH:
            size = (
                _DISPLAY_MAX_WIDTH,
                round(height * _DISPLAY_MAX_WIDTH / width),
            )
            image = np.asarray(
                cv2.resize(image, size, interpolation=cv2.INTER_AREA),
                dtype=np.uint8,
            )
        ok, encoded = cv2.imencode(".ppm", image)
        if not ok:
            return
        # Tk shows the image only while Python keeps a reference to it.
        self._photos[label] = tk.PhotoImage(data=encoded.tobytes())
        label.configure(image=self._photos[label])

    def _save(self) -> None:
        self._settings.save(self._settings_path)
        code = self._settings.to_python()
        print(code)
        self._root.clipboard_clear()
        self._root.clipboard_append(code)
        self._message.configure(
            text=(
                f"Gespeichert in {self._settings_path}. "
                "Python-Code steht im Terminal und in der Zwischenablage."
            ),
            foreground="#070",
        )


def run_tuner(
    logos: Mapping[str, Image],
    sources: Mapping[str, Callable[[], FrameSource]],
    settings_path: Path | str,
) -> None:
    """Open the tuner window; settings load from/save to `settings_path`."""
    settings_path = Path(settings_path)
    settings = (
        TuningSettings.load(settings_path)
        if settings_path.exists()
        else TuningSettings()
    )
    root = tk.Tk()
    root.title("Logo-Tuner")
    LogoTunerApp(root, logos, sources, settings, settings_path)
    root.mainloop()


def _key_for[K](labels: Mapping[K, str], label: str) -> K:
    return next(key for key, text in labels.items() if text == label)
