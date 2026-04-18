from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import Measure, MidiProject, RenderSettings

try:
    import aggdraw
except ImportError:  # pragma: no cover - optional dependency
    aggdraw = None


# Keep export HUD sizing proportional to the desktop preview canvas.
PREVIEW_REFERENCE_MAX_WIDTH = 960.0
PREVIEW_REFERENCE_MAX_HEIGHT = 540.0
MIN_OVERLAY_SCALE = 0.85
MAX_OVERLAY_SCALE = 8.0


_DEFAULT_FONT_FAMILY = "modern_light"
_FONT_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "modern_light": {
        "light": (
            "C:/Windows/Fonts/YuGothL.ttc",
            "C:/Windows/Fonts/YuGothR.ttc",
            "C:/Windows/Fonts/BIZ-UDGothicR.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W2.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "DejaVuSans.ttf",
        ),
        "regular": (
            "C:/Windows/Fonts/YuGothL.ttc",
            "C:/Windows/Fonts/YuGothR.ttc",
            "C:/Windows/Fonts/BIZ-UDGothicR.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "DejaVuSans.ttf",
        ),
        "bold": (
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "DejaVuSans-Bold.ttf",
        ),
    },
    "yu_gothic": {
        "light": ("C:/Windows/Fonts/YuGothL.ttc", "C:/Windows/Fonts/YuGothR.ttc"),
        "regular": ("C:/Windows/Fonts/YuGothR.ttc", "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/YuGothL.ttc"),
        "bold": ("C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/YuGothM.ttc"),
    },
    "biz_ud_gothic": {
        "light": ("C:/Windows/Fonts/BIZ-UDGothicR.ttc",),
        "regular": ("C:/Windows/Fonts/BIZ-UDGothicR.ttc",),
        "bold": ("C:/Windows/Fonts/BIZ-UDGothicB.ttc", "C:/Windows/Fonts/BIZ-UDGothicR.ttc"),
    },
    "meiryo": {
        "light": ("C:/Windows/Fonts/meiryo.ttc",),
        "regular": ("C:/Windows/Fonts/meiryo.ttc",),
        "bold": ("C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/meiryo.ttc"),
    },
    "noto_sans_jp": {
        "light": (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "NotoSansCJK-Regular.ttc",
        ),
        "regular": (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "NotoSansCJK-Regular.ttc",
        ),
        "bold": (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "NotoSansCJK-Bold.ttc",
        ),
    },
    "hiragino": {
        "light": (
            "/System/Library/Fonts/ヒラギノ角ゴシック W2.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
        ),
        "regular": (
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
        ),
        "bold": (
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
        ),
    },
    "deja_vu": {
        "light": ("DejaVuSans.ttf",),
        "regular": ("DejaVuSans.ttf",),
        "bold": ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
    },
}


@lru_cache(maxsize=256)
def _load_font(
    size: int,
    weight: str = "regular",
    font_family: str = _DEFAULT_FONT_FAMILY,
    custom_font_path: str = "",
) -> ImageFont.ImageFont:
    clamped_size = max(10, int(size))
    for font_path in _font_candidate_paths(font_family, weight, custom_font_path):
        try:
            return ImageFont.truetype(font_path, clamped_size)
        except OSError:
            continue
    return ImageFont.load_default()


def _font_candidate_paths(font_family: str, weight: str, custom_font_path: str) -> tuple[str, ...]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_many(paths: tuple[str, ...]) -> None:
        for raw_path in paths:
            path = raw_path.strip()
            if path and path not in seen:
                candidates.append(path)
                seen.add(path)

    if custom_font_path.strip():
        try:
            add_many((str(Path(custom_font_path.strip()).expanduser()),))
        except OSError:
            add_many((custom_font_path.strip(),))

    family = _FONT_CANDIDATES.get(font_family, _FONT_CANDIDATES[_DEFAULT_FONT_FAMILY])
    add_many(family.get(weight, family.get("regular", ())))
    if weight != "regular":
        add_many(family.get("regular", ()))

    if font_family != _DEFAULT_FONT_FAMILY:
        fallback_family = _FONT_CANDIDATES[_DEFAULT_FONT_FAMILY]
        add_many(fallback_family.get(weight, fallback_family["regular"]))
        if weight != "regular":
            add_many(fallback_family["regular"])

    add_many(("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"))
    return tuple(candidates)


@dataclass(slots=True)
class _VisibleSegment:
    note: int
    segment_start_beat: float
    segment_end_beat: float
    start_ratio: float
    end_ratio: float
    note_start_beat: float
    note_end_beat: float
    note_start_sec: float
    note_end_sec: float


@dataclass(slots=True)
class _AnimationState:
    phase: float
    wave: float
    flicker: float
    lift: float
    stepped: float
    jitter: float
    burst: float
    saw: float
    attack_ratio: float = 1.0


@dataclass(slots=True)
class _ActiveRenderItem:
    base_rect: tuple[float, float, float, float]
    frame_rect: tuple[float, float, float, float]
    state: _AnimationState


@dataclass(slots=True)
class _TrailRenderItem:
    base_rect: tuple[float, float, float, float]
    frame_rect: tuple[float, float, float, float]
    age_ratio: float
    is_active: bool
    state: _AnimationState | None = None


@dataclass(slots=True)
class _ReleaseRenderItem:
    base_rect: tuple[float, float, float, float]
    frame_rect: tuple[float, float, float, float]
    age_ratio: float
    state: _AnimationState


@dataclass(slots=True)
class _PreparedSegment:
    segment: _VisibleSegment
    rect: tuple[float, float, float, float]


@dataclass(slots=True)
class _SafeAreaInsets:
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0


class _LayerContext:
    def __init__(self, image: Image.Image) -> None:
        self.image = image
        self.draw = ImageDraw.Draw(image, "RGBA")
        self._agg = aggdraw.Draw(image) if aggdraw is not None else None
        if self._agg is not None:
            self._agg.setantialias(True)

    def flush(self) -> None:
        if self._agg is not None:
            self._agg.flush()

    def rounded_rectangle(
        self,
        rect: tuple[float, float, float, float],
        radius: float,
        fill: tuple[int, int, int, int] | None = None,
        outline: tuple[int, int, int, int] | None = None,
        width: int = 1,
    ) -> None:
        normalized = _normalize_rect(rect)
        if self._agg is None:
            self.draw.rounded_rectangle(normalized, radius=radius, fill=fill, outline=outline, width=width)
            return

        pen = None if outline is None or width <= 0 else aggdraw.Pen(outline, width)
        brush = None if fill is None else aggdraw.Brush(fill)
        self._agg.rounded_rectangle(normalized, max(0.0, float(radius)), pen, brush)

    def rectangle(
        self,
        rect: tuple[float, float, float, float],
        fill: tuple[int, int, int, int] | None = None,
        outline: tuple[int, int, int, int] | None = None,
        width: int = 1,
    ) -> None:
        self.draw.rectangle(_normalize_rect(rect), fill=fill, outline=outline, width=width)

    def line(
        self,
        points: tuple[float, float, float, float],
        fill: tuple[int, int, int, int],
        width: int = 1,
    ) -> None:
        self.draw.line(points, fill=fill, width=width)

    def polygon(
        self,
        points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
        fill: tuple[int, int, int, int],
    ) -> None:
        self.draw.polygon(points, fill=fill)


