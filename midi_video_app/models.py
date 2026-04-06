from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


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
    glow_style: str = "soft"
    animation_style: str = "pulse"
    glow_strength: float = 0.65
    animation_strength: float = 0.6
    animation_speed: float = 1.0


@dataclass(frozen=True, slots=True)
class ThemePreset:
    name: str
    settings: RenderSettings


GLOW_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "なし"),
    ("soft", "ソフト"),
    ("neon", "ネオン"),
    ("aura", "オーラ"),
    ("outline", "輪郭"),
    ("shadow", "シャドウ"),
    ("prism", "プリズム"),
)

ANIMATION_STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "なし"),
    ("pulse", "パルス"),
    ("breathe", "ブレス"),
    ("shimmer", "シマー"),
    ("bounce", "バウンス"),
    ("expand", "エクスパンド"),
    ("flicker", "フリッカー"),
    ("wave", "ウェーブ"),
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
            glow_style="soft",
            animation_style="pulse",
            glow_strength=0.65,
            animation_strength=0.55,
            animation_speed=1.0,
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
            glow_style="neon",
            animation_style="shimmer",
            glow_strength=0.8,
            animation_strength=0.7,
            animation_speed=1.3,
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
            glow_style="aura",
            animation_style="breathe",
            glow_strength=0.9,
            animation_strength=0.6,
            animation_speed=0.9,
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
            glow_style="soft",
            animation_style="wave",
            glow_strength=0.7,
            animation_strength=0.75,
            animation_speed=1.15,
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
            glow_style="prism",
            animation_style="flicker",
            glow_strength=0.95,
            animation_strength=0.85,
            animation_speed=1.6,
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
            glow_style="outline",
            animation_style="expand",
            glow_strength=0.75,
            animation_strength=0.8,
            animation_speed=1.1,
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
