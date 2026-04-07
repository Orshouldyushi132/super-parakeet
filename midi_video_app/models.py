from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping


@dataclass(slots=True)
class NoteEvent:
    note: int
    velocity: int
    channel: int
    track: int
    start_tick: int
    end_tick: int
    start_beat: float
    end_beat: float
    start_sec: float
    end_sec: float


@dataclass(slots=True)
class Measure:
    index: int
    start_beat: float
    end_beat: float
    start_sec: float
    end_sec: float
    numerator: int
    denominator: int

    @property
    def length_beats(self) -> float:
        return self.end_beat - self.start_beat


@dataclass(slots=True)
class RenderSettings:
    background_color: str = "#000000"
    idle_note_color: str = "#2f2f2f"
    active_note_color: str = "#ffffff"
    glow_color: str = "#d9d9d9"
    animation_accent_color: str = "#7dd3fc"
    outline_color: str = "#ffffff"
    corner_style: str = "rounded"
    glow_style: str = "soft"
    animation_style: str = "pulse"
    afterimage_style: str = "auto"
    glow_strength: float = 0.65
    animation_strength: float = 0.6
    animation_speed: float = 1.0
    afterimage_strength: float = 0.55
    note_length_scale: float = 1.0
    note_height_scale: float = 1.0
    horizontal_padding_ratio: float = 0.045
    vertical_padding_ratio: float = 0.08
    idle_outline_width: float = 0.0
    active_outline_width: float = 1.0
    afterimage_outline_width: float = 1.0
    afterimage_duration_sec: float = 0.2
    afterimage_padding_scale: float = 1.0
    release_fade_style: str = "outline"
    release_fade_curve: str = "smooth"
    release_fade_duration_sec: float = 0.18


@dataclass(frozen=True, slots=True)
class ThemePreset:
    name: str
    settings: RenderSettings


CORNER_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("square", "四角"),
    ("rounded", "丸角"),
    ("capsule", "カプセル"),
)

GLOW_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "なし"),
    ("soft", "ソフト"),
    ("mist", "ぼんやり"),
    ("bloom", "ブルーム"),
    ("neon", "ネオン"),
    ("aura", "オーラ"),
    ("outline", "輪郭"),
    ("shadow", "シャドウ"),
    ("prism", "プリズム"),
)

ANIMATION_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "なし"),
    ("blink", "点滅"),
    ("pop", "ポップ"),
    ("scan", "走査線"),
    ("jitter", "ガタガタ"),
    ("arcade", "アーケード"),
    ("pulse", "パルス"),
    ("breathe", "ブレス"),
    ("shimmer", "シマー"),
    ("bounce", "バウンス"),
    ("expand", "エクスパンド"),
    ("flicker", "フリッカー"),
    ("wave", "ウェーブ"),
)

AFTERIMAGE_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("auto", "おまかせ"),
    ("none", "なし"),
    ("outline", "枠だけ"),
    ("fill", "塗りだけ"),
    ("both", "枠+塗り"),
)

RELEASE_FADE_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "なし"),
    ("outline", "枠だけ"),
    ("fill", "塗りだけ"),
    ("both", "枠+塗り"),
)

RELEASE_FADE_CURVE_CHOICES: tuple[tuple[str, str], ...] = (
    ("linear", "線形"),
    ("smooth", "なめらか"),
    ("sharp", "キレよく"),
)

DEFAULT_THEME_NAME = "モノクロフラッシュ"
CUSTOM_THEME_NAME = "カスタム"