class ProjectRenderer:
    def __init__(self, project: MidiProject, settings: RenderSettings | None = None) -> None:
        self.project = project
        self.settings = settings or RenderSettings()
        self._measure_start_seconds = [measure.start_sec for measure in project.measures]
        self._measure_start_beats = [measure.start_beat for measure in project.measures]
        self._measure_segments = self._build_measure_segments(project)
        self._note_start_seconds = [note.start_sec for note in project.notes]
        self._chord_start_seconds = [chord.start_sec for chord in project.chords]
        self._measure_render_cache: dict[
            tuple[int, int, int, tuple[object, ...]],
            tuple[Image.Image, tuple[_PreparedSegment, ...]],
        ] = {}

    def set_settings(self, settings: RenderSettings) -> None:
        self.settings = settings
        self._measure_render_cache.clear()

    def _font(self, size: int, weight: str = "regular") -> ImageFont.ImageFont:
        return _load_font(
            size,
            weight,
            getattr(self.settings, "font_family", _DEFAULT_FONT_FAMILY),
            getattr(self.settings, "custom_font_path", ""),
        )

    def get_measure_for_time(self, time_sec: float) -> Measure:
        if time_sec <= 0:
            return self.project.measures[0]
        index = bisect_right(self._measure_start_seconds, time_sec) - 1
        if index < 0:
            index = 0
        if index >= len(self.project.measures):
            index = len(self.project.measures) - 1
        return self.project.measures[index]

    def render_frame(self, time_sec: float, width: int, height: int) -> Image.Image:
        clamped_time = max(0.0, min(time_sec, max(self.project.duration_sec - 1e-6, 0.0)))
        if self.settings.view_mode == "performance":
            return self._render_performance_frame(clamped_time, width, height)
        return self._render_measure_page_frame(clamped_time, width, height)

    def _render_measure_page_frame(self, clamped_time: float, width: int, height: int) -> Image.Image:
        settings = self.settings
        measure = self.get_measure_for_time(clamped_time)
        image, prepared_segments = self._get_prepared_measure(measure, width, height)
        image = image.copy()
        draw = _LayerContext(image)
        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = _LayerContext(glow_layer)
        crisp_glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        crisp_glow_draw = _LayerContext(crisp_glow_layer)

        active_items: list[_ActiveRenderItem] = []
        trail_items: list[_TrailRenderItem] = []
        release_items: list[_ReleaseRenderItem] = []
        trail_window_sec = self._afterimage_window_sec()
        afterimage_enabled = (
            self._resolved_afterimage_style() != "none"
            and trail_window_sec > 0.0
            and self.settings.afterimage_strength > 0.0
        )
        release_window_sec = self._release_fade_window_sec()
        release_enabled = self.settings.release_fade_style != "none" and release_window_sec > 0.0

        for prepared in prepared_segments:
            segment = prepared.segment
            rect = prepared.rect
            if segment.note_start_sec <= clamped_time < segment.note_end_sec:
                state = self._build_animation_state(segment, clamped_time)
                animated_rect = self._animated_rect(rect, state)
                active_items.append(_ActiveRenderItem(base_rect=rect, frame_rect=animated_rect, state=state))
                if afterimage_enabled:
                    trail_items.append(
                        _TrailRenderItem(
                            base_rect=rect,
                            frame_rect=animated_rect,
                            age_ratio=0.0,
                            is_active=True,
                            state=state,
                        )
                    )
                self._draw_glow(glow_draw, crisp_glow_draw, animated_rect, self._rect_radius(animated_rect), state)
            else:
                note_age_sec = clamped_time - segment.note_end_sec
                if release_enabled and 0.0 <= note_age_sec <= release_window_sec:
                    release_state = self._build_animation_state(
                        segment,
                        max(segment.note_start_sec, segment.note_end_sec - 1e-4),
                    )
                    release_items.append(
                        _ReleaseRenderItem(
                            base_rect=rect,
                            frame_rect=self._animated_rect(rect, release_state),
                            age_ratio=_clamp(note_age_sec / max(release_window_sec, 1e-6)),
                            state=release_state,
                        )
                    )
                if afterimage_enabled:
                    if 0.0 <= note_age_sec <= trail_window_sec:
                        trail_items.append(
                            _TrailRenderItem(
                                base_rect=rect,
                                frame_rect=rect,
                                age_ratio=_clamp(note_age_sec / max(trail_window_sec, 1e-6)),
                                is_active=False,
                            )
                        )

        glow_draw.flush()
        crisp_glow_draw.flush()
        glow_layer = self._finalize_glow_layer(glow_layer, width, height)
        image.alpha_composite(glow_layer)
        image.alpha_composite(crisp_glow_layer)

        for item in sorted((trail for trail in trail_items if not trail.is_active), key=lambda trail: trail.age_ratio, reverse=True):
            self._draw_afterimage(draw, item)
        for item in trail_items:
            if item.is_active:
                self._draw_afterimage(draw, item)
        for item in sorted(release_items, key=lambda release: release.age_ratio, reverse=True):
            self._draw_release_fade(draw, item)

        for item in active_items:
            self._draw_active_segment(draw, item.base_rect, item.frame_rect, item.state)

        draw.flush()
        return self._finalize_frame(image, width, height)

    def _render_performance_frame(self, clamped_time: float, width: int, height: int) -> Image.Image:
        overlay_layout = self._overlay_layout_mode(width, height)
        if overlay_layout == "portrait" and self._safe_area_should_scale(width, height, overlay_layout):
            return self._render_safe_scaled_performance_frame(clamped_time, width, height, overlay_layout)

        image = Image.new("RGBA", (width, height), self._background_fill())
        draw = _LayerContext(image)
        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = _LayerContext(glow_layer)
        crisp_glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        crisp_glow_draw = _LayerContext(crisp_glow_layer)

        start_measure_index, visible_measure_count = self._performance_window(clamped_time)
        visible_measures = self.project.measures[start_measure_index : start_measure_index + visible_measure_count]
        current_measure = self.get_measure_for_time(clamped_time)
        overlay_scale = self._overlay_scale(width, height)
        safe_insets = self._safe_area_insets(width, height, overlay_layout)

        horizontal_padding = width * max(0.025, self.settings.horizontal_padding_ratio * 0.55)
        vertical_padding = height * max(0.04, self.settings.vertical_padding_ratio * 0.5)
        top_overlay_height, bottom_overlay_height = self._performance_overlay_heights(overlay_layout, overlay_scale)
        lyric_gap_height = self._lyrics_reserve_height(overlay_layout, overlay_scale)
        left_padding = max(horizontal_padding, safe_insets.left)
        right_padding = max(horizontal_padding, safe_insets.right)
        top_padding = max(vertical_padding, safe_insets.top) + top_overlay_height
        bottom_padding = max(vertical_padding, safe_insets.bottom) + bottom_overlay_height + lyric_gap_height
        plot_width = max(1.0, width - left_padding - right_padding)
        plot_height = max(1.0, height - top_padding - bottom_padding)
        measure_width = plot_width / max(1, visible_measure_count)

        visible_notes = self._performance_note_range(start_measure_index, visible_measure_count, clamped_time)
        min_note, max_note = visible_notes
        note_range = max(1, max_note - min_note + 1)
        lane_height = plot_height / note_range
        rectangle_height = max(2.0, lane_height * 0.56)
        min_rectangle_width = max(2.0, width * 0.0012)

        if self.settings.show_measure_overlay:
            self._draw_performance_grid(
                draw,
                visible_measures,
                left_padding,
                top_padding,
                measure_width,
                plot_height,
                current_measure,
                overlay_layout,
                overlay_scale,
            )

        active_items: list[_ActiveRenderItem] = []
        release_items: list[_ReleaseRenderItem] = []
        trail_items: list[_TrailRenderItem] = []
        burst_items: list[tuple[float, float, float]] = []
        trail_window_sec = self._afterimage_window_sec()
        afterimage_enabled = (
            self._resolved_afterimage_style() != "none"
            and trail_window_sec > 0.0
            and self.settings.afterimage_strength > 0.0
        )
        release_window_sec = self._release_fade_window_sec()
        release_enabled = self.settings.release_fade_style != "none" and release_window_sec > 0.0

        for slot_index, measure in enumerate(visible_measures):
            measure_x0 = left_padding + slot_index * measure_width
            measure_x1 = measure_x0 + measure_width
            for segment in self._measure_segments[measure.index]:
                clipped_end_beat = self._segment_visible_end_beat(segment, clamped_time)
                if clipped_end_beat <= segment.segment_start_beat + 1e-9:
                    continue

                x0 = measure_x0 + measure_width * (
                    (segment.segment_start_beat - measure.start_beat) / max(measure.length_beats, 1e-9)
                )
                x1 = measure_x0 + measure_width * (
                    (clipped_end_beat - measure.start_beat) / max(measure.length_beats, 1e-9)
                )
                if x1 - x0 < min_rectangle_width:
                    x1 = x0 + min_rectangle_width
                if x0 >= measure_x1 + 1e-6 or x1 <= measure_x0 - 1e-6:
                    continue

                pitch_index = max_note - segment.note
                lane_top = top_padding + pitch_index * lane_height
                y0 = lane_top + (lane_height - rectangle_height) / 2.0
                y1 = y0 + rectangle_height
                rect = self._scaled_note_rect((x0, y0, x1, y1), min_rectangle_width)

                is_active = segment.note_start_sec <= clamped_time < segment.note_end_sec
                if is_active:
                    state = self._build_animation_state(segment, clamped_time)
                    animated_rect = self._animated_rect(rect, state)
                    active_items.append(_ActiveRenderItem(base_rect=rect, frame_rect=animated_rect, state=state))
                    if afterimage_enabled:
                        trail_items.append(
                            _TrailRenderItem(
                                base_rect=rect,
                                frame_rect=animated_rect,
                                age_ratio=0.0,
                                is_active=True,
                                state=state,
                            )
                        )
                    self._draw_glow(glow_draw, crisp_glow_draw, animated_rect, self._rect_radius(animated_rect), state)

                    attack_window = max(0.04, self.settings.attack_fade_duration_sec)
                    attack_age = clamped_time - segment.note_start_sec
                    if 0.0 <= attack_age <= attack_window:
                        burst_items.append(
                            (
                                rect[0],
                                (rect[1] + rect[3]) / 2.0,
                                1.0 - attack_age / attack_window,
                            )
                        )
                else:
                    self._draw_performance_idle_segment(draw, rect, is_finished=segment.note_end_sec <= clamped_time)
                    note_age_sec = clamped_time - segment.note_end_sec
                    if release_enabled and 0.0 <= note_age_sec <= release_window_sec:
                        release_state = self._build_animation_state(
                            segment,
                            max(segment.note_start_sec, segment.note_end_sec - 1e-4),
                        )
                        release_items.append(
                            _ReleaseRenderItem(
                                base_rect=rect,
                                frame_rect=self._animated_rect(rect, release_state),
                                age_ratio=_clamp(note_age_sec / max(release_window_sec, 1e-6)),
                                state=release_state,
                            )
                        )
                    if afterimage_enabled and 0.0 <= note_age_sec <= trail_window_sec:
                        trail_items.append(
                            _TrailRenderItem(
                                base_rect=rect,
                                frame_rect=rect,
                                age_ratio=_clamp(note_age_sec / max(trail_window_sec, 1e-6)),
                                is_active=False,
                            )
                        )

        glow_draw.flush()
        crisp_glow_draw.flush()
        glow_layer = self._finalize_glow_layer(glow_layer, width, height)
        image.alpha_composite(glow_layer)
        image.alpha_composite(crisp_glow_layer)

        for item in sorted((trail for trail in trail_items if not trail.is_active), key=lambda trail: trail.age_ratio, reverse=True):
            self._draw_afterimage(draw, item)
        for item in trail_items:
            if item.is_active:
                self._draw_afterimage(draw, item)
        for item in sorted(release_items, key=lambda release: release.age_ratio, reverse=True):
            self._draw_release_fade(draw, item)
        for item in active_items:
            self._draw_active_segment(draw, item.base_rect, item.frame_rect, item.state)
        for burst_x, burst_y, burst_strength in burst_items:
            self._draw_contact_burst(draw, burst_x, burst_y, lane_height, burst_strength)

        draw.flush()

        if self.settings.show_playhead:
            self._draw_playhead(
                draw,
                clamped_time,
                visible_measures,
                left_padding,
                top_padding,
                measure_width,
                plot_height,
                overlay_scale,
            )
        self._draw_performance_overlays(
            draw,
            clamped_time,
            current_measure,
            visible_measures,
            left_padding,
            right_padding,
            vertical_padding,
            width,
            height,
            top_overlay_height,
            bottom_overlay_height,
            overlay_layout,
            overlay_scale,
            safe_insets,
        )

        return self._finalize_frame(image, width, height)

    def _performance_window(self, time_sec: float) -> tuple[int, int]:
        visible_measure_count = max(1, min(len(self.project.measures), int(self.settings.visible_measure_count)))
        current_measure = self.get_measure_for_time(time_sec)
        start_index = max(0, current_measure.index - (visible_measure_count - 1))
        max_start = max(0, len(self.project.measures) - visible_measure_count)
        start_index = min(start_index, max_start)
        return start_index, visible_measure_count

    def _performance_note_range(self, start_measure_index: int, visible_measure_count: int, time_sec: float) -> tuple[int, int]:
        if not self.settings.fit_to_visible_note_range:
            return self._project_note_range()

        notes_in_window: list[int] = []
        for measure_index in range(start_measure_index, start_measure_index + visible_measure_count):
            for segment in self._measure_segments[measure_index]:
                if self.settings.hide_future_notes and segment.note_start_sec > time_sec:
                    continue
                if segment.note_end_sec < time_sec - max(self._afterimage_window_sec(), self._release_fade_window_sec(), 1.0):
                    continue
                notes_in_window.append(segment.note)

        if not notes_in_window:
            return self.project.min_note, self.project.max_note

        min_note = min(notes_in_window)
        max_note = max(notes_in_window)
        if min_note == max_note:
            min_note = max(self.project.min_note, min_note - 2)
            max_note = min(self.project.max_note, max_note + 2)
        return min_note, max_note

    def _project_note_range(self) -> tuple[int, int]:
        min_note = self.project.min_note
        max_note = self.project.max_note
        if min_note == max_note:
            min_note -= 2
            max_note += 2
        return min_note, max_note

    def _segment_visible_end_beat(self, segment: _VisibleSegment, time_sec: float) -> float:
        if self.settings.hide_future_notes and time_sec < segment.note_start_sec:
            return segment.segment_start_beat
        if not self.settings.hide_future_notes and time_sec < segment.note_start_sec:
            return segment.segment_end_beat

        if time_sec >= segment.note_end_sec:
            return segment.segment_end_beat

        reveal_duration = max(0.02, self.settings.attack_fade_duration_sec)
        reveal_ratio = _clamp((time_sec - segment.note_start_sec) / reveal_duration)
        reveal_frontier = _lerp(segment.note_start_beat, segment.note_end_beat, reveal_ratio)
        return min(segment.segment_end_beat, max(segment.segment_start_beat, reveal_frontier))

    def _draw_performance_idle_segment(
        self,
        draw: _LayerContext,
        rect: tuple[float, float, float, float],
        is_finished: bool,
    ) -> None:
        radius = self._rect_radius(rect)
        outline_width = self._outline_width(rect, 0.11, max(0.65, self.settings.active_outline_width))
        outline_color = self.settings.outline_color if is_finished else self.settings.idle_note_color
        outline_alpha = 160 if is_finished else 92
        fill_alpha = 10 if is_finished else 0
        if fill_alpha > 0:
            draw.rounded_rectangle(rect, radius=radius, fill=_with_alpha(self.settings.idle_note_color, fill_alpha))
        draw.rounded_rectangle(
            rect,
            radius=radius,
            outline=_with_alpha(outline_color, outline_alpha),
            width=outline_width,
        )

    def _draw_performance_grid(
        self,
        draw: _LayerContext,
        visible_measures: list[Measure],
        left_padding: float,
        top_padding: float,
        measure_width: float,
        plot_height: float,
        current_measure: Measure,
        overlay_layout: str,
        overlay_scale: float,
    ) -> None:
        max_label_size = 26 if overlay_layout == "wide" else 22 if overlay_layout == "compact" else 18
        minimum_label_size = max(12, int(round(12 * self._relative_overlay_scale(overlay_scale))))
        label_size = max(
            minimum_label_size,
            min(int(plot_height * 0.025), int(max_label_size * overlay_scale), int(measure_width * 0.18)),
        )
        label_font = self._font(label_size, "light")
        label_y = top_padding - getattr(label_font, "size", label_size) - max(6, int(8 * overlay_scale))
        for slot_index, measure in enumerate(visible_measures):
            measure_x0 = left_padding + slot_index * measure_width
            measure_x1 = measure_x0 + measure_width
            boundary_alpha = 150 if measure.index == current_measure.index else 86
            draw.line(
                (measure_x0, top_padding, measure_x0, top_padding + plot_height),
                fill=self._overlay_color(boundary_alpha),
                width=1,
            )
            for beat_index in range(1, measure.numerator):
                beat_ratio = beat_index / max(1, measure.numerator)
                beat_x = _lerp(measure_x0, measure_x1, beat_ratio)
                draw.line(
                    (beat_x, top_padding, beat_x, top_padding + plot_height),
                    fill=_with_alpha(self.settings.idle_note_color, 44),
                    width=1,
                )
            self._draw_overlay_text(
                draw,
                (measure_x0 + 6, label_y),
                f"{measure.index + 1:03d}",
                label_font,
                self._overlay_color(144),
                shadow_alpha=96,
            )
        draw.line(
            (left_padding + len(visible_measures) * measure_width, top_padding, left_padding + len(visible_measures) * measure_width, top_padding + plot_height),
            fill=self._overlay_color(86),
            width=1,
        )

    def _draw_playhead(
        self,
        draw: _LayerContext,
        time_sec: float,
        visible_measures: list[Measure],
        left_padding: float,
        top_padding: float,
        measure_width: float,
        plot_height: float,
        overlay_scale: float,
    ) -> None:
        current_measure = self.get_measure_for_time(time_sec)
        try:
            slot_index = next(index for index, measure in enumerate(visible_measures) if measure.index == current_measure.index)
        except StopIteration:
            return

        beat_ratio = (self._current_beat_in_measure(current_measure, time_sec) - 1.0) / max(current_measure.numerator, 1)
        playhead_x = left_padding + slot_index * measure_width + measure_width * _clamp(beat_ratio)
        line_top = top_padding - 12 * overlay_scale
        line_bottom = top_padding + plot_height + 12 * overlay_scale
        glow_color = _with_alpha(self.settings.animation_accent_color, 42)
        mid_glow_color = _with_alpha(self.settings.animation_accent_color, 88)
        playhead_color = _with_alpha(self.settings.animation_accent_color, 220)

        draw.line(
            (playhead_x, line_top, playhead_x, line_bottom),
            fill=glow_color,
            width=max(2, int(round(6 * overlay_scale))),
        )
        draw.line(
            (playhead_x, line_top, playhead_x, line_bottom),
            fill=mid_glow_color,
            width=max(2, int(round(3 * overlay_scale))),
        )
        draw.line(
            (playhead_x, line_top, playhead_x, line_bottom),
            fill=playhead_color,
            width=max(1, int(round(2 * overlay_scale))),
        )

    def _draw_contact_burst(
        self,
        draw: _LayerContext,
        burst_x: float,
        burst_y: float,
        lane_height: float,
        burst_strength: float,
    ) -> None:
        if burst_strength <= 0.0:
            return
        radius = max(4.0, lane_height * (0.38 + 0.42 * burst_strength))
        alpha = int(110 * burst_strength)
        draw.line(
            (burst_x - radius, burst_y, burst_x + radius, burst_y),
            fill=_with_alpha(self.settings.outline_color, alpha),
            width=max(1, int(lane_height * 0.08)),
        )
        draw.line(
            (burst_x, burst_y - radius * 0.75, burst_x, burst_y + radius * 0.75),
            fill=_with_alpha(self.settings.animation_accent_color, alpha),
            width=max(1, int(lane_height * 0.06)),
        )

    def _draw_performance_overlays(
        self,
        draw: _LayerContext,
        time_sec: float,
        current_measure: Measure,
        visible_measures: list[Measure],
        left_padding: float,
        right_padding: float,
        vertical_padding: float,
        width: int,
        height: int,
        top_overlay_height: float,
        bottom_overlay_height: float,
        overlay_layout: str,
        overlay_scale: float,
        safe_insets: _SafeAreaInsets,
    ) -> None:
        beat_index, beat_fraction = self._beat_display_state(current_measure, time_sec)
        beat_millis = int(_clamp(beat_fraction, 0.0, 0.999) * 1000)
        top_left_x = left_padding
        usable_width = max(1.0, width - left_padding - right_padding)
        stacked_top = overlay_layout != "wide"
        top_y = max(vertical_padding + 10 * overlay_scale, safe_insets.top)
        block_gap = (54 if overlay_layout == "wide" else 34 if overlay_layout == "compact" else 24) * overlay_scale
        divider_gap = (22 if overlay_layout == "wide" else 16 if overlay_layout == "compact" else 12) * overlay_scale
        line_height = 16 * overlay_scale
        label_font = self._font(int(15 * overlay_scale), "light")
        value_font = self._font(int((34 if overlay_layout == "wide" else 30 if overlay_layout == "compact" else 27) * overlay_scale), "light")
        stat_label_font = self._font(int(14 * overlay_scale), "light")
        stat_value_font = self._font(int((20 if overlay_layout == "wide" else 18 if overlay_layout == "compact" else 17) * overlay_scale), "light")
        chord_label_font = self._font(int((16 if overlay_layout == "wide" else 15 if overlay_layout == "compact" else 14) * overlay_scale), "light")
        chord_weight = "bold" if getattr(self.settings, "bold_chord_text", False) else "light"
        chord_font = self._font(int((56 if overlay_layout == "wide" else 48 if overlay_layout == "compact" else 38) * overlay_scale), chord_weight)
        chord_notes_font = self._font(int((21 if overlay_layout == "wide" else 19 if overlay_layout == "compact" else 17) * overlay_scale), "light")
        footer_font = self._font(int(14 * overlay_scale), "light")
        label_y = top_y
        value_y = top_y + 18 * overlay_scale
        top_cursor_y = top_y

        if self.settings.show_time_overlay:
            blocks = (
                ("小節", f"{current_measure.index + 1:03d}"),
                ("拍", f"{beat_index:02d}.{beat_millis:03d}"),
                ("時間", self._format_clock(time_sec)),
            )
            block_x = top_left_x
            beat_block_x = top_left_x
            for index, (label, value) in enumerate(blocks):
                label_bbox = draw.draw.textbbox((0, 0), label, font=label_font)
                value_bbox = draw.draw.textbbox((0, 0), value, font=value_font)
                block_width = max(label_bbox[2] - label_bbox[0], value_bbox[2] - value_bbox[0])
                if index == 1:
                    beat_block_x = block_x
                self._draw_overlay_text(
                    draw,
                    (block_x, label_y),
                    label,
                    label_font,
                    self._overlay_color(170 if index != 1 else 194),
                    shadow_alpha=92,
                )
                self._draw_overlay_text(
                    draw,
                    (block_x, value_y),
                    value,
                    value_font,
                    self._overlay_color(240 if index != 1 else 248),
                    shadow_alpha=116,
                )
                if index < len(blocks) - 1:
                    divider_x = block_x + block_width + divider_gap
                    draw.line(
                        (divider_x, label_y + 2 * overlay_scale, divider_x, value_y + line_height + 2 * overlay_scale),
                        fill=self._overlay_color(44),
                        width=1,
                    )
                block_x += block_width + block_gap
            self._draw_beat_pips(draw, current_measure, beat_index, beat_block_x, value_y + 40 * overlay_scale, overlay_scale)
            top_cursor_y = value_y + 58 * overlay_scale

        if self.settings.show_stats_overlay:
            played_notes = bisect_right(self._note_start_seconds, time_sec + 1e-9)
            total_notes = max(1, len(self.project.notes))
            active_chord = self.get_chord_for_time(time_sec)
            active_note_count = active_chord.active_note_count if active_chord else 0
            stats_lines = (
                ("再生済み", f"{played_notes}/{total_notes} ({played_notes / total_notes:.1%})"),
                ("同時発音", f"{active_note_count} ノート"),
            )
            line_y = top_y if not stacked_top else top_cursor_y + 12 * overlay_scale
            for label, value in stats_lines:
                value_bbox = draw.draw.textbbox((0, 0), value, font=stat_value_font)
                label_bbox = draw.draw.textbbox((0, 0), label, font=stat_label_font)
                if stacked_top:
                    label_x = top_left_x
                    value_x = top_left_x
                else:
                    value_x = width - right_padding - (value_bbox[2] - value_bbox[0])
                    label_x = width - right_padding - (label_bbox[2] - label_bbox[0])
                self._draw_overlay_text(
                    draw,
                    (label_x, line_y),
                    label,
                    stat_label_font,
                    self._overlay_color(156),
                    shadow_alpha=84,
                )
                self._draw_overlay_text(
                    draw,
                    (value_x, line_y + 16 * overlay_scale),
                    value,
                    stat_value_font,
                    self._overlay_color(232),
                    shadow_alpha=100,
                )
                line_y += 42 * overlay_scale
            top_cursor_y = max(top_cursor_y, line_y)

        if self.settings.show_measure_overlay and visible_measures:
            footer_text = f"表示小節 {len(visible_measures)}"
            bottom_safe_margin = max(vertical_padding, safe_insets.bottom)
            footer_y = height - bottom_safe_margin - bottom_overlay_height + 28 * overlay_scale
            if overlay_layout == "portrait" and self.settings.show_chord_overlay:
                footer_y = height - bottom_safe_margin - bottom_overlay_height + 108 * overlay_scale
            self._draw_overlay_text(
                draw,
                (left_padding, footer_y),
                footer_text,
                footer_font,
                self._overlay_color(154),
                shadow_alpha=86,
            )

        if self.settings.show_chord_overlay:
            chord = self.get_chord_for_time(time_sec)
            chord_text = chord.chord_name if chord is not None else "N.C."
            notes_text = "Notes " + (" ".join(chord.note_names) if chord is not None else "-")
            chord_label = "コード"
            chord_label_bbox = draw.draw.textbbox((0, 0), chord_label, font=chord_label_font)
            chord_bbox = draw.draw.textbbox((0, 0), chord_text, font=chord_font)
            notes_bbox = draw.draw.textbbox((0, 0), notes_text, font=chord_notes_font)
            chord_block_width = max(
                chord_label_bbox[2] - chord_label_bbox[0],
                chord_bbox[2] - chord_bbox[0],
                notes_bbox[2] - notes_bbox[0],
            )
            chord_block_width = min(chord_block_width, usable_width)
            chord_x = width - right_padding - chord_block_width
            if overlay_layout == "portrait":
                chord_x = top_left_x
            chord_y = height - max(vertical_padding, safe_insets.bottom) - bottom_overlay_height + 10 * overlay_scale
            draw.line(
                (chord_x, chord_y - 10 * overlay_scale, chord_x + min(chord_block_width, 108 * overlay_scale), chord_y - 10 * overlay_scale),
                fill=_with_alpha(self.settings.animation_accent_color, 136),
                width=max(1, int(round(2 * overlay_scale))),
            )
            self._draw_overlay_text(
                draw,
                (chord_x, chord_y),
                chord_label,
                chord_label_font,
                self._overlay_color(170),
                shadow_alpha=96,
            )
            self._draw_overlay_text(
                draw,
                (chord_x, chord_y + 18 * overlay_scale),
                chord_text,
                chord_font,
                self._overlay_color(244),
                shadow_alpha=118,
                embolden=max(1, int(round(overlay_scale))) if getattr(self.settings, "bold_chord_text", False) else 0,
            )
            self._draw_overlay_text(
                draw,
                (chord_x, chord_y + 76 * overlay_scale),
                notes_text,
                chord_notes_font,
                self._overlay_color(176),
                shadow_alpha=88,
            )

    def _draw_beat_pips(self, draw: _LayerContext, measure: Measure, beat_index: int, origin_x: float, origin_y: float, overlay_scale: float = 1.0) -> None:
        pip_width = max(16, int(round(26 * overlay_scale)))
        gap = max(5, int(round(10 * overlay_scale)))
        pip_height = max(4, int(round(6 * overlay_scale)))
        for index in range(measure.numerator):
            x0 = origin_x + index * (pip_width + gap)
            color = self.settings.animation_accent_color if index + 1 == beat_index else self.settings.outline_color if index + 1 < beat_index else self.settings.idle_note_color
            alpha = 214 if index + 1 == beat_index else 126 if index + 1 < beat_index else 54
            draw.rectangle((x0, origin_y, x0 + pip_width, origin_y + pip_height), fill=_with_alpha(color, alpha))

    def _beat_display_state(self, measure: Measure, time_sec: float) -> tuple[int, float]:
        beat_progress = max(0.0, self._current_beat_in_measure(measure, time_sec) - 1.0)
        whole_beats_elapsed = int(math.floor(beat_progress + 1e-9))
        clamped_elapsed = min(max(0, whole_beats_elapsed), max(0, measure.numerator - 1))
        beat_index = clamped_elapsed + 1
        beat_fraction = _clamp(beat_progress - whole_beats_elapsed, 0.0, 0.999999)
        return beat_index, beat_fraction

    def _current_beat_in_measure(self, measure: Measure, time_sec: float) -> float:
        measure_duration = max(1e-9, measure.end_sec - measure.start_sec)
        elapsed_ratio = _clamp((time_sec - measure.start_sec) / measure_duration)
        return 1.0 + elapsed_ratio * max(0.0, float(measure.numerator))

    def get_chord_for_time(self, time_sec: float):
        if not self.project.chords:
            return None
        index = bisect_right(self._chord_start_seconds, time_sec) - 1
        if index < 0:
            return None
        chord = self.project.chords[index]
        if chord.start_sec <= time_sec < chord.end_sec:
            return chord
        return None

    @staticmethod
    def _format_clock(seconds: float) -> str:
        total_milliseconds = max(0, int(round(seconds * 1000)))
        minutes, remainder = divmod(total_milliseconds, 60_000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"

    def _get_prepared_measure(self, measure: Measure, width: int, height: int) -> tuple[Image.Image, tuple[_PreparedSegment, ...]]:
        cache_key = (measure.index, width, height, self._cache_signature())
        cached = self._measure_render_cache.get(cache_key)
        if cached is not None:
            return cached

        image = Image.new("RGBA", (width, height), self._background_fill())
        draw = _LayerContext(image)

        horizontal_padding = width * self.settings.horizontal_padding_ratio
        vertical_padding = height * self.settings.vertical_padding_ratio
        left_padding = horizontal_padding
        right_padding = horizontal_padding
        top_padding = vertical_padding
        bottom_padding = vertical_padding

        plot_width = max(1.0, width - left_padding - right_padding)
        plot_height = max(1.0, height - top_padding - bottom_padding)

        note_range = max(1, self.project.max_note - self.project.min_note + 1)
        lane_height = plot_height / note_range
        rectangle_height = max(2.0, lane_height * 0.6)
        min_rectangle_width = max(2.0, width * 0.001)

        prepared_segments: list[_PreparedSegment] = []
        for segment in self._measure_segments[measure.index]:
            x0 = left_padding + plot_width * segment.start_ratio
            x1 = left_padding + plot_width * segment.end_ratio
            if x1 - x0 < min_rectangle_width:
                x1 = x0 + min_rectangle_width

            pitch_index = self.project.max_note - segment.note
            lane_top = top_padding + pitch_index * lane_height
            y0 = lane_top + (lane_height - rectangle_height) / 2.0
            y1 = y0 + rectangle_height
            rect = self._scaled_note_rect((x0, y0, x1, y1), min_rectangle_width)
            prepared_segments.append(_PreparedSegment(segment=segment, rect=rect))
            self._draw_idle_segment(draw, rect)

        draw.flush()
        prepared = (image, tuple(prepared_segments))
        self._measure_render_cache[cache_key] = prepared
        return prepared

    def _cache_signature(self) -> tuple[object, ...]:
        settings = self.settings
        return (
            settings.background_color,
            settings.transparent_background,
            settings.idle_note_color,
            settings.outline_color,
            settings.corner_style,
            settings.note_length_scale,
            settings.note_height_scale,
            settings.horizontal_padding_ratio,
            settings.vertical_padding_ratio,
            settings.idle_outline_width,
            getattr(settings, "font_family", _DEFAULT_FONT_FAMILY),
            getattr(settings, "custom_font_path", ""),
        )

    def _background_fill(self) -> tuple[int, int, int, int]:
        if self.settings.transparent_background:
            return 0, 0, 0, 0
        return _with_alpha(self.settings.background_color, 255)

    def _finalize_frame(self, image: Image.Image, width: int, height: int) -> Image.Image:
        self._draw_canvas_border(image, width, height)
        return image if self.settings.transparent_background else image.convert("RGB")

    def _draw_canvas_border(self, image: Image.Image, width: int, height: int) -> None:
        if not getattr(self.settings, "canvas_border_enabled", True):
            return

        border_scale = max(0.0, float(getattr(self.settings, "canvas_border_width", 1.0)))
        if border_scale <= 0.0:
            return

        border_width = max(1, int(round(min(width, height) * 0.0018 * border_scale)))
        rect = (
            0,
            0,
            max(0, width - 1),
            max(0, height - 1),
        )
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle(
            rect,
            outline=_with_alpha(getattr(self.settings, "canvas_border_color", "#3f3f3f"), 230),
            width=border_width,
        )

        inner_offset = border_width + 1
        if width > inner_offset * 2 + 2 and height > inner_offset * 2 + 2:
            draw.rectangle(
                (
                    inner_offset,
                    inner_offset,
                    width - inner_offset - 1,
                    height - inner_offset - 1,
                ),
                outline=_with_alpha(getattr(self.settings, "canvas_border_color", "#3f3f3f"), 72),
                width=max(1, border_width // 2),
            )

    @staticmethod
    def _overlay_scale(width: float, height: float) -> float:
        reference_width, reference_height = ProjectRenderer._preview_reference_size(width, height)
        base_scale = math.sqrt(max(1.0, reference_width * reference_height) / (1920.0 * 1080.0))
        base_scale = max(MIN_OVERLAY_SCALE, min(base_scale, 2.4))
        if width <= reference_width + 1e-6 and height <= reference_height + 1e-6:
            return base_scale
        output_scale = min(width / max(reference_width, 1.0), height / max(reference_height, 1.0))
        return max(MIN_OVERLAY_SCALE, min(base_scale * output_scale, MAX_OVERLAY_SCALE))

    @staticmethod
    def _preview_reference_size(width: float, height: float) -> tuple[float, float]:
        aspect_ratio = max(1e-6, width / max(height, 1.0))
        max_reference_ratio = PREVIEW_REFERENCE_MAX_WIDTH / PREVIEW_REFERENCE_MAX_HEIGHT
        if aspect_ratio >= max_reference_ratio:
            reference_width = PREVIEW_REFERENCE_MAX_WIDTH
            reference_height = max(1.0, reference_width / aspect_ratio)
        else:
            reference_height = PREVIEW_REFERENCE_MAX_HEIGHT
            reference_width = max(1.0, reference_height * aspect_ratio)
        return reference_width, reference_height

    @staticmethod
    def _relative_overlay_scale(overlay_scale: float) -> float:
        return max(1.0, overlay_scale / MIN_OVERLAY_SCALE)

    def _safe_area_insets(self, width: float, height: float, overlay_layout: str) -> _SafeAreaInsets:
        if overlay_layout != "portrait" or not getattr(self.settings, "safe_area_enabled", True):
            return _SafeAreaInsets()

        scale = _clamp(float(getattr(self.settings, "safe_area_scale", 1.0)), 0.0, 2.0)
        return _SafeAreaInsets(
            left=width * 0.055 * scale,
            top=height * 0.085 * scale,
            right=width * 0.16 * scale,
            bottom=height * 0.18 * scale,
        )

    def _safe_area_should_scale(self, width: float, height: float, overlay_layout: str) -> bool:
        if overlay_layout != "portrait" or not getattr(self.settings, "safe_area_enabled", True):
            return False

        safe_insets = self._safe_area_insets(width, height, overlay_layout)
        safe_width = width - safe_insets.left - safe_insets.right
        safe_height = height - safe_insets.top - safe_insets.bottom
        return safe_width > 1.0 and safe_height > 1.0 and (
            safe_insets.left > 0.0 or safe_insets.top > 0.0 or safe_insets.right > 0.0 or safe_insets.bottom > 0.0
        )

    def _render_safe_scaled_performance_frame(
        self,
        clamped_time: float,
        width: int,
        height: int,
        overlay_layout: str,
    ) -> Image.Image:
        safe_insets = self._safe_area_insets(width, height, overlay_layout)
        safe_width = max(1.0, width - safe_insets.left - safe_insets.right)
        safe_height = max(1.0, height - safe_insets.top - safe_insets.bottom)
        safe_scale = min(1.0, safe_width / max(width, 1.0), safe_height / max(height, 1.0))

        output = Image.new("RGBA", (width, height), self._background_fill())
        original_safe_area_enabled = self.settings.safe_area_enabled
        original_transparent_background = self.settings.transparent_background
        original_canvas_border_enabled = self.settings.canvas_border_enabled

        try:
            self.settings.safe_area_enabled = False
            self.settings.transparent_background = True
            self.settings.canvas_border_enabled = False
            content = self._render_performance_frame(clamped_time, width, height)
        finally:
            self.settings.safe_area_enabled = original_safe_area_enabled
            self.settings.transparent_background = original_transparent_background
            self.settings.canvas_border_enabled = original_canvas_border_enabled

        scaled_width = max(1, int(round(width * safe_scale)))
        scaled_height = max(1, int(round(height * safe_scale)))
        if (scaled_width, scaled_height) != (width, height):
            resample_filter = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
            content = content.resize((scaled_width, scaled_height), resample_filter)

        x = int(round(safe_insets.left + (safe_width - scaled_width) / 2.0))
        y = int(round(safe_insets.top + (safe_height - scaled_height) / 2.0))
        x = max(0, min(width - scaled_width, x))
        y = max(0, min(height - scaled_height, y))
        output.alpha_composite(content, (x, y))
        return self._finalize_frame(output, width, height)

    @staticmethod
    def _safe_overlay_scale(overlay_scale: float, overlay_layout: str, safe_insets: _SafeAreaInsets) -> float:
        if overlay_layout != "portrait" or safe_insets.bottom <= 0:
            return overlay_scale
        return max(MIN_OVERLAY_SCALE, overlay_scale * 0.88)

    @staticmethod
    def _overlay_layout_mode(width: float, height: float) -> str:
        aspect_ratio = width / max(height, 1.0)
        if aspect_ratio < 0.9:
            return "portrait"
        if aspect_ratio < 1.35:
            return "compact"
        return "wide"

    def _performance_overlay_heights(self, overlay_layout: str, overlay_scale: float) -> tuple[float, float]:
        if overlay_layout == "portrait":
            top_height = 224 * overlay_scale if self.settings.show_time_overlay or self.settings.show_stats_overlay else 46 * overlay_scale
            bottom_height = 146 * overlay_scale if self.settings.show_chord_overlay else 54 * overlay_scale
            return top_height, bottom_height
        if overlay_layout == "compact":
            top_height = 212 * overlay_scale if self.settings.show_time_overlay or self.settings.show_stats_overlay else 44 * overlay_scale
            bottom_height = 126 * overlay_scale if self.settings.show_chord_overlay else 50 * overlay_scale
            return top_height, bottom_height
        top_height = 128 * overlay_scale if self.settings.show_time_overlay or self.settings.show_stats_overlay else 42 * overlay_scale
        bottom_height = 112 * overlay_scale if self.settings.show_chord_overlay else 46 * overlay_scale
        return top_height, bottom_height

    def _lyrics_reserve_height(self, overlay_layout: str, overlay_scale: float) -> float:
        if not self.settings.show_chord_overlay:
            return 0.0
        space_scale = max(0.0, float(getattr(self.settings, "lyrics_space_scale", 1.0)))
        if overlay_layout == "portrait":
            return 132 * overlay_scale * space_scale
        if overlay_layout == "compact":
            return 108 * overlay_scale * space_scale
        return 84 * overlay_scale * space_scale

    def _overlay_color(self, alpha: int) -> tuple[int, int, int, int]:
        return _with_alpha(self.settings.text_color, alpha)

    def _overlay_stroke_color(self, alpha: int) -> tuple[int, int, int, int]:
        red, green, blue = _hex_to_rgb(self.settings.text_color)
        luminance = red * 0.299 + green * 0.587 + blue * 0.114
        stroke_hex = "#000000" if luminance >= 150 else "#ffffff"
        return _with_alpha(stroke_hex, alpha)

    def _draw_hud_panel(
        self,
        draw: _LayerContext,
        rect: tuple[float, float, float, float],
        radius: float,
        accent: bool,
        fill_alpha: int,
        outline_alpha: int,
    ) -> None:
        fill_color = _with_alpha(self.settings.background_color, fill_alpha)
        outline_color = _with_alpha(self.settings.animation_accent_color if accent else self.settings.outline_color, outline_alpha)
        normalized = _normalize_rect(rect)
        outline_width = max(1, int(round(radius * 0.16)))
        draw.draw.rounded_rectangle(normalized, radius=radius, fill=fill_color)
        draw.draw.rounded_rectangle(
            normalized,
            radius=radius,
            outline=outline_color,
            width=outline_width,
        )

    def _draw_overlay_text(
        self,
        draw: _LayerContext,
        position: tuple[float, float],
        text: str,
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int, int],
        shadow_alpha: int = 96,
        embolden: int = 0,
    ) -> None:
        shadow_offset = max(1, int(round(getattr(font, "size", 16) * 0.06)))
        if shadow_alpha > 0:
            shadow_fill = self._overlay_stroke_color(min(255, shadow_alpha))
            draw.draw.text(
                (position[0], position[1] + shadow_offset),
                text,
                fill=shadow_fill,
                font=font,
            )
        if embolden > 0:
            for offset_x in range(1, embolden + 1):
                draw.draw.text(
                    (position[0] + offset_x, position[1]),
                    text,
                    fill=fill,
                    font=font,
                )
                draw.draw.text(
                    (position[0] - offset_x, position[1]),
                    text,
                    fill=fill,
                    font=font,
                )
        draw.draw.text(
            position,
            text,
            fill=fill,
            font=font,
        )

    def _draw_idle_segment(self, draw: _LayerContext, rect: tuple[float, float, float, float]) -> None:
        radius = self._rect_radius(rect)
        draw.rounded_rectangle(rect, radius=radius, fill=_with_alpha(self.settings.idle_note_color, 255))
        outline_width = self._outline_width(rect, 0.08, self.settings.idle_outline_width)
        if outline_width > 0:
            draw.rounded_rectangle(
                rect,
                radius=radius,
                outline=_with_alpha(self.settings.outline_color, 118),
                width=outline_width,
            )

    def _draw_active_segment(
        self,
        draw: _LayerContext,
        base_rect: tuple[float, float, float, float],
        frame_rect: tuple[float, float, float, float],
        state: _AnimationState,
    ) -> None:
        # Calculate attack fade visibility
        style = self.settings.attack_fade_style
        attack_visibility = 1.0 if style == "none" else self._attack_fade_visibility(state.attack_ratio)
        
        fill_color = self._active_fill_color(state)
        base_radius = self._rect_radius(base_rect)
        frame_radius = self._rect_radius(frame_rect)
        
        # Apply attack fade to fill color based on style
        if style in {"fill", "both"}:
            fill_color = (fill_color[0], fill_color[1], fill_color[2], int(fill_color[3] * attack_visibility))
        
        draw.rounded_rectangle(base_rect, radius=base_radius, fill=fill_color)

        outline_alpha = 225 if self.settings.glow_style in {"neon", "outline", "prism"} else 175
        outline_width = self._outline_width(base_rect, 0.12, self.settings.active_outline_width)
        if outline_width > 0:
            if style in {"outline", "both"}:
                outline_color = _with_alpha(self.settings.outline_color, int(outline_alpha * attack_visibility))
            else:
                outline_color = _with_alpha(self.settings.outline_color, outline_alpha)
            draw.rounded_rectangle(
                base_rect,
                radius=base_radius,
                outline=outline_color,
                width=outline_width,
            )

        self._draw_animation_overlay(draw, base_rect, frame_rect, base_radius, frame_radius, state)

    def _draw_release_fade(self, draw: _LayerContext, item: _ReleaseRenderItem) -> None:
        style = self.settings.release_fade_style
        visibility = self._release_fade_visibility(item.age_ratio)
        if style == "none" or visibility <= 0.01:
            return

        base_rect = item.base_rect
        frame_rect = item.frame_rect
        base_radius = self._rect_radius(base_rect)
        frame_radius = self._rect_radius(frame_rect)
        fill_color = self._active_fill_color(item.state)

        if style in {"fill", "both"}:
            draw.rounded_rectangle(
                base_rect,
                radius=base_radius,
                fill=(fill_color[0], fill_color[1], fill_color[2], int(190 * visibility)),
            )

        if style in {"outline", "both"}:
            outline_width = self._outline_width(frame_rect, 0.12, self.settings.active_outline_width)
            if outline_width > 0:
                outline_alpha = 205 if self.settings.glow_style in {"neon", "outline", "prism"} else 155
                draw.rounded_rectangle(
                    frame_rect,
                    radius=frame_radius,
                    outline=_with_alpha(self.settings.outline_color, int(outline_alpha * visibility)),
                    width=outline_width,
                )

    def _draw_afterimage(self, draw: _LayerContext, item: _TrailRenderItem) -> None:
        style = self._resolved_afterimage_style()
        strength = self.settings.afterimage_strength * max(0.2, self.settings.animation_strength)
        if style == "none" or strength <= 0.0 or self.settings.animation_style == "none":
            return

        rect = item.frame_rect if item.is_active else item.base_rect
        age_ratio = _clamp(item.age_ratio)
        visibility = strength * ((1.0 - age_ratio) ** 0.82)
        if not item.is_active and visibility <= 0.03:
            return

        state = item.state
        emphasis = 1.0 if state is None else 0.45 + state.wave * 0.55
        outer_rect = self._afterimage_frame_rect(rect, item.is_active, visibility, emphasis)
        outer_radius = self._rect_radius(outer_rect)

        if item.is_active:
            outline_color = _with_alpha(self.settings.outline_color, int(220 * _clamp(0.55 + visibility * 0.7)))
            glow_outline = _with_alpha(self.settings.outline_color, int(92 * _clamp(0.35 + visibility)))
            fill_color = _with_alpha(self.settings.active_note_color, int(44 * _clamp(0.2 + visibility)))
        else:
            outline_mix = 0.78
            outline_tuple = _mix_colors(self.settings.outline_color, self.settings.idle_note_color, outline_mix)
            outline_color = (outline_tuple[0], outline_tuple[1], outline_tuple[2], int(122 * visibility))
            glow_outline = (outline_tuple[0], outline_tuple[1], outline_tuple[2], int(48 * visibility))
            fill_tuple = _mix_colors(self.settings.active_note_color, self.settings.idle_note_color, 0.78)
            fill_color = (fill_tuple[0], fill_tuple[1], fill_tuple[2], int(28 * visibility))

        frame_width = self._outline_width(
            outer_rect,
            0.08 if item.is_active else 0.065,
            self.settings.afterimage_outline_width,
        )

        if style in {"fill", "both"}:
            draw.rounded_rectangle(outer_rect, radius=outer_radius, fill=fill_color)

        if style in {"outline", "both"} and frame_width > 0:
            halo_rect = _expand_rect(outer_rect, 1.5, 1.5)
            draw.rounded_rectangle(
                halo_rect,
                radius=self._rect_radius(halo_rect),
                outline=glow_outline,
                width=max(1, frame_width + 1),
            )
            draw.rounded_rectangle(
                outer_rect,
                radius=outer_radius,
                outline=outline_color,
                width=frame_width,
            )

    def _resolved_afterimage_style(self) -> str:
        style = self.settings.afterimage_style
        if style != "auto":
            return style

        animation_style = self.settings.animation_style
        if animation_style in {"pop", "breathe", "wave"}:
            return "both"
        if animation_style in {"pulse", "bounce", "expand", "shimmer"}:
            return "fill"
        if animation_style == "none":
            return "none"
        return "outline"

    def _afterimage_window_sec(self) -> float:
        return max(0.0, self.settings.afterimage_duration_sec)

    def _release_fade_window_sec(self) -> float:
        return max(0.0, self.settings.release_fade_duration_sec)

    def _afterimage_frame_rect(
        self,
        rect: tuple[float, float, float, float],
        is_active: bool,
        visibility: float,
        emphasis: float,
    ) -> tuple[float, float, float, float]:
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        base_pad = max(height * (0.42 + 0.18 * visibility + 0.12 * emphasis), min(width, height) * 0.16)
        horizontal_pad = base_pad * (1.1 + min(0.34, width / max(height, 1.0) * 0.035))
        vertical_pad = base_pad * (0.92 + visibility * 0.28)

        if is_active:
            horizontal_pad += height * 0.1
            vertical_pad += height * 0.12

        padding_scale = max(0.0, self.settings.afterimage_padding_scale)
        horizontal_pad *= padding_scale
        vertical_pad *= padding_scale
        return _expand_rect(rect, horizontal_pad, vertical_pad)

    def _release_fade_visibility(self, age_ratio: float) -> float:
        progress = _clamp(age_ratio)
        curve = self.settings.release_fade_curve
        if curve == "linear":
            return 1.0 - progress
        if curve == "sharp":
            return (1.0 - progress) ** 2.15
        eased = progress * progress * (3.0 - 2.0 * progress)
        return 1.0 - eased

    def _attack_fade_visibility(self, attack_ratio: float) -> float:
        progress = _clamp(attack_ratio)
        curve = self.settings.attack_fade_curve
        if curve == "linear":
            return progress
        if curve == "sharp":
            return progress ** 1.6
        eased = progress * progress * (3.0 - 2.0 * progress)
        return eased

    def _build_animation_state(self, segment: _VisibleSegment, time_sec: float) -> _AnimationState:
        duration = max(segment.note_end_sec - segment.note_start_sec, 1e-6)
        phase = _clamp((time_sec - segment.note_start_sec) / duration)
        speed = max(0.25, self.settings.animation_speed)
        seed = (segment.note * 0.137 + segment.note_start_sec * 0.071) % 1.0
        cycle = phase * speed + seed
        wave = 0.5 + 0.5 * math.sin(cycle * math.tau)
        flicker = 0.35 + 0.65 * abs(math.sin((phase * (speed * 3.7 + 0.8) + seed) * math.tau))
        lift = math.sin(cycle * math.tau)
        stepped = round((0.15 + wave * 0.85) * 4.0) / 4.0
        jitter = round(math.sin((cycle * 4.5 + seed) * math.tau) * 2.0) / 2.0
        saw = (cycle * 1.35) % 1.0
        burst = math.sin(saw * math.pi)
        
        # Calculate attack fade progress
        attack_fade_duration = max(0.0, self.settings.attack_fade_duration_sec)
        attack_age_sec = time_sec - segment.note_start_sec
        attack_ratio = 1.0 if attack_fade_duration <= 0.0 else min(1.0, max(0.0, attack_age_sec / attack_fade_duration))
        
        return _AnimationState(
            phase=phase,
            wave=wave,
            flicker=flicker,
            lift=lift,
            stepped=stepped,
            jitter=jitter,
            burst=burst,
            saw=saw,
            attack_ratio=attack_ratio,
        )

    def _animated_rect(
        self,
        rect: tuple[float, float, float, float],
        state: _AnimationState,
    ) -> tuple[float, float, float, float]:
        style = self.settings.animation_style
        strength = self.settings.animation_strength
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]

        expand_x = 0.0
        expand_y = 0.0
        if style == "blink":
            snap = 1.0 if state.stepped >= 0.5 else 0.0
            expand_x = width * 0.08 * strength * snap
            expand_y = height * 0.32 * strength * snap
        elif style == "pop":
            pop_amount = 0.32 + state.burst * 0.95
            expand_x = width * 0.16 * strength * pop_amount
            expand_y = height * 0.48 * strength * pop_amount
        elif style == "scan":
            expand_y = height * 0.26 * strength * (0.35 + state.stepped * 0.65)
            expand_x = width * 0.03 * strength * state.stepped
        elif style == "jitter":
            expand_x = width * 0.05 * strength * abs(state.jitter)
            expand_y = height * 0.26 * strength * abs(state.jitter)
        elif style == "arcade":
            snap = 1.0 if state.stepped >= 0.5 else 0.0
            expand_x = width * 0.08 * strength * state.stepped
            expand_y = height * 0.18 * strength * (0.2 + snap * 0.8)
        elif style == "pulse":
            pulse = 0.18 + state.wave * 0.82
            expand_x = width * 0.12 * strength * pulse
            expand_y = height * 0.38 * strength * pulse
        elif style == "breathe":
            stretch = state.wave - 0.5
            expand_x = width * 0.08 * strength * stretch
            expand_y = height * 0.44 * strength * stretch
        elif style == "shimmer":
            expand_x = width * 0.05 * strength * (0.5 + state.burst * 0.5)
            expand_y = height * 0.12 * strength * (0.35 + state.wave * 0.65)
        elif style == "bounce":
            hop = abs(state.lift)
            expand_x = width * 0.08 * strength * hop
            expand_y = height * 0.42 * strength * hop - height * 0.08 * strength * (1.0 - hop)
        elif style == "expand":
            expansion = 0.25 + state.wave * 0.95
            expand_x = width * 0.16 * strength * expansion
            expand_y = height * 0.42 * strength * expansion
        elif style == "flicker":
            expand_x = width * 0.06 * strength * state.flicker
            expand_y = height * 0.24 * strength * state.flicker
        elif style == "wave":
            expand_x = width * 0.08 * strength * state.wave
            expand_y = height * 0.3 * strength * (0.25 + state.wave)

        return _expand_rect(rect, expand_x, expand_y)

    def _draw_glow(
        self,
        glow_draw: _LayerContext,
        crisp_glow_draw: _LayerContext,
        rect: tuple[float, float, float, float],
        radius: float,
        state: _AnimationState,
    ) -> None:
        style = self.settings.glow_style
        strength = self.settings.glow_strength
        if style == "none" or strength <= 0.0:
            return

        # Apply attack fade to glow
        attack_fade_style = self.settings.attack_fade_style
        attack_visibility = 1.0 if attack_fade_style == "none" else self._attack_fade_visibility(state.attack_ratio)

        height = rect[3] - rect[1]
        base_alpha = int(165 * _clamp(0.3 + strength) * attack_visibility)

        if style == "soft":
            for scale, alpha_scale in ((0.4, 0.55), (0.85, 0.3), (1.25, 0.16)):
                expansion = height * strength * scale
                glow_draw.rounded_rectangle(
                    _expand_rect(rect, expansion, expansion),
                    radius=radius + expansion,
                    fill=_with_alpha(self.settings.glow_color, int(base_alpha * alpha_scale)),
                )
            return

        if style == "mist":
            for scale, alpha_scale in ((0.7, 0.44), (1.25, 0.28), (1.9, 0.18), (2.6, 0.1)):
                expansion = height * strength * scale
                glow_draw.rounded_rectangle(
                    _expand_rect(rect, expansion, expansion * 1.2),
                    radius=radius + expansion,
                    fill=_with_alpha(self.settings.glow_color, int(base_alpha * alpha_scale)),
                )
            return

        if style == "bloom":
            for scale, alpha_scale in ((0.55, 0.5), (1.1, 0.34), (1.85, 0.22), (2.8, 0.12)):
                expansion = height * strength * scale
                glow_draw.rounded_rectangle(
                    _expand_rect(rect, expansion * 1.1, expansion * 1.25),
                    radius=radius + expansion,
                    fill=_with_alpha(self.settings.glow_color, int(base_alpha * alpha_scale)),
                )
            crisp_glow_draw.rounded_rectangle(
                _expand_rect(rect, height * 0.05, height * 0.05),
                radius=radius + height * 0.05,
                fill=_with_alpha(self.settings.active_note_color, 54),
            )
            return

        if style == "neon":
            for scale, alpha_scale in ((0.2, 0.75), (0.55, 0.38), (1.0, 0.18)):
                expansion = height * strength * scale
                glow_draw.rounded_rectangle(
                    _expand_rect(rect, expansion, expansion),
                    radius=radius + expansion,
                    fill=_with_alpha(self.settings.glow_color, int(base_alpha * alpha_scale)),
                )
            crisp_glow_draw.rounded_rectangle(
                rect,
                radius=radius,
                outline=_with_alpha(self.settings.outline_color, 235),
                width=max(1, int(height * 0.14)),
            )
            return

        if style == "aura":
            aura_colors = (
                self.settings.glow_color,
                self.settings.animation_accent_color,
                self.settings.glow_color,
            )
            for index, color in enumerate(aura_colors):
                expansion = height * strength * (0.3 + index * 0.4 + state.wave * 0.15)
                glow_draw.rounded_rectangle(
                    _expand_rect(rect, expansion, expansion),
                    radius=radius + expansion,
                    fill=_with_alpha(color, int(base_alpha / (1.0 + index * 1.15))),
                )
            return

        if style == "outline":
            expansion = height * strength * 0.18
            crisp_glow_draw.rounded_rectangle(
                _expand_rect(rect, expansion, expansion),
                radius=radius + expansion,
                outline=_with_alpha(self.settings.outline_color, 220),
                width=max(1, int(height * 0.18)),
            )
            glow_draw.rounded_rectangle(
                _expand_rect(rect, expansion * 1.4, expansion * 1.4),
                radius=radius + expansion * 1.4,
                fill=_with_alpha(self.settings.glow_color, 60),
            )
            return

        if style == "shadow":
            shadow_offset = height * strength * 0.38
            for index, alpha in enumerate((90, 54, 28)):
                expansion = height * strength * (0.18 + index * 0.22)
                shadow_rect = _offset_rect(
                    _expand_rect(rect, expansion, expansion),
                    shadow_offset * (0.8 + index * 0.18),
                    shadow_offset * (0.8 + index * 0.18),
                )
                glow_draw.rounded_rectangle(
                    shadow_rect,
                    radius=radius + expansion,
                    fill=_with_alpha(self.settings.glow_color, alpha),
                )
            return

        if style == "prism":
            prism_layers = (
                (self.settings.glow_color, 0.28, 0.64),
                (self.settings.animation_accent_color, 0.7, 0.32),
                (self.settings.outline_color, 1.18, 0.16),
            )
            for color, scale, alpha_scale in prism_layers:
                expansion = height * strength * (scale + state.wave * 0.08)
                glow_draw.rounded_rectangle(
                    _expand_rect(rect, expansion, expansion),
                    radius=radius + expansion,
                    fill=_with_alpha(color, int(base_alpha * alpha_scale)),
                )
            crisp_glow_draw.rounded_rectangle(
                rect,
                radius=radius,
                outline=_with_alpha(self.settings.outline_color, 205),
                width=max(1, int(height * 0.1)),
            )

    def _finalize_glow_layer(self, glow_layer: Image.Image, width: int, height: int) -> Image.Image:
        style = self.settings.glow_style
        strength = self.settings.glow_strength
        if style == "none" or strength <= 0.0:
            return glow_layer

        blur_map = {
            "soft": (0.006, 0.011),
            "mist": (0.014, 0.028),
            "bloom": (0.018, 0.038),
            "neon": (0.004, 0.009),
            "aura": (0.01, 0.02),
            "outline": (0.004, 0.008),
            "shadow": (0.01, 0.018),
            "prism": (0.007, 0.015),
        }
        first_factor, second_factor = blur_map.get(style, (0.006, 0.012))
        first_radius = max(1.0, height * first_factor * max(0.4, strength))
        second_radius = max(first_radius + 0.5, height * second_factor * max(0.55, strength))

        first = glow_layer.filter(ImageFilter.GaussianBlur(first_radius))
        second = _scale_image_alpha(glow_layer.filter(ImageFilter.GaussianBlur(second_radius)), 0.75)
        combined = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        combined.alpha_composite(first)
        combined.alpha_composite(second)

        if style in {"mist", "bloom"}:
            third_radius = second_radius * (1.45 if style == "mist" else 1.75)
            third_strength = 0.52 if style == "mist" else 0.65
            third = _scale_image_alpha(glow_layer.filter(ImageFilter.GaussianBlur(third_radius)), third_strength)
            combined.alpha_composite(third)

        return combined

    def _active_fill_color(self, state: _AnimationState) -> tuple[int, int, int, int]:
        style = self.settings.animation_style
        strength = self.settings.animation_strength
        mix_amount = 0.0

        if style == "blink":
            mix_amount = 0.42 * strength * (1.0 if state.stepped >= 0.5 else 0.08)
        elif style == "pop":
            mix_amount = 0.38 * strength * (0.25 + state.burst * 0.75)
        elif style == "scan":
            mix_amount = 0.2 * strength * (0.35 + state.saw * 0.65)
        elif style == "jitter":
            mix_amount = 0.28 * strength * abs(state.jitter)
        elif style == "arcade":
            mix_amount = 0.34 * strength * (0.35 + state.stepped * 0.65)
        elif style == "pulse":
            mix_amount = 0.18 * strength * (0.2 + state.wave * 0.8)
        elif style == "breathe":
            mix_amount = 0.17 * strength * (0.25 + state.wave * 0.75)
        elif style == "shimmer":
            mix_amount = 0.25 * strength * (0.25 + state.burst * 0.75)
        elif style == "bounce":
            mix_amount = 0.22 * strength * (0.2 + abs(state.lift) * 0.8)
        elif style == "expand":
            mix_amount = 0.28 * strength * (0.25 + state.wave * 0.75)
        elif style == "flicker":
            mix_amount = 0.35 * strength * state.flicker
        elif style == "wave":
            mix_amount = 0.22 * strength * (0.25 + state.wave * 0.75)

        return _mix_colors(self.settings.active_note_color, self.settings.animation_accent_color, mix_amount)

    def _draw_animation_overlay(
        self,
        draw: _LayerContext,
        base_rect: tuple[float, float, float, float],
        frame_rect: tuple[float, float, float, float],
        base_radius: float,
        frame_radius: float,
        state: _AnimationState,
    ) -> None:
        style = self.settings.animation_style
        strength = self.settings.animation_strength
        width = base_rect[2] - base_rect[0]
        height = base_rect[3] - base_rect[1]
        accent = self.settings.animation_accent_color
        afterimage_style = self._resolved_afterimage_style()

        if style == "none":
            return

        if style == "blink":
            if state.stepped >= 0.5:
                stripe_height = max(1.0, height * 0.22)
                draw.rectangle(
                    (base_rect[0] + 1.0, base_rect[1] + 1.0, base_rect[2] - 1.0, base_rect[1] + stripe_height),
                    fill=_with_alpha(self.settings.outline_color, 165),
                )
                draw.rounded_rectangle(
                    frame_rect,
                    radius=frame_radius,
                    outline=_with_alpha(accent, 135),
                    width=max(1, int(height * 0.1)),
                )
            return

        if style == "pop":
            inner_rect = _inset_rect(base_rect, width * 0.12, height * 0.18)
            pop_rect = _expand_rect(frame_rect, height * 0.04 * state.burst, height * 0.08 * state.burst)
            draw.rounded_rectangle(
                pop_rect,
                radius=self._rect_radius(pop_rect),
                outline=_with_alpha(accent, int(160 * (0.25 + state.burst * 0.75))),
                width=max(1, int(height * 0.11)),
            )
            if afterimage_style in {"outline", "both"}:
                draw.rounded_rectangle(
                    inner_rect,
                    radius=max(1.0, self._rect_radius(inner_rect) * 0.8),
                    outline=_with_alpha(self.settings.outline_color, int(115 + 70 * state.burst)),
                    width=max(1, int(height * 0.08)),
                )
            else:
                draw.rounded_rectangle(
                    inner_rect,
                    radius=max(1.0, self._rect_radius(inner_rect) * 0.8),
                    fill=_with_alpha(self.settings.outline_color, int(40 + 65 * state.burst)),
                )
            return

        if style == "scan":
            line_height = max(1.0, height * 0.14)
            steps = 5
            step_index = min(steps - 1, int(state.phase * steps))
            scan_y = _lerp(base_rect[1] + line_height, base_rect[3] - line_height, step_index / max(1, steps - 1))
            draw.rectangle(
                (base_rect[0] + 1.0, scan_y - line_height / 2.0, base_rect[2] - 1.0, scan_y + line_height / 2.0),
                fill=_with_alpha(accent, 120),
            )
            tail_y = max(base_rect[1] + line_height / 2.0, scan_y - line_height * 1.45)
            draw.rectangle(
                (
                    base_rect[0] + width * 0.08,
                    tail_y - line_height / 3.0,
                    base_rect[2] - width * 0.08,
                    tail_y + line_height / 3.0,
                ),
                fill=_with_alpha(self.settings.outline_color, 70),
            )
            draw.rounded_rectangle(frame_rect, radius=frame_radius, outline=_with_alpha(accent, 100), width=max(1, int(height * 0.08)))
            return

        if style == "jitter":
            draw.rounded_rectangle(
                frame_rect,
                radius=frame_radius,
                outline=_with_alpha(accent, 130),
                width=max(1, int(height * 0.1)),
            )
            slice_width = max(2.0, width * 0.1)
            slice_x = base_rect[0] + width * (0.15 + 0.2 * abs(state.jitter))
            draw.rectangle(
                (slice_x, base_rect[1] + 1.0, min(base_rect[2], slice_x + slice_width), base_rect[3] - 1.0),
                fill=_with_alpha(self.settings.outline_color, 78),
            )
            return

        if style == "arcade":
            frame_width = max(1, int(height * 0.12))
            draw.rectangle(
                frame_rect,
                outline=_with_alpha(accent, 130),
                width=frame_width,
            )
            pips = 3
            pip_width = max(2.0, width * 0.08)
            gap = max(2.0, width * 0.04)
            start_x = base_rect[0] + width * 0.12
            pip_y = base_rect[1] + height * 0.18
            for index in range(pips):
                if index <= int(state.stepped * (pips - 1) + 0.001):
                    x0 = start_x + index * (pip_width + gap)
                    draw.rectangle(
                        (x0, pip_y, x0 + pip_width, pip_y + height * 0.12),
                        fill=_with_alpha(self.settings.outline_color, 150),
                    )
            corner_size = max(2.0, height * 0.16)
            draw.rectangle(
                (base_rect[0], base_rect[1], base_rect[0] + corner_size, base_rect[1] + corner_size),
                fill=_with_alpha(accent, 95),
            )
            draw.rectangle(
                (base_rect[2] - corner_size, base_rect[3] - corner_size, base_rect[2], base_rect[3]),
                fill=_with_alpha(accent, 95),
            )
            return

        if style == "pulse":
            shine_height = height * (0.22 + 0.1 * state.wave)
            highlight_rect = _inset_rect((base_rect[0], base_rect[1], base_rect[2], base_rect[1] + shine_height), 1.0, 1.0)
            draw.rounded_rectangle(
                frame_rect,
                radius=frame_radius,
                outline=_with_alpha(accent, int(145 * (0.3 + state.wave * 0.7))),
                width=max(1, int(height * 0.1)),
            )
            draw.rounded_rectangle(
                highlight_rect,
                radius=max(1.0, base_radius * 0.6),
                fill=_with_alpha(self.settings.outline_color, int(70 + 60 * state.wave)),
            )
            return

        if style == "breathe":
            top_gloss = _inset_rect((base_rect[0], base_rect[1], base_rect[2], base_rect[1] + height * 0.34), 1.0, 1.0)
            bottom_glow = _inset_rect((base_rect[0], base_rect[3] - height * 0.28, base_rect[2], base_rect[3]), width * 0.06, 1.0)
            draw.rounded_rectangle(
                top_gloss,
                radius=max(1.0, base_radius * 0.65),
                fill=_with_alpha(self.settings.outline_color, int(65 + 50 * state.wave)),
            )
            draw.rounded_rectangle(
                bottom_glow,
                radius=max(1.0, base_radius * 0.5),
                outline=_with_alpha(accent, int(120 * (0.25 + state.wave * 0.75))),
                width=max(1, int(height * 0.08)),
            )
            draw.rounded_rectangle(frame_rect, radius=frame_radius, outline=_with_alpha(accent, 82), width=max(1, int(height * 0.08)))
            return

        if style == "shimmer":
            bar_width = max(5.0, width * 0.22)
            travel = _lerp(base_rect[0] - bar_width, base_rect[2] + bar_width, state.phase)
            shimmer = [
                (travel - bar_width, base_rect[3]),
                (travel, base_rect[1]),
                (travel + bar_width, base_rect[1]),
                (travel, base_rect[3]),
            ]
            draw.polygon(shimmer, fill=_with_alpha(accent, int(110 * _clamp(0.2 + strength))))
            draw.rounded_rectangle(frame_rect, radius=frame_radius, outline=_with_alpha(accent, 92), width=max(1, int(height * 0.08)))
            return

        if style == "bounce":
            draw.rounded_rectangle(
                frame_rect,
                radius=frame_radius,
                outline=_with_alpha(accent, 90),
                width=max(1, int(height * 0.12)),
            )
            shadow_rect = (
                frame_rect[0] + width * 0.08,
                frame_rect[3] + height * 0.08,
                frame_rect[2] - width * 0.08,
                frame_rect[3] + height * 0.18,
            )
            draw.rounded_rectangle(
                shadow_rect,
                radius=max(1.0, height * 0.12),
                fill=_with_alpha(accent, 36),
            )
            return

        if style == "expand":
            draw.rounded_rectangle(
                frame_rect,
                radius=frame_radius,
                outline=_with_alpha(accent, int(150 * (1.0 - state.wave * 0.55))),
                width=max(1, int(height * 0.12)),
            )
            inner_rect = _inset_rect(base_rect, width * 0.08, height * 0.1)
            draw.rounded_rectangle(
                inner_rect,
                radius=max(1.0, self._rect_radius(inner_rect) * 0.75),
                outline=_with_alpha(self.settings.outline_color, 85),
                width=max(1, int(height * 0.08)),
            )
            return

        if style == "flicker":
            alpha = int(70 + 120 * state.flicker)
            slice_height = max(2.0, height * 0.18)
            for index in range(3):
                band_y = _lerp(base_rect[1] + slice_height, base_rect[3] - slice_height, ((state.saw + index * 0.23) % 1.0))
                draw.rectangle(
                    (
                        base_rect[0] + width * 0.05,
                        band_y - slice_height / 2.0,
                        base_rect[2] - width * 0.05,
                        band_y + slice_height / 2.0,
                    ),
                    fill=_with_alpha(accent, max(0, alpha - index * 28)),
                )
            draw.rounded_rectangle(frame_rect, radius=frame_radius, outline=_with_alpha(accent, 92), width=max(1, int(height * 0.08)))
            return

        if style == "wave":
            stripe_count = 3
            for index in range(stripe_count):
                offset = (state.phase + index / stripe_count) % 1.0
                stripe_y = _lerp(base_rect[1] + 2.0, base_rect[3] - 2.0, offset)
                wobble = width * 0.06 * math.sin((offset + state.phase) * math.tau)
                draw.line(
                    (base_rect[0] + 2.0 + wobble, stripe_y, base_rect[2] - 2.0 - wobble, stripe_y),
                    fill=_with_alpha(accent, 95),
                    width=max(1, int(height * 0.08)),
                )
            draw.rounded_rectangle(frame_rect, radius=frame_radius, outline=_with_alpha(accent, 88), width=max(1, int(height * 0.08)))

    def _rect_radius(self, rect: tuple[float, float, float, float]) -> float:
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        corner_style = self.settings.corner_style
        if corner_style == "square":
            return 0.0
        if corner_style == "capsule":
            return max(1.0, min(height, width) * 0.49)
        return max(1.0, min(height, width) * 0.24)

    def _scaled_note_rect(
        self,
        rect: tuple[float, float, float, float],
        min_width: float,
    ) -> tuple[float, float, float, float]:
        scaled = _scale_rect(
            rect,
            max(0.25, self.settings.note_length_scale),
            max(0.25, self.settings.note_height_scale),
        )
        width = scaled[2] - scaled[0]
        if width >= min_width:
            return scaled

        center_x = (scaled[0] + scaled[2]) / 2.0
        return (center_x - min_width / 2.0, scaled[1], center_x + min_width / 2.0, scaled[3])

    def _outline_width(
        self,
        rect: tuple[float, float, float, float],
        base_ratio: float,
        scale: float,
    ) -> int:
        if scale <= 0.0:
            return 0
        return max(1, int((rect[3] - rect[1]) * base_ratio * scale))

    def _build_measure_segments(self, project: MidiProject) -> list[list[_VisibleSegment]]:
        segments_by_measure: list[list[_VisibleSegment]] = [[] for _ in project.measures]
        measure_starts = [measure.start_beat for measure in project.measures]
        epsilon = 1e-9

        for note in project.notes:
            measure_index = bisect_right(measure_starts, note.start_beat) - 1
            if measure_index < 0:
                measure_index = 0

            while measure_index < len(project.measures):
                measure = project.measures[measure_index]
                if note.end_beat <= measure.start_beat + epsilon:
                    break
                if note.start_beat >= measure.end_beat - epsilon:
                    measure_index += 1
                    continue

                overlap_start = max(note.start_beat, measure.start_beat)
                overlap_end = min(note.end_beat, measure.end_beat)
                start_ratio = (overlap_start - measure.start_beat) / max(measure.length_beats, epsilon)
                end_ratio = (overlap_end - measure.start_beat) / max(measure.length_beats, epsilon)

                segments_by_measure[measure.index].append(
                    _VisibleSegment(
                        note=note.note,
                        segment_start_beat=overlap_start,
                        segment_end_beat=overlap_end,
                        start_ratio=max(0.0, min(1.0, start_ratio)),
                        end_ratio=max(0.0, min(1.0, end_ratio)),
                        note_start_beat=note.start_beat,
                        note_end_beat=note.end_beat,
                        note_start_sec=note.start_sec,
                        note_end_sec=note.end_sec,
                    )
                )

                if note.end_beat <= measure.end_beat + epsilon:
                    break
                measure_index += 1

        for measure_segments in segments_by_measure:
            measure_segments.sort(key=lambda segment: (segment.note, segment.start_ratio, segment.end_ratio))

        return segments_by_measure


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * _clamp(amount)


