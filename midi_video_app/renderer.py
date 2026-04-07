from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

from .models import Measure, MidiProject, RenderSettings

try:
    import aggdraw
except ImportError:  # pragma: no cover - optional dependency
    aggdraw = None


@dataclass(slots=True)
class _VisibleSegment:
    note: int
    start_ratio: float
    end_ratio: float
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
        self._measure_segments = self._build_measure_segments(project)
        self._measure_render_cache: dict[
            tuple[int, int, int, tuple[object, ...]],
            tuple[Image.Image, tuple[_PreparedSegment, ...]],
        ] = {}

    def set_settings(self, settings: RenderSettings) -> None:
        self.settings = settings
        self._measure_render_cache.clear()

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
        settings = self.settings
        clamped_time = max(0.0, min(time_sec, max(self.project.duration_sec - 1e-6, 0.0)))
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
        return image.convert("RGB")

    def _get_prepared_measure(self, measure: Measure, width: int, height: int) -> tuple[Image.Image, tuple[_PreparedSegment, ...]]:
        cache_key = (measure.index, width, height, self._cache_signature())
        cached = self._measure_render_cache.get(cache_key)
        if cached is not None:
            return cached

        image = Image.new("RGBA", (width, height), _with_alpha(self.settings.background_color, 255))
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
            settings.idle_note_color,
            settings.outline_color,
            settings.corner_style,
            settings.note_length_scale,
            settings.note_height_scale,
            settings.horizontal_padding_ratio,
            settings.vertical_padding_ratio,
            settings.idle_outline_width,
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
                        start_ratio=max(0.0, min(1.0, start_ratio)),
                        end_ratio=max(0.0, min(1.0, end_ratio)),
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