THEME_PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset(
        name="モノクロフラッシュ",
        settings=RenderSettings(
            background_color="#000000",
            idle_note_color="#2f2f2f",
            active_note_color="#ffffff",
            glow_color="#d9d9d9",
            animation_accent_color="#7dd3fc",
            outline_color="#ffffff",
            corner_style="rounded",
            glow_style="bloom",
            animation_style="blink",
            afterimage_style="outline",
            glow_strength=0.8,
            animation_strength=0.65,
            animation_speed=1.15,
            afterimage_strength=0.42,
        ),
    ),
    ThemePreset(
        name="アイスブルー",
        settings=RenderSettings(
            background_color="#07131d",
            idle_note_color="#223343",
            active_note_color="#effbff",
            glow_color="#93dcff",
            animation_accent_color="#37bdf8",
            outline_color="#e1f5ff",
            corner_style="rounded",
            glow_style="neon",
            animation_style="scan",
            afterimage_style="outline",
            glow_strength=0.8,
            animation_strength=0.65,
            animation_speed=1.1,
            afterimage_strength=0.48,
        ),
    ),
    ThemePreset(
        name="サンセット",
        settings=RenderSettings(
            background_color="#17070b",
            idle_note_color="#41242a",
            active_note_color="#fff1d8",
            glow_color="#ff9f6e",
            animation_accent_color="#ff4d8d",
            outline_color="#ffe7c2",
            corner_style="capsule",
            glow_style="mist",
            animation_style="pop",
            afterimage_style="both",
            glow_strength=0.9,
            animation_strength=0.75,
            animation_speed=0.9,
            afterimage_strength=0.74,
        ),
    ),
    ThemePreset(
        name="エメラルド",
        settings=RenderSettings(
            background_color="#05110c",
            idle_note_color="#1d3329",
            active_note_color="#e9fff3",
            glow_color="#6ee7b7",
            animation_accent_color="#34d399",
            outline_color="#d7ffea",
            corner_style="rounded",
            glow_style="soft",
            animation_style="arcade",
            afterimage_style="outline",
            glow_strength=0.75,
            animation_strength=0.7,
            animation_speed=1.0,
            afterimage_strength=0.52,
        ),
    ),
    ThemePreset(
        name="マゼンタネオン",
        settings=RenderSettings(
            background_color="#120613",
            idle_note_color="#39203d",
            active_note_color="#fff3ff",
            glow_color="#ff74dd",
            animation_accent_color="#9b8cff",
            outline_color="#ffe0ff",
            corner_style="square",
            glow_style="prism",
            animation_style="jitter",
            afterimage_style="outline",
            glow_strength=0.95,
            animation_strength=0.85,
            animation_speed=1.6,
            afterimage_strength=0.62,
        ),
    ),
    ThemePreset(
        name="ゴールドスパーク",
        settings=RenderSettings(
            background_color="#161108",
            idle_note_color="#40331e",
            active_note_color="#fff8e2",
            glow_color="#ffd166",
            animation_accent_color="#fca311",
            outline_color="#fff0bc",
            corner_style="square",
            glow_style="outline",
            animation_style="arcade",
            afterimage_style="outline",
            glow_strength=0.75,
            animation_strength=0.8,
            animation_speed=1.1,
            afterimage_strength=0.56,
        ),
    ),
    ThemePreset(
        name="アーケード",
        settings=RenderSettings(
            background_color="#060606",
            idle_note_color="#2a2a2a",
            active_note_color="#ffffff",
            glow_color="#9cf7ff",
            animation_accent_color="#00e5ff",
            outline_color="#ffffff",
            corner_style="square",
            glow_style="mist",
            animation_style="scan",
            afterimage_style="outline",
            glow_strength=1.0,
            animation_strength=0.9,
            animation_speed=1.2,
            afterimage_strength=0.55,
        ),
    ),
    ThemePreset(
        name="オーロラグラス",
        settings=RenderSettings(
            background_color="#081119",
            idle_note_color="#20313d",
            active_note_color="#f4fbff",
            glow_color="#85dcff",
            animation_accent_color="#8cf6d7",
            outline_color="#ffffff",
            corner_style="rounded",
            glow_style="bloom",
            animation_style="shimmer",
            afterimage_style="both",
            glow_strength=0.95,
            animation_strength=0.76,
            animation_speed=0.92,
            afterimage_strength=0.58,
        ),
    ),
    ThemePreset(
        name="シネマノワール",
        settings=RenderSettings(
            background_color="#020202",
            idle_note_color="#1c1c1c",
            active_note_color="#f6f0e3",
            glow_color="#c6a97a",
            animation_accent_color="#f0dcc0",
            outline_color="#fff7ec",
            corner_style="square",
            glow_style="shadow",
            animation_style="breathe",
            afterimage_style="outline",
            glow_strength=0.72,
            animation_strength=0.62,
            animation_speed=0.82,
            afterimage_strength=0.45,
        ),
    ),
    ThemePreset(
        name="シトラスポップ",
        settings=RenderSettings(
            background_color="#110a16",
            idle_note_color="#342540",
            active_note_color="#fff8ee",
            glow_color="#ffb44d",
            animation_accent_color="#77ffd4",
            outline_color="#fffdf7",
            corner_style="capsule",
            glow_style="prism",
            animation_style="pulse",
            afterimage_style="both",
            glow_strength=0.98,
            animation_strength=0.88,
            animation_speed=1.14,
            afterimage_strength=0.68,
        ),
    ),
)