def _expand_rect(rect: tuple[float, float, float, float], expand_x: float, expand_y: float) -> tuple[float, float, float, float]:
    return (
        rect[0] - expand_x,
        rect[1] - expand_y,
        rect[2] + expand_x,
        rect[3] + expand_y,
    )


def _offset_rect(rect: tuple[float, float, float, float], offset_x: float, offset_y: float) -> tuple[float, float, float, float]:
    return (
        rect[0] + offset_x,
        rect[1] + offset_y,
        rect[2] + offset_x,
        rect[3] + offset_y,
    )


def _normalize_rect(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = rect
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _scale_rect(rect: tuple[float, float, float, float], scale_x: float, scale_y: float) -> tuple[float, float, float, float]:
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    return _expand_rect(rect, width * (scale_x - 1.0) / 2.0, height * (scale_y - 1.0) / 2.0)


def _inset_rect(rect: tuple[float, float, float, float], inset_x: float, inset_y: float) -> tuple[float, float, float, float]:
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    clamped_x = min(max(0.0, inset_x), max(0.0, (width - 1.0) / 2.0))
    clamped_y = min(max(0.0, inset_y), max(0.0, (height - 1.0) / 2.0))
    return (
        rect[0] + clamped_x,
        rect[1] + clamped_y,
        rect[2] - clamped_x,
        rect[3] - clamped_y,
    )


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) != 6:
        raise ValueError(f"Unsupported color value: {color}")
    return tuple(int(value[index : index + 2], 16) for index in range(0, 6, 2))


def _with_alpha(color: str, alpha: int) -> tuple[int, int, int, int]:
    red, green, blue = _hex_to_rgb(color)
    return red, green, blue, max(0, min(255, int(alpha)))


def _mix_colors(color_a: str, color_b: str, amount: float, alpha: int = 255) -> tuple[int, int, int, int]:
    red_a, green_a, blue_a = _hex_to_rgb(color_a)
    red_b, green_b, blue_b = _hex_to_rgb(color_b)
    ratio = _clamp(amount)
    red = int(red_a + (red_b - red_a) * ratio)
    green = int(green_a + (green_b - green_a) * ratio)
    blue = int(blue_a + (blue_b - blue_a) * ratio)
    return red, green, blue, alpha


def _scale_image_alpha(image: Image.Image, factor: float) -> Image.Image:
    scaled = image.copy()
    alpha = scaled.getchannel("A").point(lambda value: int(value * factor))
    scaled.putalpha(alpha)
    return scaled