def clone_render_settings(settings: RenderSettings) -> RenderSettings:
    return replace(settings)


def get_render_settings_for_theme(name: str) -> RenderSettings:
    for preset in THEME_PRESETS:
        if preset.name == name:
            return clone_render_settings(preset.settings)
    return RenderSettings()


def render_settings_to_dict(settings: RenderSettings) -> dict[str, Any]:
    return asdict(settings)


def render_settings_from_mapping(data: Mapping[str, Any] | None) -> RenderSettings:
    settings = RenderSettings()
    if not data:
        return settings

    choice_sets = {
        "corner_style": {value for value, _ in CORNER_STYLE_CHOICES},
        "glow_style": {value for value, _ in GLOW_STYLE_CHOICES},
        "animation_style": {value for value, _ in ANIMATION_STYLE_CHOICES},
        "afterimage_style": {value for value, _ in AFTERIMAGE_STYLE_CHOICES},
        "release_fade_style": {value for value, _ in RELEASE_FADE_STYLE_CHOICES},
        "release_fade_curve": {value for value, _ in RELEASE_FADE_CURVE_CHOICES},
    }
    float_ranges = {
        "glow_strength": (0.0, 1.5),
        "animation_strength": (0.0, 1.5),
        "animation_speed": (0.25, 3.0),
        "afterimage_strength": (0.0, 1.5),
        "note_length_scale": (0.25, 2.5),
        "note_height_scale": (0.25, 2.5),
        "horizontal_padding_ratio": (0.0, 0.18),
        "vertical_padding_ratio": (0.0, 0.2),
        "idle_outline_width": (0.0, 3.0),
        "active_outline_width": (0.0, 3.0),
        "afterimage_outline_width": (0.0, 3.0),
        "afterimage_duration_sec": (0.0, 2.0),
        "afterimage_padding_scale": (0.0, 3.0),
        "release_fade_duration_sec": (0.0, 2.0),
    }

    for field_name in render_settings_to_dict(settings):
        if field_name not in data:
            continue

        value = data[field_name]
        if field_name.endswith("_color"):
            if isinstance(value, str) and value.strip():
                setattr(settings, field_name, value.strip())
            continue

        if field_name in choice_sets:
            if isinstance(value, str) and value in choice_sets[field_name]:
                setattr(settings, field_name, value)
            continue

        if field_name in float_ranges:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            minimum, maximum = float_ranges[field_name]
            setattr(settings, field_name, max(minimum, min(maximum, numeric_value)))

    return settings


@dataclass(slots=True)
class MidiProject:
    source_path: Path
    ticks_per_beat: int
    notes: list[NoteEvent]
    measures: list[Measure]
    min_note: int
    max_note: int
    duration_sec: float

    @property
    def measure_count(self) -> int:
        return len(self.measures)
