from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import ImageTk

from .audio_engine import AudioMixSettings, create_mixed_audio_wav
from .exporter import (
    DEFAULT_EXPORT_FORMAT,
    DEFAULT_EXPORT_ORIENTATION,
    DEFAULT_EXPORT_RESOLUTION,
    EXPORT_FORMAT_CHOICES,
    EXPORT_FORMAT_H264,
    EXPORT_FORMAT_MOV,
    EXPORT_FORMAT_WEBM_VP9,
    EXPORT_ORIENTATION_CHOICES,
    EXPORT_FORMAT_PNG_SEQUENCE,
    EXPORT_RESOLUTION_PRESETS,
    ExportResolutionPreset,
    export_video,
    get_export_dimensions,
    get_export_resolution_preset,
)
from .midi_loader import load_midi_project
from .models import (
    AFTERIMAGE_STYLE_CHOICES,
    ANIMATION_STYLE_CHOICES,
    ATTACK_FADE_CURVE_CHOICES,
    ATTACK_FADE_STYLE_CHOICES,
    CORNER_STYLE_CHOICES,
    CUSTOM_THEME_NAME,
    DEFAULT_THEME_NAME,
    FONT_FAMILY_CHOICES,
    GLOW_STYLE_CHOICES,
    MAD_IMAGE_STYLE_CHOICES,
    RELEASE_FADE_CURVE_CHOICES,
    RELEASE_FADE_STYLE_CHOICES,
    VIEW_MODE_CHOICES,
    MidiProject,
    clone_render_settings,
    get_render_settings_for_theme,
)
from .preset_store import (
    delete_user_preset,
    get_render_settings_for_name,
    is_user_preset,
    save_user_preset,
    theme_name_choices,
)
from .renderer import ProjectRenderer

try:
    import winsound
except ImportError:  # pragma: no cover - Windows only
    winsound = None


PREVIEW_MAX_WIDTH = 960
PREVIEW_MAX_HEIGHT = 540
DEFAULT_FPS = 120

PATH_DISPLAY_FILENAME = "filename"
PATH_DISPLAY_FOLDER_AND_FILE = "folder_and_file"
PATH_DISPLAY_DIRECTORY = "directory"
PATH_DISPLAY_FULL = "full"
PATH_DISPLAY_HIDDEN = "hidden"
DEFAULT_PATH_DISPLAY = PATH_DISPLAY_FULL

PATH_DISPLAY_CHOICES: tuple[tuple[str, str], ...] = (
    (PATH_DISPLAY_FILENAME, "ファイル名だけ"),
    (PATH_DISPLAY_FOLDER_AND_FILE, "フォルダ名 + ファイル名"),
    (PATH_DISPLAY_DIRECTORY, "ディレクトリパス"),
    (PATH_DISPLAY_FULL, "フルパス"),
    (PATH_DISPLAY_HIDDEN, "非表示"),
)


class MidiVideoApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MIDI動画書き出しツール")
        self.root.geometry("1480x920")
        self.root.minsize(1240, 800)

        self.project: MidiProject | None = None
        self.render_settings = get_render_settings_for_theme(DEFAULT_THEME_NAME)
        self.renderer: ProjectRenderer | None = None
        self.current_time_sec = 0.0
        self.playing = False
        self.playback_started_at = 0.0
        self.playback_origin_sec = 0.0
        self._slider_updating = False
        self._preview_image: ImageTk.PhotoImage | None = None
        self._export_thread: threading.Thread | None = None
        self._updating_style_controls = False
        self._preview_audio_path: Path | None = None
        self.backing_audio_path: Path | None = None

        self._glow_value_to_label = {value: label for value, label in GLOW_STYLE_CHOICES}
        self._glow_label_to_value = {label: value for value, label in GLOW_STYLE_CHOICES}
        self._animation_value_to_label = {value: label for value, label in ANIMATION_STYLE_CHOICES}
        self._animation_label_to_value = {label: value for value, label in ANIMATION_STYLE_CHOICES}
        self._mad_image_style_value_to_label = {value: label for value, label in MAD_IMAGE_STYLE_CHOICES}
        self._mad_image_style_label_to_value = {label: value for value, label in MAD_IMAGE_STYLE_CHOICES}
        self._afterimage_value_to_label = {value: label for value, label in AFTERIMAGE_STYLE_CHOICES}
        self._afterimage_label_to_value = {label: value for value, label in AFTERIMAGE_STYLE_CHOICES}
        self._corner_value_to_label = {value: label for value, label in CORNER_STYLE_CHOICES}
        self._corner_label_to_value = {label: value for value, label in CORNER_STYLE_CHOICES}
        self._view_mode_value_to_label = {value: label for value, label in VIEW_MODE_CHOICES}
        self._view_mode_label_to_value = {label: value for value, label in VIEW_MODE_CHOICES}
        self._font_family_value_to_label = {value: label for value, label in FONT_FAMILY_CHOICES}
        self._font_family_label_to_value = {label: value for value, label in FONT_FAMILY_CHOICES}
        self._release_fade_value_to_label = {value: label for value, label in RELEASE_FADE_STYLE_CHOICES}
        self._release_fade_label_to_value = {label: value for value, label in RELEASE_FADE_STYLE_CHOICES}
        self._release_curve_value_to_label = {value: label for value, label in RELEASE_FADE_CURVE_CHOICES}
        self._release_curve_label_to_value = {label: value for value, label in RELEASE_FADE_CURVE_CHOICES}
        self._attack_fade_value_to_label = {value: label for value, label in ATTACK_FADE_STYLE_CHOICES}
        self._attack_fade_label_to_value = {label: value for value, label in ATTACK_FADE_STYLE_CHOICES}
        self._attack_curve_value_to_label = {value: label for value, label in ATTACK_FADE_CURVE_CHOICES}
        self._attack_curve_label_to_value = {label: value for value, label in ATTACK_FADE_CURVE_CHOICES}
        self._export_format_value_to_label = {value: label for value, label in EXPORT_FORMAT_CHOICES}
        self._export_format_label_to_value = {label: value for value, label in EXPORT_FORMAT_CHOICES}
        self._export_orientation_value_to_label = {value: label for value, label in EXPORT_ORIENTATION_CHOICES}
        self._export_orientation_label_to_value = {label: value for value, label in EXPORT_ORIENTATION_CHOICES}
        self._export_resolution_value_to_label = {preset.value: preset.label for preset in EXPORT_RESOLUTION_PRESETS}
        self._export_resolution_label_to_value = {preset.label: preset.value for preset in EXPORT_RESOLUTION_PRESETS}
        self._path_display_value_to_label = {value: label for value, label in PATH_DISPLAY_CHOICES}
        self._path_display_label_to_value = {label: value for value, label in PATH_DISPLAY_CHOICES}
        self._theme_names = theme_name_choices()

        self.file_label_var = tk.StringVar(value="MIDIファイルが読み込まれていません")
        self.status_var = tk.StringVar(value="MIDIファイルを選択してください。")
        self.time_var = tk.StringVar(value="00:00.000 / 00:00.000")
        self.measure_var = tk.StringVar(value="小節: -")
        self.fps_var = tk.StringVar(value=str(DEFAULT_FPS))
        self.export_format_var = tk.StringVar(value=self._export_format_value_to_label[DEFAULT_EXPORT_FORMAT])
        self.export_orientation_var = tk.StringVar(
            value=self._export_orientation_value_to_label[DEFAULT_EXPORT_ORIENTATION]
        )
        self.export_resolution_var = tk.StringVar(value=self._export_resolution_value_to_label[DEFAULT_EXPORT_RESOLUTION])
        self.export_dimension_var = tk.StringVar()
        self.export_hint_var = tk.StringVar()
        self.preset_name_var = tk.StringVar()
        self.path_display_var = tk.StringVar(value=self._path_display_value_to_label[DEFAULT_PATH_DISPLAY])

        self.theme_var = tk.StringVar(value=DEFAULT_THEME_NAME)
        self.view_mode_var = tk.StringVar(value=self._view_mode_value_to_label[self.render_settings.view_mode])
        self.font_family_var = tk.StringVar(
            value=self._font_family_value_to_label.get(
                self.render_settings.font_family,
                self._font_family_value_to_label["modern_light"],
            )
        )
        self.custom_font_path_var = tk.StringVar(value="カスタムフォント: 未選択")
        self.corner_style_var = tk.StringVar(value=self._corner_value_to_label[self.render_settings.corner_style])
        self.glow_style_var = tk.StringVar(value=self._glow_value_to_label[self.render_settings.glow_style])
        self.animation_style_var = tk.StringVar(value=self._animation_value_to_label[self.render_settings.animation_style])
        self.mad_image_style_var = tk.StringVar(
            value=self._mad_image_style_value_to_label[self.render_settings.mad_image_style]
        )
        self.afterimage_style_var = tk.StringVar(value=self._afterimage_value_to_label[self.render_settings.afterimage_style])
        self.release_fade_style_var = tk.StringVar(
            value=self._release_fade_value_to_label[self.render_settings.release_fade_style]
        )
        self.release_fade_curve_var = tk.StringVar(
            value=self._release_curve_value_to_label[self.render_settings.release_fade_curve]
        )
        self.attack_fade_style_var = tk.StringVar(
            value=self._attack_fade_value_to_label[self.render_settings.attack_fade_style]
        )
        self.attack_fade_curve_var = tk.StringVar(
            value=self._attack_curve_value_to_label[self.render_settings.attack_fade_curve]
        )
        self.visible_measure_count_var = tk.DoubleVar(value=float(self.render_settings.visible_measure_count))
        self.lyrics_space_scale_var = tk.DoubleVar(value=self.render_settings.lyrics_space_scale * 100.0)
        self.safe_area_enabled_var = tk.BooleanVar(value=self.render_settings.safe_area_enabled)
        self.safe_area_scale_var = tk.DoubleVar(value=self.render_settings.safe_area_scale * 100.0)
        self.canvas_border_enabled_var = tk.BooleanVar(value=self.render_settings.canvas_border_enabled)
        self.canvas_border_width_var = tk.DoubleVar(value=self.render_settings.canvas_border_width * 100.0)
        self.yatsume_enabled_var = tk.BooleanVar(value=self.render_settings.yatsume_enabled)
        self.yatsume_kick_note_var = tk.StringVar()
        self.yatsume_hihat_note_var = tk.StringVar()
        self.yatsume_clap_note_var = tk.StringVar()
        self.yatsume_cymbal_note_var = tk.StringVar()
        self.yatsume_assign_role_var = tk.StringVar(value="kick")
        self.yatsume_size_var = tk.DoubleVar(value=self.render_settings.yatsume_size * 100.0)
        self.yatsume_duration_var = tk.DoubleVar(value=self.render_settings.yatsume_duration_sec * 100.0)
        self.yatsume_outline_width_var = tk.DoubleVar(value=self.render_settings.yatsume_outline_width * 100.0)
        self.yatsume_animation_speed_var = tk.DoubleVar(value=self.render_settings.yatsume_animation_speed * 100.0)
        self.yatsume_position_x_var = tk.DoubleVar(value=self.render_settings.yatsume_position_x * 100.0)
        self.yatsume_position_y_var = tk.DoubleVar(value=self.render_settings.yatsume_position_y * 100.0)
        self.yatsume_seek_var = tk.DoubleVar(value=0.0)
        self.show_midi_notes_var = tk.BooleanVar(value=self.render_settings.show_midi_notes)
        self.mad_image_enabled_var = tk.BooleanVar(value=self.render_settings.mad_image_enabled)
        self.mad_image_alternate_flip_var = tk.BooleanVar(value=self.render_settings.mad_image_alternate_flip)
        self.mad_image_size_var = tk.DoubleVar(value=self.render_settings.mad_image_size * 100.0)
        self.mad_image_duration_var = tk.DoubleVar(value=self.render_settings.mad_image_duration_sec * 100.0)
        self.mad_image_opacity_var = tk.DoubleVar(value=self.render_settings.mad_image_opacity * 100.0)
        self.mad_image_position_x_var = tk.DoubleVar(value=self.render_settings.mad_image_position_x * 100.0)
        self.mad_image_position_y_var = tk.DoubleVar(value=self.render_settings.mad_image_position_y * 100.0)
        self.transparent_background_var = tk.BooleanVar(value=self.render_settings.transparent_background)
        self.fit_to_visible_note_range_var = tk.BooleanVar(value=self.render_settings.fit_to_visible_note_range)
        self.hide_future_notes_var = tk.BooleanVar(value=self.render_settings.hide_future_notes)
        self.show_time_overlay_var = tk.BooleanVar(value=self.render_settings.show_time_overlay)
        self.show_measure_overlay_var = tk.BooleanVar(value=self.render_settings.show_measure_overlay)
        self.show_stats_overlay_var = tk.BooleanVar(value=self.render_settings.show_stats_overlay)
        self.show_chord_overlay_var = tk.BooleanVar(value=self.render_settings.show_chord_overlay)
        self.bold_chord_text_var = tk.BooleanVar(value=self.render_settings.bold_chord_text)
        self.show_playhead_var = tk.BooleanVar(value=self.render_settings.show_playhead)
        self.glow_strength_var = tk.DoubleVar(value=self.render_settings.glow_strength * 100.0)
        self.animation_strength_var = tk.DoubleVar(value=self.render_settings.animation_strength * 100.0)
        self.animation_speed_var = tk.DoubleVar(value=self.render_settings.animation_speed * 100.0)
        self.afterimage_strength_var = tk.DoubleVar(value=self.render_settings.afterimage_strength * 100.0)
        self.note_length_scale_var = tk.DoubleVar(value=self.render_settings.note_length_scale * 100.0)
        self.note_height_scale_var = tk.DoubleVar(value=self.render_settings.note_height_scale * 100.0)
        self.horizontal_padding_var = tk.DoubleVar(value=self.render_settings.horizontal_padding_ratio * 100.0)
        self.vertical_padding_var = tk.DoubleVar(value=self.render_settings.vertical_padding_ratio * 100.0)
        self.idle_outline_width_var = tk.DoubleVar(value=self.render_settings.idle_outline_width * 100.0)
        self.active_outline_width_var = tk.DoubleVar(value=self.render_settings.active_outline_width * 100.0)
        self.afterimage_outline_width_var = tk.DoubleVar(value=self.render_settings.afterimage_outline_width * 100.0)
        self.afterimage_duration_var = tk.DoubleVar(value=self.render_settings.afterimage_duration_sec * 100.0)
        self.afterimage_padding_var = tk.DoubleVar(value=self.render_settings.afterimage_padding_scale * 100.0)
        self.release_fade_duration_var = tk.DoubleVar(value=self.render_settings.release_fade_duration_sec * 100.0)
        self.attack_fade_duration_var = tk.DoubleVar(value=self.render_settings.attack_fade_duration_sec * 100.0)
        self.enable_midi_audio_var = tk.BooleanVar(value=True)
        self.loop_backing_audio_var = tk.BooleanVar(value=False)
        self.midi_audio_volume_var = tk.DoubleVar(value=70.0)
        self.backing_audio_volume_var = tk.DoubleVar(value=85.0)
        self.glow_strength_text_var = tk.StringVar()
        self.animation_strength_text_var = tk.StringVar()
        self.animation_speed_text_var = tk.StringVar()
        self.afterimage_strength_text_var = tk.StringVar()
        self.note_length_scale_text_var = tk.StringVar()
        self.note_height_scale_text_var = tk.StringVar()
        self.lyrics_space_scale_text_var = tk.StringVar()
        self.safe_area_scale_text_var = tk.StringVar()
        self.canvas_border_width_text_var = tk.StringVar()
        self.yatsume_size_text_var = tk.StringVar()
        self.yatsume_duration_text_var = tk.StringVar()
        self.yatsume_outline_width_text_var = tk.StringVar()
        self.yatsume_animation_speed_text_var = tk.StringVar()
        self.yatsume_position_x_text_var = tk.StringVar()
        self.yatsume_position_y_text_var = tk.StringVar()
        self.yatsume_seek_time_var = tk.StringVar(value="00:00.000 / 00:00.000")
        self.mad_image_size_text_var = tk.StringVar()
        self.mad_image_duration_text_var = tk.StringVar()
        self.mad_image_opacity_text_var = tk.StringVar()
        self.mad_image_position_x_text_var = tk.StringVar()
        self.mad_image_position_y_text_var = tk.StringVar()
        self.horizontal_padding_text_var = tk.StringVar()
        self.vertical_padding_text_var = tk.StringVar()
        self.idle_outline_width_text_var = tk.StringVar()
        self.active_outline_width_text_var = tk.StringVar()
        self.afterimage_outline_width_text_var = tk.StringVar()
        self.afterimage_duration_text_var = tk.StringVar()
        self.afterimage_padding_text_var = tk.StringVar()
        self.release_fade_duration_text_var = tk.StringVar()
        self.attack_fade_duration_text_var = tk.StringVar()
        self.visible_measure_count_text_var = tk.StringVar()
        self.midi_audio_volume_text_var = tk.StringVar()
        self.backing_audio_volume_text_var = tk.StringVar()
        self.backing_audio_path_var = tk.StringVar(value="追加の音声ファイル: なし")
        self.mad_image_path_var = tk.StringVar(value="音MAD画像: なし")

        self._color_labels = {
            "background_color": "背景色",
            "idle_note_color": "通常ノーツ色",
            "active_note_color": "発音中ノーツ色",
            "glow_color": "発光色",
            "animation_accent_color": "アニメ色",
            "outline_color": "輪郭色",
            "text_color": "文字色",
            "canvas_border_color": "動画範囲の枠色",
        }
        self._yatsume_note_label_to_value: dict[str, int] = {}
        self._yatsume_note_value_to_label: dict[int, str] = {}
        self._yatsume_piano_rows: list[tuple[float, float, int]] = []
        self._yatsume_roll_left = 0.0
        self._yatsume_roll_right = 0.0
        self._yatsume_roll_top = 0.0
        self._yatsume_roll_bottom = 0.0
        self._yatsume_note_var_by_role: dict[str, tk.StringVar] = {
            "kick": self.yatsume_kick_note_var,
            "hihat": self.yatsume_hihat_note_var,
            "clap": self.yatsume_clap_note_var,
            "cymbal": self.yatsume_cymbal_note_var,
        }
        self._yatsume_field_by_role: dict[str, str] = {
            "kick": "yatsume_kick_note",
            "hihat": "yatsume_hihat_note",
            "clap": "yatsume_clap_note",
            "cymbal": "yatsume_cymbal_note",
        }
        self._color_labels["yatsume_outline_color"] = "ヤツメ穴の枠色"
        self._color_labels["yatsume_fill_color"] = "ヤツメ穴の内側色"
        self._color_value_vars: dict[str, tk.StringVar] = {}
        self._color_swatches: dict[str, tk.Label] = {}

        self._configure_styles()
        self._build_ui()
        self._sync_style_controls_from_settings(selected_theme=DEFAULT_THEME_NAME)
        self._schedule_playback_tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        bg = "#081018"
        panel = "#101822"
        panel_soft = "#16202c"
        line = "#263446"
        text = "#f5f7fb"
        muted = "#9eb0c6"
        accent = "#8cf6d7"
        accent_soft = "#7dd3fc"

        self.root.configure(background=bg)
        style.configure(".", background=bg, foreground=text, fieldbackground=panel_soft)
        style.configure("TFrame", background=bg)
        style.configure("Surface.TFrame", background=panel)
        style.configure("Card.TFrame", background=panel_soft)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Muted.TLabel", background=bg, foreground=muted)
        style.configure("Hero.TLabel", background=bg, foreground=text, font=("Yu Gothic UI Semibold", 18))
        style.configure("TLabelframe", background=bg, foreground=text, bordercolor=line, relief="solid")
        style.configure("TLabelframe.Label", background=bg, foreground=text, font=("Yu Gothic UI Semibold", 10))
        style.configure("TButton", padding=(10, 7), background=panel_soft, foreground=text, bordercolor=line)
        style.map("TButton", background=[("active", "#1b2a38")], bordercolor=[("active", accent_soft)])
        style.configure("Accent.TButton", background=accent, foreground="#061018", bordercolor=accent, padding=(12, 8))
        style.map("Accent.TButton", background=[("active", "#b4fff1")], foreground=[("active", "#041018")])
        style.configure("TEntry", fieldbackground=panel_soft, foreground=text, insertcolor=text, bordercolor=line)
        style.configure("TCombobox", fieldbackground=panel_soft, foreground=text, arrowcolor=text, bordercolor=line)
        style.map("TCombobox", fieldbackground=[("readonly", panel_soft)], selectbackground=[("readonly", panel_soft)])
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 8), background=panel_soft, foreground=muted)
        style.map("TNotebook.Tab", background=[("selected", panel), ("active", panel_soft)], foreground=[("selected", text)])
        style.configure("Horizontal.TScale", background=bg, troughcolor=panel_soft)
        style.configure("TProgressbar", troughcolor=panel_soft, background=accent_soft, bordercolor=line)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="MIDI Motion Studio", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="見た目を整えながら、演奏ビューをそのまま動画や連番PNGに書き出せます。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(outer, style="Surface.TFrame", padding=14)
        controls.pack(fill="x")

        ttk.Button(controls, text="MIDIを開く", command=self.open_midi).pack(side="left")
        ttk.Button(controls, text="再生 / 一時停止", command=self.toggle_playback).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="停止", command=self.stop_playback).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="前の小節へ", command=lambda: self.jump_measure(-1)).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="次の小節へ", command=lambda: self.jump_measure(1)).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="書き出し", style="Accent.TButton", command=self.export_media).pack(side="left", padx=(16, 0))

        ttk.Label(
            controls,
            text="書き出し形式・縦横・解像度・FPS は右側の「書き出し」タブでまとめて変更できます。",
            style="Muted.TLabel",
        ).pack(side="right")

        meta = ttk.Frame(outer)
        meta.pack(fill="x", pady=(12, 8))
        ttk.Label(meta, textvariable=self.file_label_var).pack(side="left")
        ttk.Label(meta, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)

        preview_panel = ttk.LabelFrame(content, text="プレビュー", padding=8)
        preview_panel.pack(side="left", fill="both", expand=True)

        self.preview_label = tk.Label(preview_panel, anchor="center", bg="#020406", relief="flat")
        self.preview_label.pack(fill="both", expand=True)

        settings_panel = ttk.LabelFrame(content, text="見た目設定", padding=12)
        settings_panel.pack(side="right", fill="both", padx=(16, 0))
        settings_panel.columnconfigure(3, weight=1)

        self._build_settings_panel(settings_panel)

        timeline_frame = ttk.Frame(outer)
        timeline_frame.pack(fill="x", pady=(12, 0))

        self.timeline = ttk.Scale(timeline_frame, from_=0.0, to=1.0, orient="horizontal", command=self.on_timeline_changed)
        self.timeline.pack(fill="x")

        info = ttk.Frame(outer)
        info.pack(fill="x", pady=(12, 0))

        ttk.Label(info, textvariable=self.time_var).pack(side="left")
        ttk.Label(info, textvariable=self.measure_var).pack(side="left", padx=(20, 0))
        ttk.Label(info, text="初期設定は 4K / 横動画 / 120FPS です。", style="Muted.TLabel").pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill="x", pady=(12, 0))

    def _build_settings_panel(self, panel: ttk.LabelFrame) -> None:
        ttk.Label(
            panel,
            text="テーマを土台にしつつ、ノーツ寸法・残像時間・切り替えフェードまで細かく詰められます。書き出し設定は最後のタブから変更できます。",
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        notebook = ttk.Notebook(panel)
        notebook.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(12, 0))
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        basic_tab = ttk.Frame(notebook, padding=12)
        color_tab = ttk.Frame(notebook, padding=12)
        effect_tab = ttk.Frame(notebook, padding=12)
        mad_tab = ttk.Frame(notebook, padding=12)
        yatsume_tab = ttk.Frame(notebook, padding=12)
        detail_tab = ttk.Frame(notebook, padding=12)
        export_tab = ttk.Frame(notebook, padding=12)
        notebook.add(yatsume_tab, text="ヤツメ穴")

        notebook.add(basic_tab, text="基本")
        notebook.add(color_tab, text="色")
        notebook.add(effect_tab, text="演出")
        notebook.add(mad_tab, text="音MAD")
        notebook.add(detail_tab, text="詳細")
        notebook.add(export_tab, text="書き出し")

        self._build_basic_settings_tab(basic_tab)
        self._build_color_settings_tab(color_tab)
        self._build_effect_settings_tab(effect_tab)
        self._build_mad_settings_tab(mad_tab)
        self._build_yatsume_settings_tab(yatsume_tab)
        self._build_detail_settings_tab(detail_tab)
        self._build_export_settings_tab(export_tab)
        notebook.insert(4, yatsume_tab)

    def _build_basic_settings_tab(self, panel: ttk.Frame) -> None:
        row = 0
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=1)

        ttk.Label(panel, text="保存プリセット").grid(row=row, column=0, sticky="w")
        self.preset_name_entry = ttk.Entry(panel, textvariable=self.preset_name_var)
        self.preset_name_entry.grid(row=row, column=1, columnspan=3, sticky="ew")

        row += 1
        self.save_preset_button = ttk.Button(
            panel,
            text="現在設定を保存",
            style="Accent.TButton",
            command=self._save_current_preset,
        )
        self.save_preset_button.grid(
            row=row,
            column=1,
            sticky="ew",
            pady=(8, 0),
        )
        self.delete_preset_button = ttk.Button(panel, text="選択プリセットを削除", command=self._delete_selected_preset)
        self.delete_preset_button.grid(
            row=row,
            column=2,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )

        row += 1
        ttk.Label(
            panel,
            text="今の見た目を名前付きで保存して、あとからすぐ呼び戻せます。",
            style="Muted.TLabel",
            wraplength=320,
            justify="left",
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))

        row += 1
        ttk.Label(panel, text="テーマ").grid(row=row, column=0, sticky="w")
        self.theme_combo = ttk.Combobox(panel, state="readonly", values=self._theme_names, textvariable=self.theme_var, width=18)
        self.theme_combo.grid(row=row, column=1, columnspan=3, sticky="ew")
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_selected)

        row += 1
        ttk.Label(panel, text="角の形").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.corner_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in CORNER_STYLE_CHOICES],
            textvariable=self.corner_style_var,
            width=16,
        )
        self.corner_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.corner_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="表示モード").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.view_mode_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in VIEW_MODE_CHOICES],
            textvariable=self.view_mode_var,
            width=16,
        )
        self.view_mode_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.view_mode_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="文字フォント").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.font_family_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in FONT_FAMILY_CHOICES],
            textvariable=self.font_family_var,
            width=16,
        )
        self.font_family_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.font_family_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        font_file_frame = ttk.Frame(panel)
        font_file_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        font_file_frame.columnconfigure(0, weight=1)
        ttk.Label(font_file_frame, textvariable=self.custom_font_path_var, style="Muted.TLabel", wraplength=320, justify="left").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
        )
        ttk.Button(font_file_frame, text="フォントファイルを選択", command=self._choose_custom_font).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(6, 0),
        )
        ttk.Button(font_file_frame, text="カスタムフォントを解除", command=self._clear_custom_font).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(6, 0),
        )

        row += 1
        ttk.Label(panel, text="パス表示").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.path_display_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in PATH_DISPLAY_CHOICES],
            textvariable=self.path_display_var,
            width=16,
        )
        self.path_display_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.path_display_combo.bind("<<ComboboxSelected>>", self._on_path_display_changed)

        row += 1
        self._add_slider_control(
            panel,
            row,
            "表示する小節数",
            self.visible_measure_count_var,
            self.visible_measure_count_text_var,
            1,
            8,
            self._on_strength_changed,
        )

        row += 1
        self._add_slider_control(
            panel,
            row,
            "歌詞スペースの高さ",
            self.lyrics_space_scale_var,
            self.lyrics_space_scale_text_var,
            0,
            300,
            self._on_strength_changed,
        )

        row += 1
        ttk.Checkbutton(
            panel,
            text="縦動画セーフエリアを使う",
            variable=self.safe_area_enabled_var,
            command=self._on_toggle_changed,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))

        row += 1
        self._add_slider_control(
            panel,
            row,
            "セーフエリア余白",
            self.safe_area_scale_var,
            self.safe_area_scale_text_var,
            0,
            200,
            self._on_strength_changed,
        )

        row += 1
        ttk.Checkbutton(
            panel,
            text="動画範囲の枠を表示",
            variable=self.canvas_border_enabled_var,
            command=self._on_toggle_changed,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))

        row += 1
        self._add_slider_control(
            panel,
            row,
            "動画範囲の枠幅",
            self.canvas_border_width_var,
            self.canvas_border_width_text_var,
            0,
            500,
            self._on_strength_changed,
        )

        row += 1
        overlay_frame = ttk.Frame(panel)
        overlay_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        overlay_frame.columnconfigure(0, weight=1)
        overlay_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(overlay_frame, text="未再生ノーツを隠す", variable=self.hide_future_notes_var, command=self._on_toggle_changed).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(overlay_frame, text="再生バー", variable=self.show_playhead_var, command=self._on_toggle_changed).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(overlay_frame, text="時間とビート表示", variable=self.show_time_overlay_var, command=self._on_toggle_changed).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(overlay_frame, text="小節ガイド", variable=self.show_measure_overlay_var, command=self._on_toggle_changed).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(overlay_frame, text="統計表示", variable=self.show_stats_overlay_var, command=self._on_toggle_changed).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(overlay_frame, text="コード表示", variable=self.show_chord_overlay_var, command=self._on_toggle_changed).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(overlay_frame, text="コード名を太字", variable=self.bold_chord_text_var, command=self._on_toggle_changed).grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            overlay_frame,
            text="表示中の音域だけに自動フィット",
            variable=self.fit_to_visible_note_range_var,
            command=self._on_toggle_changed,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        row += 1
        ttk.Separator(panel).grid(row=row, column=0, columnspan=4, sticky="ew", pady=12)

        row += 1
        ttk.Label(panel, text="ノーツのサイズと余白").grid(row=row, column=0, columnspan=4, sticky="w")

        row += 1
        self._add_slider_control(
            panel,
            row,
            "ノーツの長さ",
            self.note_length_scale_var,
            self.note_length_scale_text_var,
            25,
            250,
            self._on_strength_changed,
        )
        row += 1
        self._add_slider_control(
            panel,
            row,
            "ノーツの高さ",
            self.note_height_scale_var,
            self.note_height_scale_text_var,
            25,
            250,
            self._on_strength_changed,
        )
        row += 1
        self._add_slider_control(
            panel,
            row,
            "左右の余白",
            self.horizontal_padding_var,
            self.horizontal_padding_text_var,
            0,
            18,
            self._on_strength_changed,
        )
        row += 1
        self._add_slider_control(
            panel,
            row,
            "上下の余白",
            self.vertical_padding_var,
            self.vertical_padding_text_var,
            0,
            20,
            self._on_strength_changed,
        )

    def _build_color_settings_tab(self, panel: ttk.Frame) -> None:
        row = 0
        panel.columnconfigure(1, weight=0)
        panel.columnconfigure(2, weight=0)
        panel.columnconfigure(3, weight=1)
        for field_name in (
            "background_color",
            "idle_note_color",
            "active_note_color",
            "glow_color",
            "animation_accent_color",
            "outline_color",
            "text_color",
            "canvas_border_color",
            "yatsume_outline_color",
            "yatsume_fill_color",
        ):
            self._add_color_control(panel, row, field_name)
            row += 1

    def _build_effect_settings_tab(self, panel: ttk.Frame) -> None:
        row = 0
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=1)

        ttk.Label(panel, text="光り方").grid(row=row, column=0, sticky="w")
        self.glow_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in GLOW_STYLE_CHOICES],
            textvariable=self.glow_style_var,
            width=16,
        )
        self.glow_combo.grid(row=row, column=1, columnspan=3, sticky="ew")
        self.glow_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="アニメーション").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.animation_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in ANIMATION_STYLE_CHOICES],
            textvariable=self.animation_style_var,
            width=16,
        )
        self.animation_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.animation_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="残像").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.afterimage_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in AFTERIMAGE_STYLE_CHOICES],
            textvariable=self.afterimage_style_var,
            width=16,
        )
        self.afterimage_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.afterimage_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="切り替えフェード").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.release_fade_style_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in RELEASE_FADE_STYLE_CHOICES],
            textvariable=self.release_fade_style_var,
            width=16,
        )
        self.release_fade_style_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.release_fade_style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="フェードカーブ").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.release_fade_curve_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in RELEASE_FADE_CURVE_CHOICES],
            textvariable=self.release_fade_curve_var,
            width=16,
        )
        self.release_fade_curve_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.release_fade_curve_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="フェードイン（攻撃）").grid(row=row, column=0, sticky="w", pady=(12, 0))

        row += 1
        ttk.Label(panel, text="スタイル").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.attack_fade_style_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in ATTACK_FADE_STYLE_CHOICES],
            textvariable=self.attack_fade_style_var,
            width=16,
        )
        self.attack_fade_style_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.attack_fade_style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        row += 1
        ttk.Label(panel, text="フェードカーブ").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.attack_fade_curve_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in ATTACK_FADE_CURVE_CHOICES],
            textvariable=self.attack_fade_curve_var,
            width=16,
        )
        self.attack_fade_curve_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.attack_fade_curve_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        for label, variable, text_variable, minimum, maximum in (
            ("発光の強さ", self.glow_strength_var, self.glow_strength_text_var, 0, 150),
            ("アニメの強さ", self.animation_strength_var, self.animation_strength_text_var, 0, 150),
            ("アニメ速度", self.animation_speed_var, self.animation_speed_text_var, 25, 300),
            ("残像の強さ", self.afterimage_strength_var, self.afterimage_strength_text_var, 0, 150),
            ("残像の時間", self.afterimage_duration_var, self.afterimage_duration_text_var, 0, 200),
            ("フェードアウト時間", self.release_fade_duration_var, self.release_fade_duration_text_var, 0, 200),
            ("フェードイン時間", self.attack_fade_duration_var, self.attack_fade_duration_text_var, 0, 200),
        ):
            row += 1
            self._add_slider_control(
                panel,
                row,
                label,
                variable,
                text_variable,
                minimum,
                maximum,
                self._on_strength_changed,
            )

    def _build_mad_settings_tab(self, panel: ttk.Frame) -> None:
        row = 0
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=1)

        ttk.Label(
            panel,
            text="MIDIノーツの開始タイミングに合わせて、1枚の画像素材を音MAD風に出現させます。",
            wraplength=320,
            justify="left",
        ).grid(row=row, column=0, columnspan=4, sticky="w")

        row += 1
        ttk.Checkbutton(
            panel,
            text="音MAD画像を使う",
            variable=self.mad_image_enabled_var,
            command=self._on_toggle_changed,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(
            panel,
            text="MIDIノーツを表示",
            variable=self.show_midi_notes_var,
            command=self._on_toggle_changed,
        ).grid(row=row, column=2, columnspan=2, sticky="w", pady=(10, 0))

        row += 1
        ttk.Label(panel, textvariable=self.mad_image_path_var, style="Muted.TLabel", wraplength=320, justify="left").grid(
            row=row,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(8, 0),
        )

        row += 1
        image_row = ttk.Frame(panel)
        image_row.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(image_row, text="画像ファイルを選ぶ", command=self._choose_mad_image).pack(side="left")
        ttk.Button(image_row, text="画像を外す", command=self._clear_mad_image).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            image_row,
            text="1ノーツごとに左右反転",
            variable=self.mad_image_alternate_flip_var,
            command=self._on_toggle_changed,
        ).pack(side="left", padx=(10, 0))

        row += 1
        ttk.Label(panel, text="登場アニメーション").grid(row=row, column=0, sticky="w", pady=(10, 0))
        self.mad_image_style_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in MAD_IMAGE_STYLE_CHOICES],
            textvariable=self.mad_image_style_var,
            width=16,
        )
        self.mad_image_style_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(10, 0))
        self.mad_image_style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        for label, variable, text_variable, minimum, maximum in (
            ("画像サイズ", self.mad_image_size_var, self.mad_image_size_text_var, 5, 200),
            ("表示時間", self.mad_image_duration_var, self.mad_image_duration_text_var, 3, 500),
            ("不透明度", self.mad_image_opacity_var, self.mad_image_opacity_text_var, 0, 100),
            ("横位置", self.mad_image_position_x_var, self.mad_image_position_x_text_var, 0, 100),
            ("縦位置", self.mad_image_position_y_var, self.mad_image_position_y_text_var, 0, 100),
        ):
            row += 1
            self._add_slider_control(
                panel,
                row,
                label,
                variable,
                text_variable,
                minimum,
                maximum,
                self._on_strength_changed,
            )

    def _build_yatsume_settings_tab(self, panel: ttk.Frame) -> None:
        row = 0
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=1)

        ttk.Label(
            panel,
            text="ドラムMIDIの発音に合わせて中央へ図形を重ねます。キック・ハイハット・クラップ・シンバルの担当キーは、下のピアノロールを見ながら感覚的に選べます。",
            wraplength=340,
            justify="left",
        ).grid(row=row, column=0, columnspan=4, sticky="w")

        row += 1
        ttk.Checkbutton(
            panel,
            text="ヤツメ穴を使う",
            variable=self.yatsume_enabled_var,
            command=self._on_toggle_changed,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(10, 0))

        note_rows = (
            ("キック", "kick", self.yatsume_kick_note_var),
            ("ハイハット", "hihat", self.yatsume_hihat_note_var),
            ("クラップ", "clap", self.yatsume_clap_note_var),
            ("シンバル", "cymbal", self.yatsume_cymbal_note_var),
        )
        self._yatsume_note_combos: dict[str, ttk.Combobox] = {}
        for role_label, role_key, variable in note_rows:
            row += 1
            ttk.Label(panel, text=f"{role_label}のキー").grid(row=row, column=0, sticky="w", pady=(8, 0))
            combo = ttk.Combobox(panel, state="readonly", textvariable=variable, width=24)
            combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=(8, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event, role=role_key: self._on_yatsume_note_selected(role))
            self._yatsume_note_combos[role_key] = combo

        row += 1
        row += 1
        ttk.Label(
            panel,
            text="上が高いキー、下が低いキーです。各パーツの担当キーは上のプルダウンで決めて、下のピアノロールはノート位置の確認とプレビュー移動に使います。",
            style="Muted.TLabel",
            wraplength=340,
            justify="left",
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(10, 0))

        row += 1
        self.yatsume_piano_roll = tk.Canvas(
            panel,
            width=360,
            height=230,
            background="#081018",
            highlightthickness=1,
            highlightbackground="#263446",
            bd=0,
        )
        self.yatsume_piano_roll.grid(row=row, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        panel.rowconfigure(row, weight=1)
        self.yatsume_piano_roll.bind("<Button-1>", self._on_yatsume_piano_roll_clicked)
        self.yatsume_piano_roll.bind("<B1-Motion>", self._on_yatsume_piano_roll_dragged)
        self.yatsume_piano_roll.bind("<Configure>", lambda _event: self._refresh_yatsume_piano_roll())

        row += 1
        seek_row = ttk.Frame(panel)
        seek_row.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        seek_row.columnconfigure(1, weight=1)
        ttk.Label(seek_row, text="プレビュー移動").grid(row=0, column=0, sticky="w")
        ttk.Label(seek_row, textvariable=self.yatsume_seek_time_var, style="Muted.TLabel").grid(row=0, column=2, sticky="e")
        self.yatsume_seek_scale = ttk.Scale(
            seek_row,
            from_=0.0,
            to=1.0,
            variable=self.yatsume_seek_var,
            orient="horizontal",
            command=self._on_yatsume_seek_changed,
        )
        self.yatsume_seek_scale.grid(row=0, column=1, sticky="ew", padx=(10, 10))

        for label, variable, text_variable, minimum, maximum in (
            ("図形サイズ", self.yatsume_size_var, self.yatsume_size_text_var, 5, 120),
            ("表示時間", self.yatsume_duration_var, self.yatsume_duration_text_var, 3, 300),
            ("枠の太さ", self.yatsume_outline_width_var, self.yatsume_outline_width_text_var, 10, 500),
        ):
            row += 1
            self._add_slider_control(
                panel,
                row,
                label,
                variable,
                text_variable,
                minimum,
                maximum,
                self._on_strength_changed,
            )

        row += 1
        self._add_slider_control(
            panel,
            row,
            "横位置",
            self.yatsume_position_x_var,
            self.yatsume_position_x_text_var,
            0,
            100,
            self._on_strength_changed,
        )

        row += 1
        self._add_slider_control(
            panel,
            row,
            "アニメ速度",
            self.yatsume_animation_speed_var,
            self.yatsume_animation_speed_text_var,
            20,
            400,
            self._on_strength_changed,
        )

        row += 1
        self._add_slider_control(
            panel,
            row,
            "縦位置",
            self.yatsume_position_y_var,
            self.yatsume_position_y_text_var,
            0,
            100,
            self._on_strength_changed,
        )

    def _build_detail_settings_tab(self, panel: ttk.Frame) -> None:
        row = 0
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=1)

        ttk.Label(
            panel,
            text="線幅や残像フレームの広がりを調整したいときに使います。",
            wraplength=320,
            justify="left",
        ).grid(row=row, column=0, columnspan=4, sticky="w")

        for label, variable, text_variable, minimum, maximum in (
            ("通常ノーツ枠", self.idle_outline_width_var, self.idle_outline_width_text_var, 0, 300),
            ("発音中ノーツ枠", self.active_outline_width_var, self.active_outline_width_text_var, 0, 300),
            ("残像の枠幅", self.afterimage_outline_width_var, self.afterimage_outline_width_text_var, 0, 300),
            ("残像フレームの広さ", self.afterimage_padding_var, self.afterimage_padding_text_var, 0, 300),
        ):
            row += 1
            self._add_slider_control(
                panel,
                row,
                label,
                variable,
                text_variable,
                minimum,
                maximum,
                self._on_strength_changed,
            )

        row += 1
        ttk.Button(panel, text="標準テーマに戻す", command=self._reset_to_default_theme).grid(
            row=row,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(14, 0),
        )

    def _build_export_settings_tab(self, panel: ttk.Frame) -> None:
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(3, weight=1)

        ttk.Label(
            panel,
            text="書き出しに使うファイル形式、縦横、解像度、FPS をここでまとめて切り替えられます。",
            wraplength=320,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(panel, text="出力ファイル").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.export_format_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in EXPORT_FORMAT_CHOICES],
            textvariable=self.export_format_var,
            width=18,
        )
        self.export_format_combo.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        self.export_format_combo.bind("<<ComboboxSelected>>", self._on_export_options_changed)

        ttk.Label(panel, text="動画の向き").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(12, 0))
        self.export_orientation_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[label for _, label in EXPORT_ORIENTATION_CHOICES],
            textvariable=self.export_orientation_var,
            width=12,
        )
        self.export_orientation_combo.grid(row=1, column=3, sticky="ew", pady=(12, 0))
        self.export_orientation_combo.bind("<<ComboboxSelected>>", self._on_export_options_changed)

        ttk.Label(panel, text="解像度").grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.export_resolution_combo = ttk.Combobox(
            panel,
            state="readonly",
            values=[preset.label for preset in EXPORT_RESOLUTION_PRESETS],
            textvariable=self.export_resolution_var,
            width=18,
        )
        self.export_resolution_combo.grid(row=2, column=1, sticky="ew", pady=(12, 0))
        self.export_resolution_combo.bind("<<ComboboxSelected>>", self._on_export_options_changed)

        ttk.Label(panel, text="FPS").grid(row=2, column=2, sticky="w", padx=(12, 0), pady=(12, 0))
        ttk.Entry(panel, width=8, textvariable=self.fps_var).grid(row=2, column=3, sticky="ew", pady=(12, 0))

        ttk.Label(panel, text="出力サイズ").grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Label(panel, textvariable=self.export_dimension_var).grid(row=3, column=1, sticky="w", pady=(12, 0))

        self.transparent_background_check = ttk.Checkbutton(
            panel,
            text="背景透過を使う",
            variable=self.transparent_background_var,
            command=self._on_toggle_changed,
        )
        self.transparent_background_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Separator(panel).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(14, 10))

        ttk.Label(panel, text="音声").grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(
            panel,
            text="MIDIデータから音を鳴らす",
            variable=self.enable_midi_audio_var,
            command=self._on_audio_option_changed,
        ).grid(row=6, column=1, columnspan=3, sticky="w")

        ttk.Label(panel, textvariable=self.backing_audio_path_var, style="Muted.TLabel", wraplength=320, justify="left").grid(
            row=7,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(10, 0),
        )

        audio_file_row = ttk.Frame(panel)
        audio_file_row.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(audio_file_row, text="音声ファイルを選ぶ", command=self._choose_backing_audio).pack(side="left")
        ttk.Button(audio_file_row, text="音声ファイルを外す", command=self._clear_backing_audio).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            audio_file_row,
            text="短い音声はループする",
            variable=self.loop_backing_audio_var,
            command=self._on_audio_option_changed,
        ).pack(side="left", padx=(12, 0))

        self._add_slider_control(
            panel,
            9,
            "MIDI音量",
            self.midi_audio_volume_var,
            self.midi_audio_volume_text_var,
            0,
            150,
            self._on_audio_option_changed,
        )
        self._add_slider_control(
            panel,
            10,
            "追加音声音量",
            self.backing_audio_volume_var,
            self.backing_audio_volume_text_var,
            0,
            150,
            self._on_audio_option_changed,
        )

        ttk.Label(panel, textvariable=self.export_hint_var, style="Muted.TLabel", wraplength=320, justify="left").grid(
            row=11,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(12, 0),
        )

    def _add_color_control(self, panel: ttk.LabelFrame, row: int, field_name: str) -> None:
        label = self._color_labels[field_name]
        value_var = tk.StringVar()
        self._color_value_vars[field_name] = value_var

        ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=3)

        swatch = tk.Label(panel, width=3, relief="groove", cursor="hand2")
        swatch.grid(row=row, column=1, sticky="w", padx=(8, 8))
        swatch.bind("<Button-1>", lambda _event, name=field_name: self._choose_color(name))
        self._color_swatches[field_name] = swatch

        ttk.Button(panel, text="変更", command=lambda name=field_name: self._choose_color(name)).grid(
            row=row,
            column=2,
            sticky="w",
        )
        ttk.Label(panel, textvariable=value_var).grid(row=row, column=3, sticky="w", padx=(8, 0))

    def _add_slider_control(
        self,
        panel: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.DoubleVar,
        text_variable: tk.StringVar,
        minimum: float,
        maximum: float,
        command,
    ) -> None:
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Scale(panel, from_=minimum, to=maximum, variable=variable, command=command).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        ttk.Label(panel, textvariable=text_variable).grid(row=row, column=3, sticky="w", padx=(8, 0), pady=(8, 0))

    def _refresh_theme_choices(self, selected_theme: str | None = None) -> None:
        self._theme_names = theme_name_choices()
        if hasattr(self, "theme_combo"):
            self.theme_combo.configure(values=self._theme_names)
        if selected_theme and selected_theme in self._theme_names:
            self.theme_var.set(selected_theme)
        elif self.theme_var.get() not in self._theme_names:
            self.theme_var.set(DEFAULT_THEME_NAME)
        self._update_preset_button_states()

    def _update_preset_button_states(self) -> None:
        if hasattr(self, "delete_preset_button"):
            if is_user_preset(self.theme_var.get()):
                self.delete_preset_button.state(["!disabled"])
            else:
                self.delete_preset_button.state(["disabled"])

    def _load_theme_settings(self, theme_name: str):
        if theme_name == CUSTOM_THEME_NAME:
            return None
        return get_render_settings_for_name(theme_name) or get_render_settings_for_theme(theme_name)

    def _save_current_preset(self) -> None:
        preset_name = self.preset_name_var.get().strip()
        if not preset_name:
            messagebox.showinfo("プリセット名を入力してください", "保存するプリセット名を入力してください。")
            return
        if is_user_preset(preset_name):
            overwrite = messagebox.askyesno("上書き確認", f"`{preset_name}` を上書きしますか？")
            if not overwrite:
                return
        try:
            saved_name = save_user_preset(preset_name, clone_render_settings(self.render_settings))
        except ValueError as error:
            messagebox.showerror("プリセットを保存できません", str(error))
            return

        self._refresh_theme_choices(saved_name)
        self.status_var.set(f"プリセット `{saved_name}` を保存しました。")
        self.theme_var.set(saved_name)
        self._update_preset_button_states()

    def _delete_selected_preset(self) -> None:
        theme_name = self.theme_var.get()
        if not is_user_preset(theme_name):
            messagebox.showinfo("削除できません", "保存済みユーザープリセットを選んだときだけ削除できます。")
            return
        should_delete = messagebox.askyesno("プリセット削除", f"`{theme_name}` を削除しますか？")
        if not should_delete:
            return
        if delete_user_preset(theme_name):
            self._refresh_theme_choices(DEFAULT_THEME_NAME)
            self.render_settings = get_render_settings_for_theme(DEFAULT_THEME_NAME)
            if self.renderer:
                self.renderer.set_settings(self.render_settings)
            self.preset_name_var.set("")
            self._sync_style_controls_from_settings(selected_theme=DEFAULT_THEME_NAME)
            self._refresh_preview_if_loaded()
            self.status_var.set(f"プリセット `{theme_name}` を削除しました。")
        self._update_preset_button_states()

    def open_midi(self) -> None:
        midi_path = filedialog.askopenfilename(
            title="MIDIファイルを選択",
            filetypes=[("MIDIファイル", "*.mid *.midi"), ("すべてのファイル", "*.*")],
        )
        if not midi_path:
            return

        self._stop_audio_preview()
        self.status_var.set("MIDIを読み込み中...")
        self.root.update_idletasks()

        try:
            self.project = load_midi_project(midi_path)
            self.renderer = ProjectRenderer(self.project, self.render_settings)
        except Exception as error:
            self.project = None
            self.renderer = None
            messagebox.showerror("MIDIの読み込みに失敗しました", str(error))
            self.status_var.set("MIDIの読み込みに失敗しました。")
            return

        self.current_time_sec = 0.0
        self.playing = False
        self.timeline.configure(to=max(self.project.duration_sec, 0.001))
        if hasattr(self, "yatsume_seek_scale"):
            self.yatsume_seek_scale.configure(to=max(self.project.duration_sec, 0.001))
        self._refresh_path_labels()
        self._refresh_yatsume_note_choices()
        self._sync_yatsume_note_controls_from_settings()
        self.status_var.set("MIDIを読み込みました。小節ごとの切り替え表示でプレビューできます。")
        self.progress.configure(value=0.0)
        self._refresh_preview()

    def toggle_playback(self) -> None:
        if not self.project:
            messagebox.showinfo("MIDIを開いてください", "再生する前にMIDIファイルを読み込んでください。")
            return

        if self.playing:
            self.playing = False
            self.playback_origin_sec = self.current_time_sec
            self._stop_audio_preview()
            self.status_var.set("再生を一時停止しました。")
            return

        if self.current_time_sec >= self.project.duration_sec:
            self.current_time_sec = 0.0

        self.playback_origin_sec = self.current_time_sec
        self._start_audio_preview()
        self.playing = True
        self.playback_started_at = time.perf_counter()
        self.status_var.set("再生中...")

    def stop_playback(self) -> None:
        self.playing = False
        self.current_time_sec = 0.0
        self.playback_origin_sec = 0.0
        self._stop_audio_preview()
        self.status_var.set("停止しました。")
        self._refresh_preview()

    def jump_measure(self, direction: int) -> None:
        if not self.project or not self.renderer:
            return

        current_measure = self.renderer.get_measure_for_time(self.current_time_sec)
        target_index = max(0, min(current_measure.index + direction, self.project.measure_count - 1))
        self.playing = False
        self._stop_audio_preview()
        self.current_time_sec = self.project.measures[target_index].start_sec
        self.playback_origin_sec = self.current_time_sec
        self.status_var.set(f"{target_index + 1}小節目へ移動しました。")
        self._refresh_preview()

    def export_mp4(self) -> None:
        self.export_media()

    def _selected_export_format(self) -> str:
        return self._export_format_label_to_value.get(self.export_format_var.get(), DEFAULT_EXPORT_FORMAT)

    def _selected_export_orientation(self) -> str:
        return self._export_orientation_label_to_value.get(
            self.export_orientation_var.get(),
            DEFAULT_EXPORT_ORIENTATION,
        )

    def _selected_export_resolution_preset(self) -> ExportResolutionPreset:
        value = self._export_resolution_label_to_value.get(
            self.export_resolution_var.get(),
            DEFAULT_EXPORT_RESOLUTION,
        )
        return get_export_resolution_preset(value)

    def _selected_export_dimensions(self) -> tuple[int, int]:
        preset = self._selected_export_resolution_preset()
        return get_export_dimensions(preset.value, self._selected_export_orientation())

    def _selected_path_display_mode(self) -> str:
        return self._path_display_label_to_value.get(self.path_display_var.get(), DEFAULT_PATH_DISPLAY)

    def _format_path_for_display(self, path: Path, *, hidden_text: str) -> str:
        mode = self._selected_path_display_mode()
        resolved_path = Path(path)
        if mode == PATH_DISPLAY_FILENAME:
            return resolved_path.name
        if mode == PATH_DISPLAY_FOLDER_AND_FILE:
            parent_name = resolved_path.parent.name
            return f"{parent_name}\\{resolved_path.name}" if parent_name else resolved_path.name
        if mode == PATH_DISPLAY_DIRECTORY:
            return str(resolved_path.parent)
        if mode == PATH_DISPLAY_HIDDEN:
            return hidden_text
        return str(resolved_path)

    def _refresh_path_labels(self) -> None:
        if self.project is None:
            self.file_label_var.set("MIDIファイルが読み込まれていません")
        else:
            midi_display = self._format_path_for_display(
                self.project.source_path,
                hidden_text="読み込み済み",
            )
            self.file_label_var.set(f"MIDIファイル: {midi_display}")

        if self.backing_audio_path is None:
            self.backing_audio_path_var.set("追加の音声ファイル: なし")
        else:
            audio_display = self._format_path_for_display(
                self.backing_audio_path,
                hidden_text="選択済み",
            )
            self.backing_audio_path_var.set(f"追加の音声ファイル: {audio_display}")
        self._refresh_mad_image_label()

    def _refresh_custom_font_label(self) -> None:
        font_path = getattr(self.render_settings, "custom_font_path", "")
        if not font_path:
            self.custom_font_path_var.set("カスタムフォント: 未選択")
            return

        font_display = self._format_path_for_display(
            Path(font_path),
            hidden_text="選択済み",
        )
        self.custom_font_path_var.set(f"カスタムフォント: {font_display}")

    def _refresh_mad_image_label(self) -> None:
        image_path = getattr(self.render_settings, "mad_image_path", "")
        if not image_path:
            self.mad_image_path_var.set("音MAD画像: なし")
            return

        image_display = self._format_path_for_display(
            Path(image_path),
            hidden_text="選択済み",
        )
        self.mad_image_path_var.set(f"音MAD画像: {image_display}")

    @staticmethod
    def _midi_note_name(note_number: int) -> str:
        note_names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        octave = note_number // 12 - 1
        return f"{note_names[note_number % 12]}{octave}"

    @staticmethod
    def _gm_drum_name(note_number: int) -> str:
        drum_names = {
            35: "Acoustic Bass Drum",
            36: "Bass Drum",
            37: "Side Stick",
            38: "Snare",
            39: "Hand Clap",
            40: "Electric Snare",
            41: "Low Floor Tom",
            42: "Closed Hi-Hat",
            43: "High Floor Tom",
            44: "Pedal Hi-Hat",
            45: "Low Tom",
            46: "Open Hi-Hat",
            47: "Low-Mid Tom",
            48: "Hi-Mid Tom",
            49: "Crash Cymbal",
            50: "High Tom",
            51: "Ride Cymbal",
            52: "Chinese Cymbal",
            53: "Ride Bell",
            55: "Splash Cymbal",
            57: "Crash Cymbal 2",
            59: "Ride Cymbal 2",
        }
        return drum_names.get(note_number, "Drum Note")

    def _drum_source_notes(self):
        if not self.project:
            return []
        drum_notes = [note for note in self.project.notes if note.channel == 9]
        return drum_notes if drum_notes else list(self.project.notes)

    def _format_yatsume_note_label(self, note_number: int, hit_count: int | None = None) -> str:
        suffix = f" / 発音{hit_count}回" if hit_count is not None else ""
        return f"{note_number:03d} | {self._midi_note_name(note_number)} | {self._gm_drum_name(note_number)}{suffix}"

    def _refresh_yatsume_note_choices(self) -> None:
        counts_by_note: dict[int, int] = {}
        for note in self._drum_source_notes():
            counts_by_note[note.note] = counts_by_note.get(note.note, 0) + 1

        candidate_notes = sorted(set(counts_by_note) | {36, 42, 39, 49})
        self._yatsume_note_label_to_value = {}
        self._yatsume_note_value_to_label = {}
        labels: list[str] = []
        for note_number in candidate_notes:
            label = self._format_yatsume_note_label(note_number, counts_by_note.get(note_number))
            labels.append(label)
            self._yatsume_note_label_to_value[label] = note_number
            self._yatsume_note_value_to_label[note_number] = label

        for combo in getattr(self, "_yatsume_note_combos", {}).values():
            combo.configure(values=labels)

    def _sync_yatsume_note_controls_from_settings(self) -> None:
        if not self._yatsume_note_value_to_label:
            self._refresh_yatsume_note_choices()

        for role, field_name in self._yatsume_field_by_role.items():
            note_number = int(getattr(self.render_settings, field_name))
            label = self._yatsume_note_value_to_label.get(note_number)
            if label is None:
                label = self._format_yatsume_note_label(note_number)
                self._yatsume_note_label_to_value[label] = note_number
                self._yatsume_note_value_to_label[note_number] = label
                combo = getattr(self, "_yatsume_note_combos", {}).get(role)
                if combo is not None:
                    values = list(combo.cget("values"))
                    if label not in values:
                        values.append(label)
                        combo.configure(values=values)
            self._yatsume_note_var_by_role[role].set(label)

    def _set_yatsume_role_note(self, role: str, note_number: int, *, refresh_preview: bool = True) -> None:
        field_name = self._yatsume_field_by_role[role]
        setattr(self.render_settings, field_name, int(note_number))
        label = self._yatsume_note_value_to_label.get(int(note_number), self._format_yatsume_note_label(int(note_number)))
        self._yatsume_note_var_by_role[role].set(label)
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_yatsume_piano_roll()
        if refresh_preview:
            self._refresh_preview_if_loaded()

    def _on_yatsume_note_selected(self, role: str) -> None:
        if self._updating_style_controls:
            return
        label = self._yatsume_note_var_by_role[role].get()
        note_number = self._yatsume_note_label_to_value.get(label)
        if note_number is None:
            return
        self._set_yatsume_role_note(role, note_number)

    def _seek_preview_to_time(self, time_sec: float) -> None:
        if not self.project:
            return
        self.current_time_sec = max(0.0, min(time_sec, self.project.duration_sec))
        self.playing = False
        self.playback_origin_sec = self.current_time_sec
        self._stop_audio_preview()
        self._refresh_preview()

    def _seek_preview_to_ratio(self, ratio: float) -> None:
        if not self.project:
            return
        self._seek_preview_to_time(self.project.duration_sec * max(0.0, min(1.0, ratio)))

    def _on_yatsume_seek_changed(self, raw_value: str) -> None:
        if self._slider_updating or not self.project:
            return
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return
        self._seek_preview_to_time(value)

    def _refresh_yatsume_piano_roll(self) -> None:
        if not hasattr(self, "yatsume_piano_roll"):
            return

        canvas = self.yatsume_piano_roll
        canvas.delete("all")
        width = max(320, int(canvas.winfo_width() or 360))
        height = max(170, int(canvas.winfo_height() or 230))
        self._yatsume_roll_left = 0.0
        self._yatsume_roll_right = 0.0
        self._yatsume_roll_top = 0.0
        self._yatsume_roll_bottom = 0.0

        if not self.project:
            canvas.create_text(
                width / 2.0,
                height / 2.0,
                text="MIDIを開くと、ここにドラムのピアノロールが表示されます。",
                fill="#9eb0c6",
                font=("Yu Gothic UI", 10),
            )
            return

        drum_notes = self._drum_source_notes()
        if not drum_notes:
            canvas.create_text(
                width / 2.0,
                height / 2.0,
                text="このMIDIには表示できるノーツがありません。",
                fill="#9eb0c6",
                font=("Yu Gothic UI", 10),
            )
            return

        notes_by_pitch: dict[int, list] = {}
        for note in drum_notes:
            notes_by_pitch.setdefault(note.note, []).append(note)
        ordered_notes = sorted(notes_by_pitch.keys(), reverse=True)
        label_width = 154
        top_padding = 20
        bottom_padding = 10
        roll_left = label_width + 10
        roll_right = width - 10
        roll_width = max(1, roll_right - roll_left)
        self._yatsume_roll_left = roll_left
        self._yatsume_roll_right = roll_right
        self._yatsume_roll_top = top_padding - 2
        self._yatsume_roll_bottom = height - bottom_padding
        row_height = max(14.0, min(32.0, (height - top_padding - bottom_padding) / max(1, len(ordered_notes))))
        role_colors = {
            "kick": "#ff9b72",
            "hihat": "#93c5fd",
            "clap": "#f9a8d4",
            "cymbal": "#fde68a",
        }
        role_note_numbers = {
            role: int(getattr(self.render_settings, field_name))
            for role, field_name in self._yatsume_field_by_role.items()
        }
        duration = max(self.project.duration_sec, 0.001)
        self._yatsume_piano_rows = []

        canvas.create_rectangle(0, 0, width, height, fill="#081018", outline="")
        canvas.create_text(
            10,
            6,
            anchor="nw",
            text="ピアノロール / クリックとドラッグでプレビュー移動",
            fill="#f5f7fb",
            font=("Yu Gothic UI Semibold", 10),
        )

        for row_index, note_number in enumerate(ordered_notes):
            y0 = top_padding + row_index * row_height
            y1 = y0 + row_height - 2
            assigned_roles = [role for role, mapped_note in role_note_numbers.items() if mapped_note == note_number]
            row_fill = "#101822"
            outline = "#1d2a38"
            if assigned_roles:
                row_fill = "#152232"
                outline = role_colors[assigned_roles[0]]
            canvas.create_rectangle(0, y0, width, y1, fill=row_fill, outline=outline)
            label_color = role_colors[assigned_roles[0]] if assigned_roles else "#d7dee8"
            canvas.create_text(
                10,
                (y0 + y1) / 2.0,
                anchor="w",
                text=self._format_yatsume_note_label(note_number, len(notes_by_pitch[note_number])),
                fill=label_color,
                font=("Yu Gothic UI", 9),
            )
            self._yatsume_piano_rows.append((y0, y1, note_number))

            for note in notes_by_pitch[note_number]:
                x0 = roll_left + (note.start_sec / duration) * roll_width
                note_duration = max(0.025, note.end_sec - note.start_sec)
                x1 = roll_left + min(1.0, (note.start_sec + note_duration) / duration) * roll_width
                if x1 - x0 < 2:
                    x1 = x0 + 2
                fill = "#49596c"
                if assigned_roles:
                    fill = role_colors[assigned_roles[0]]
                canvas.create_rectangle(x0, y0 + 3, x1, y1 - 3, fill=fill, outline="")

        current_x = roll_left + (max(0.0, min(self.current_time_sec, duration)) / duration) * roll_width
        canvas.create_line(current_x, top_padding - 2, current_x, height - bottom_padding, fill="#ffffff", width=1)
        canvas.create_rectangle(roll_left, top_padding - 2, roll_right, height - bottom_padding, outline="#2a3747", width=1)

    def _on_yatsume_piano_roll_clicked(self, event) -> None:
        if self._yatsume_roll_left <= event.x <= self._yatsume_roll_right:
            roll_width = max(1.0, self._yatsume_roll_right - self._yatsume_roll_left)
            self._seek_preview_to_ratio((event.x - self._yatsume_roll_left) / roll_width)
        return

    def _on_yatsume_piano_roll_dragged(self, event) -> None:
        if self._yatsume_roll_left <= event.x <= self._yatsume_roll_right:
            roll_width = max(1.0, self._yatsume_roll_right - self._yatsume_roll_left)
            self._seek_preview_to_ratio((event.x - self._yatsume_roll_left) / roll_width)

    def _get_preview_dimensions(self) -> tuple[int, int]:
        width, height = self._selected_export_dimensions()
        ratio = width / max(height, 1)
        max_ratio = PREVIEW_MAX_WIDTH / PREVIEW_MAX_HEIGHT
        if ratio >= max_ratio:
            width = PREVIEW_MAX_WIDTH
            height = max(1, int(round(width / ratio)))
        else:
            height = PREVIEW_MAX_HEIGHT
            width = max(1, int(round(height * ratio)))
        return width, height

    @staticmethod
    def _next_available_directory(parent: Path, base_name: str) -> Path:
        candidate = parent / base_name
        if not candidate.exists():
            return candidate
        suffix = 2
        while True:
            numbered = parent / f"{base_name}_{suffix}"
            if not numbered.exists():
                return numbered
            suffix += 1

    def _update_export_option_state(self) -> None:
        export_format = self._selected_export_format()
        width, height = self._selected_export_dimensions()
        allow_transparency = export_format in {EXPORT_FORMAT_MOV, EXPORT_FORMAT_WEBM_VP9, EXPORT_FORMAT_PNG_SEQUENCE}

        self.export_dimension_var.set(f"{width} x {height}")
        if export_format == EXPORT_FORMAT_H264:
            self.export_hint_var.set("H.264 は MP4 で書き出します。背景透過は使えませんが、MIDI音と追加音声は一緒に入れられます。")
        elif export_format == EXPORT_FORMAT_WEBM_VP9:
            self.export_hint_var.set("WebM VP9 は背景透過に対応した圧縮動画です。Windows では Edge / Chrome などで確認しやすい形式です。")
        elif export_format == EXPORT_FORMAT_MOV:
            self.export_hint_var.set("MOV は背景透過ありでも書き出せます。MIDI音や追加音声も一緒に書き出せる、編集向けの形式です。")
        else:
            self.export_hint_var.set("連番PNGは1フレームずつ保存し、音声がある場合は同じフォルダに WAV も出力します。背景透過にも対応します。")

        if allow_transparency:
            self.transparent_background_check.state(["!disabled"])
        else:
            self.transparent_background_check.state(["disabled"])
            if self.transparent_background_var.get():
                self.transparent_background_var.set(False)
                self.render_settings.transparent_background = False
                if self.renderer:
                    self.renderer.set_settings(self.render_settings)

    def _on_export_options_changed(self, _event=None) -> None:
        self._update_export_option_state()
        self._refresh_preview_if_loaded()

    def export_media(self) -> None:
        if not self.project or not self.renderer:
            messagebox.showinfo("MIDIを開いてください", "書き出す前にMIDIファイルを読み込んでください。")
            return

        if self._export_thread and self._export_thread.is_alive():
            messagebox.showinfo("書き出し中です", "すでに書き出し中です。完了してからもう一度お試しください。")
            return

        try:
            fps = max(1, int(self.fps_var.get()))
        except ValueError:
            messagebox.showerror("FPSが不正です", "FPSには1以上の整数を入力してください。")
            return

        export_format = self._selected_export_format()
        resolution = self._selected_export_resolution_preset()
        orientation = self._selected_export_orientation()
        width, height = self._selected_export_dimensions()
        audio_mix_settings = self._current_audio_mix_settings()
        output_path: str | Path

        if export_format == EXPORT_FORMAT_PNG_SEQUENCE:
            parent_directory = filedialog.askdirectory(title="連番PNGの保存先フォルダを選択")
            if not parent_directory:
                return
            output_path = self._next_available_directory(
                Path(parent_directory),
                f"{self.project.source_path.stem}_連番PNG",
            )
        else:
            if export_format == EXPORT_FORMAT_MOV:
                extension = ".mov"
                format_label = "MOV"
            elif export_format == EXPORT_FORMAT_WEBM_VP9:
                extension = ".webm"
                format_label = "WebM VP9"
            else:
                extension = ".mp4"
                format_label = "H.264 MP4"
            default_name = f"{self.project.source_path.stem}_{resolution.value}_{orientation}_{width}x{height}{extension}"
            output_path = filedialog.asksaveasfilename(
                title=f"{format_label}の保存先を選択",
                defaultextension=extension,
                initialfile=default_name,
                filetypes=[(format_label, f"*{extension}")],
            )
            if not output_path:
                return
            if Path(output_path).suffix.lower() != extension:
                output_path = str(Path(output_path).with_suffix(extension))

        output_display_path = self._format_path_for_display(
            Path(output_path),
            hidden_text="非表示",
        )
        export_settings = clone_render_settings(self.render_settings)
        if export_format == EXPORT_FORMAT_H264:
            export_settings.transparent_background = False
        export_renderer = ProjectRenderer(self.project, export_settings)

        self.playing = False
        self._stop_audio_preview()
        self.progress.configure(value=0.0)
        self.status_var.set("現在の見た目設定で書き出しています...")

        def progress_callback(progress_value: float, message: str) -> None:
            self.root.after(0, lambda: self._update_export_progress(progress_value, message))

        def run_export() -> None:
            try:
                saved_path = export_video(
                    project=self.project,
                    renderer=export_renderer,
                    output_path=output_path,
                    width=width,
                    height=height,
                    fps=fps,
                    progress_callback=progress_callback,
                    export_format=export_format,
                    png_sequence_prefix=self.project.source_path.stem,
                    audio_mix_settings=audio_mix_settings,
                )
            except Exception as error:
                self.root.after(0, lambda: messagebox.showerror("書き出しに失敗しました", str(error)))
                self.root.after(0, lambda: self.status_var.set("書き出しに失敗しました。"))
                return

            completion_message = (
                f"連番PNGを書き出しました:\n{output_display_path}"
                + ("\n音声は同じフォルダに WAV として保存されています。" if audio_mix_settings.has_audio() else "")
                if export_format == EXPORT_FORMAT_PNG_SEQUENCE
                else f"{self._export_format_value_to_label.get(export_format, '動画')}を書き出しました:\n{output_display_path}"
            )
            self.root.after(0, lambda: messagebox.showinfo("書き出し完了", completion_message))
            self.root.after(0, lambda: self.status_var.set("書き出しが完了しました。"))

        self._export_thread = threading.Thread(target=run_export, daemon=True)
        self._export_thread.start()

    def _current_audio_mix_settings(self) -> AudioMixSettings:
        return AudioMixSettings(
            enable_midi_audio=bool(self.enable_midi_audio_var.get()),
            midi_volume=max(0.0, self.midi_audio_volume_var.get() / 100.0),
            backing_track_path=self.backing_audio_path,
            backing_track_volume=max(0.0, self.backing_audio_volume_var.get() / 100.0),
            loop_backing_track=bool(self.loop_backing_audio_var.get()),
        )

    def _choose_backing_audio(self) -> None:
        audio_path = filedialog.askopenfilename(
            title="音声ファイルを選択",
            filetypes=[
                ("音声ファイル", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not audio_path:
            return
        self.backing_audio_path = Path(audio_path)
        self._refresh_path_labels()
        self._on_audio_option_changed()

    def _clear_backing_audio(self) -> None:
        self.backing_audio_path = None
        self._refresh_path_labels()
        self._on_audio_option_changed()

    def _on_audio_option_changed(self, _raw_value=None) -> None:
        self._update_slider_labels()
        if self.playing:
            self._stop_audio_preview()
            self.playback_origin_sec = self.current_time_sec
            self._start_audio_preview()
            self.playback_started_at = time.perf_counter()

    def _on_path_display_changed(self, _event=None) -> None:
        self._refresh_path_labels()
        self._refresh_custom_font_label()
        self._refresh_mad_image_label()

    def _start_audio_preview(self) -> None:
        if not self.project:
            return
        self._stop_audio_preview()
        if winsound is None:
            return

        audio_settings = self._current_audio_mix_settings()
        if not audio_settings.has_audio():
            return

        try:
            preview_path = self._render_preview_audio_file(audio_settings)
        except Exception as error:
            self.status_var.set(f"音声の準備に失敗しました: {error}")
            return
        if preview_path is None:
            return
        self._preview_audio_path = preview_path
        winsound.PlaySound(str(preview_path), winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT)

    def _stop_audio_preview(self) -> None:
        if winsound is not None:
            winsound.PlaySound(None, 0)
        if self._preview_audio_path is not None:
            try:
                self._preview_audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._preview_audio_path = None

    def _render_preview_audio_file(self, audio_settings: AudioMixSettings) -> Path | None:
        if not self.project or not audio_settings.has_audio():
            return None
        temp_handle = tempfile.NamedTemporaryFile(prefix="midi_preview_audio_", suffix=".wav", delete=False)
        temp_handle.close()
        preview_path = Path(temp_handle.name)
        created_path = create_mixed_audio_wav(
            self.project,
            audio_settings,
            preview_path,
            start_sec=self.current_time_sec,
        )
        if created_path is None:
            preview_path.unlink(missing_ok=True)
            return None
        return created_path

    def _on_close(self) -> None:
        self.playing = False
        self._stop_audio_preview()
        self.root.destroy()

    def on_timeline_changed(self, raw_value: str) -> None:
        if self._slider_updating or not self.project:
            return

        try:
            value = float(raw_value)
        except ValueError:
            return

        self.current_time_sec = max(0.0, min(value, self.project.duration_sec))
        self.playing = False
        self.playback_origin_sec = self.current_time_sec
        self._stop_audio_preview()
        self._refresh_preview()

    def _choose_custom_font(self) -> None:
        font_path = filedialog.askopenfilename(
            title="フォントファイルを選択",
            filetypes=[
                ("フォントファイル", "*.ttf *.ttc *.otf"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not font_path:
            return

        self.render_settings.custom_font_path = str(Path(font_path))
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_custom_font_label()
        self._refresh_preview_if_loaded()

    def _clear_custom_font(self) -> None:
        self.render_settings.custom_font_path = ""
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_custom_font_label()
        self._refresh_preview_if_loaded()

    def _choose_mad_image(self) -> None:
        image_path = filedialog.askopenfilename(
            title="音MAD画像ファイルを選択",
            filetypes=[
                ("画像ファイル", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not image_path:
            return

        self.render_settings.mad_image_path = str(Path(image_path))
        self.render_settings.mad_image_enabled = True
        self.mad_image_enabled_var.set(True)
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_mad_image_label()
        self._refresh_preview_if_loaded()

    def _clear_mad_image(self) -> None:
        self.render_settings.mad_image_path = ""
        self.render_settings.mad_image_enabled = False
        self.mad_image_enabled_var.set(False)
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_mad_image_label()
        self._refresh_preview_if_loaded()

    def _choose_color(self, field_name: str) -> None:
        initial_color = getattr(self.render_settings, field_name)
        selected = colorchooser.askcolor(color=initial_color, title=f"{self._color_labels[field_name]}を選択", parent=self.root)
        if not selected or not selected[1]:
            return

        setattr(self.render_settings, field_name, selected[1])
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self._sync_style_controls_from_settings(selected_theme=CUSTOM_THEME_NAME)
        self._refresh_preview_if_loaded()

    def _on_theme_selected(self, _event=None) -> None:
        if self._updating_style_controls:
            return

        theme_name = self.theme_var.get()
        if theme_name == CUSTOM_THEME_NAME:
            self.preset_name_var.set("")
            return

        loaded_settings = self._load_theme_settings(theme_name)
        if loaded_settings is None:
            return
        self.render_settings = loaded_settings
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self._sync_style_controls_from_settings(selected_theme=theme_name)
        self._refresh_preview_if_loaded()

    def _reset_to_default_theme(self) -> None:
        self.render_settings = get_render_settings_for_theme(DEFAULT_THEME_NAME)
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self._sync_style_controls_from_settings(selected_theme=DEFAULT_THEME_NAME)
        self._refresh_preview_if_loaded()

    def _on_style_changed(self, _event=None) -> None:
        if self._updating_style_controls:
            return

        self.render_settings.view_mode = self._view_mode_label_to_value[self.view_mode_var.get()]
        self.render_settings.font_family = self._font_family_label_to_value.get(
            self.font_family_var.get(),
            "modern_light",
        )
        self.render_settings.corner_style = self._corner_label_to_value[self.corner_style_var.get()]
        self.render_settings.glow_style = self._glow_label_to_value[self.glow_style_var.get()]
        self.render_settings.animation_style = self._animation_label_to_value[self.animation_style_var.get()]
        self.render_settings.mad_image_style = self._mad_image_style_label_to_value[self.mad_image_style_var.get()]
        self.render_settings.afterimage_style = self._afterimage_label_to_value[self.afterimage_style_var.get()]
        self.render_settings.release_fade_style = self._release_fade_label_to_value[self.release_fade_style_var.get()]
        self.render_settings.release_fade_curve = self._release_curve_label_to_value[self.release_fade_curve_var.get()]
        self.render_settings.attack_fade_style = self._attack_fade_label_to_value[self.attack_fade_style_var.get()]
        self.render_settings.attack_fade_curve = self._attack_curve_label_to_value[self.attack_fade_curve_var.get()]
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_preview_if_loaded()

    def _on_toggle_changed(self) -> None:
        if self._updating_style_controls:
            return

        self.render_settings.transparent_background = bool(self.transparent_background_var.get())
        self.render_settings.safe_area_enabled = bool(self.safe_area_enabled_var.get())
        self.render_settings.canvas_border_enabled = bool(self.canvas_border_enabled_var.get())
        self.render_settings.yatsume_enabled = bool(self.yatsume_enabled_var.get())
        self.render_settings.show_midi_notes = bool(self.show_midi_notes_var.get())
        self.render_settings.mad_image_enabled = bool(self.mad_image_enabled_var.get())
        self.render_settings.mad_image_alternate_flip = bool(self.mad_image_alternate_flip_var.get())
        self.render_settings.fit_to_visible_note_range = bool(self.fit_to_visible_note_range_var.get())
        self.render_settings.hide_future_notes = bool(self.hide_future_notes_var.get())
        self.render_settings.show_time_overlay = bool(self.show_time_overlay_var.get())
        self.render_settings.show_measure_overlay = bool(self.show_measure_overlay_var.get())
        self.render_settings.show_stats_overlay = bool(self.show_stats_overlay_var.get())
        self.render_settings.show_chord_overlay = bool(self.show_chord_overlay_var.get())
        self.render_settings.bold_chord_text = bool(self.bold_chord_text_var.get())
        self.render_settings.show_playhead = bool(self.show_playhead_var.get())
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._update_export_option_state()
        self._refresh_preview_if_loaded()

    def _on_strength_changed(self, _raw_value=None) -> None:
        if self._updating_style_controls:
            return

        self.render_settings.visible_measure_count = max(1, min(8, int(round(self.visible_measure_count_var.get()))))
        self.render_settings.lyrics_space_scale = round(self.lyrics_space_scale_var.get() / 100.0, 3)
        self.render_settings.safe_area_scale = round(self.safe_area_scale_var.get() / 100.0, 3)
        self.render_settings.canvas_border_width = round(self.canvas_border_width_var.get() / 100.0, 3)
        self.render_settings.yatsume_size = round(self.yatsume_size_var.get() / 100.0, 3)
        self.render_settings.yatsume_duration_sec = round(self.yatsume_duration_var.get() / 100.0, 3)
        self.render_settings.yatsume_outline_width = round(self.yatsume_outline_width_var.get() / 100.0, 3)
        self.render_settings.yatsume_animation_speed = round(self.yatsume_animation_speed_var.get() / 100.0, 3)
        self.render_settings.yatsume_position_x = round(self.yatsume_position_x_var.get() / 100.0, 3)
        self.render_settings.yatsume_position_y = round(self.yatsume_position_y_var.get() / 100.0, 3)
        self.render_settings.mad_image_size = round(self.mad_image_size_var.get() / 100.0, 3)
        self.render_settings.mad_image_duration_sec = round(self.mad_image_duration_var.get() / 100.0, 3)
        self.render_settings.mad_image_opacity = round(self.mad_image_opacity_var.get() / 100.0, 3)
        self.render_settings.mad_image_position_x = round(self.mad_image_position_x_var.get() / 100.0, 3)
        self.render_settings.mad_image_position_y = round(self.mad_image_position_y_var.get() / 100.0, 3)
        self.render_settings.glow_strength = round(self.glow_strength_var.get() / 100.0, 3)
        self.render_settings.animation_strength = round(self.animation_strength_var.get() / 100.0, 3)
        self.render_settings.animation_speed = round(self.animation_speed_var.get() / 100.0, 3)
        self.render_settings.afterimage_strength = round(self.afterimage_strength_var.get() / 100.0, 3)
        self.render_settings.note_length_scale = round(self.note_length_scale_var.get() / 100.0, 3)
        self.render_settings.note_height_scale = round(self.note_height_scale_var.get() / 100.0, 3)
        self.render_settings.horizontal_padding_ratio = round(self.horizontal_padding_var.get() / 100.0, 3)
        self.render_settings.vertical_padding_ratio = round(self.vertical_padding_var.get() / 100.0, 3)
        self.render_settings.idle_outline_width = round(self.idle_outline_width_var.get() / 100.0, 3)
        self.render_settings.active_outline_width = round(self.active_outline_width_var.get() / 100.0, 3)
        self.render_settings.afterimage_outline_width = round(self.afterimage_outline_width_var.get() / 100.0, 3)
        self.render_settings.afterimage_duration_sec = round(self.afterimage_duration_var.get() / 100.0, 3)
        self.render_settings.afterimage_padding_scale = round(self.afterimage_padding_var.get() / 100.0, 3)
        self.render_settings.release_fade_duration_sec = round(self.release_fade_duration_var.get() / 100.0, 3)
        self.render_settings.attack_fade_duration_sec = round(self.attack_fade_duration_var.get() / 100.0, 3)
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._update_slider_labels()
        self._refresh_preview_if_loaded()

    def _sync_style_controls_from_settings(self, selected_theme: str) -> None:
        self._updating_style_controls = True

        self._refresh_theme_choices(selected_theme)
        self.theme_var.set(selected_theme)
        self.view_mode_var.set(self._view_mode_value_to_label[self.render_settings.view_mode])
        self.font_family_var.set(
            self._font_family_value_to_label.get(
                self.render_settings.font_family,
                self._font_family_value_to_label["modern_light"],
            )
        )
        self.corner_style_var.set(self._corner_value_to_label[self.render_settings.corner_style])
        self.glow_style_var.set(self._glow_value_to_label[self.render_settings.glow_style])
        self.animation_style_var.set(self._animation_value_to_label[self.render_settings.animation_style])
        self.mad_image_style_var.set(self._mad_image_style_value_to_label[self.render_settings.mad_image_style])
        self.afterimage_style_var.set(self._afterimage_value_to_label[self.render_settings.afterimage_style])
        self.release_fade_style_var.set(self._release_fade_value_to_label[self.render_settings.release_fade_style])
        self.release_fade_curve_var.set(self._release_curve_value_to_label[self.render_settings.release_fade_curve])
        self.attack_fade_style_var.set(self._attack_fade_value_to_label[self.render_settings.attack_fade_style])
        self.attack_fade_curve_var.set(self._attack_curve_value_to_label[self.render_settings.attack_fade_curve])
        self.visible_measure_count_var.set(float(self.render_settings.visible_measure_count))
        self.lyrics_space_scale_var.set(self.render_settings.lyrics_space_scale * 100.0)
        self.safe_area_enabled_var.set(self.render_settings.safe_area_enabled)
        self.safe_area_scale_var.set(self.render_settings.safe_area_scale * 100.0)
        self.canvas_border_enabled_var.set(self.render_settings.canvas_border_enabled)
        self.canvas_border_width_var.set(self.render_settings.canvas_border_width * 100.0)
        self.yatsume_enabled_var.set(self.render_settings.yatsume_enabled)
        self.yatsume_size_var.set(self.render_settings.yatsume_size * 100.0)
        self.yatsume_duration_var.set(self.render_settings.yatsume_duration_sec * 100.0)
        self.yatsume_outline_width_var.set(self.render_settings.yatsume_outline_width * 100.0)
        self.yatsume_animation_speed_var.set(self.render_settings.yatsume_animation_speed * 100.0)
        self.yatsume_position_x_var.set(self.render_settings.yatsume_position_x * 100.0)
        self.yatsume_position_y_var.set(self.render_settings.yatsume_position_y * 100.0)
        self.show_midi_notes_var.set(self.render_settings.show_midi_notes)
        self.mad_image_enabled_var.set(self.render_settings.mad_image_enabled)
        self.mad_image_alternate_flip_var.set(self.render_settings.mad_image_alternate_flip)
        self.mad_image_size_var.set(self.render_settings.mad_image_size * 100.0)
        self.mad_image_duration_var.set(self.render_settings.mad_image_duration_sec * 100.0)
        self.mad_image_opacity_var.set(self.render_settings.mad_image_opacity * 100.0)
        self.mad_image_position_x_var.set(self.render_settings.mad_image_position_x * 100.0)
        self.mad_image_position_y_var.set(self.render_settings.mad_image_position_y * 100.0)
        self.transparent_background_var.set(self.render_settings.transparent_background)
        self.fit_to_visible_note_range_var.set(self.render_settings.fit_to_visible_note_range)
        self.hide_future_notes_var.set(self.render_settings.hide_future_notes)
        self.show_time_overlay_var.set(self.render_settings.show_time_overlay)
        self.show_measure_overlay_var.set(self.render_settings.show_measure_overlay)
        self.show_stats_overlay_var.set(self.render_settings.show_stats_overlay)
        self.show_chord_overlay_var.set(self.render_settings.show_chord_overlay)
        self.bold_chord_text_var.set(self.render_settings.bold_chord_text)
        self.show_playhead_var.set(self.render_settings.show_playhead)
        self.glow_strength_var.set(self.render_settings.glow_strength * 100.0)
        self.animation_strength_var.set(self.render_settings.animation_strength * 100.0)
        self.animation_speed_var.set(self.render_settings.animation_speed * 100.0)
        self.afterimage_strength_var.set(self.render_settings.afterimage_strength * 100.0)
        self.note_length_scale_var.set(self.render_settings.note_length_scale * 100.0)
        self.note_height_scale_var.set(self.render_settings.note_height_scale * 100.0)
        self.horizontal_padding_var.set(self.render_settings.horizontal_padding_ratio * 100.0)
        self.vertical_padding_var.set(self.render_settings.vertical_padding_ratio * 100.0)
        self.idle_outline_width_var.set(self.render_settings.idle_outline_width * 100.0)
        self.active_outline_width_var.set(self.render_settings.active_outline_width * 100.0)
        self.afterimage_outline_width_var.set(self.render_settings.afterimage_outline_width * 100.0)
        self.afterimage_duration_var.set(self.render_settings.afterimage_duration_sec * 100.0)
        self.afterimage_padding_var.set(self.render_settings.afterimage_padding_scale * 100.0)
        self.release_fade_duration_var.set(self.render_settings.release_fade_duration_sec * 100.0)
        self.attack_fade_duration_var.set(self.render_settings.attack_fade_duration_sec * 100.0)
        self._update_slider_labels()

        for field_name, label in self._color_swatches.items():
            color_value = getattr(self.render_settings, field_name)
            label.configure(background=color_value)
            self._color_value_vars[field_name].set(color_value.upper())

        self.preset_name_var.set(selected_theme if is_user_preset(selected_theme) else "")
        self._update_preset_button_states()
        self._update_export_option_state()
        self._refresh_custom_font_label()
        self._refresh_mad_image_label()
        self._refresh_yatsume_note_choices()
        self._sync_yatsume_note_controls_from_settings()
        self._refresh_yatsume_piano_roll()

        self._updating_style_controls = False

    def _update_slider_labels(self) -> None:
        self.glow_strength_text_var.set(f"{self.glow_strength_var.get():.0f}%")
        self.animation_strength_text_var.set(f"{self.animation_strength_var.get():.0f}%")
        self.animation_speed_text_var.set(f"{self.animation_speed_var.get():.0f}%")
        self.afterimage_strength_text_var.set(f"{self.afterimage_strength_var.get():.0f}%")
        self.note_length_scale_text_var.set(f"{self.note_length_scale_var.get():.0f}%")
        self.note_height_scale_text_var.set(f"{self.note_height_scale_var.get():.0f}%")
        self.visible_measure_count_text_var.set(f"{int(round(self.visible_measure_count_var.get()))}小節")
        self.lyrics_space_scale_text_var.set(f"{self.lyrics_space_scale_var.get():.0f}%")
        self.safe_area_scale_text_var.set(f"{self.safe_area_scale_var.get():.0f}%")
        self.canvas_border_width_text_var.set(f"{self.canvas_border_width_var.get() / 100.0:.2f}x")
        self.yatsume_size_text_var.set(f"{self.yatsume_size_var.get():.0f}%")
        self.yatsume_duration_text_var.set(f"{self.yatsume_duration_var.get() / 100.0:.2f}秒")
        self.yatsume_outline_width_text_var.set(f"{self.yatsume_outline_width_var.get() / 100.0:.2f}x")
        self.yatsume_animation_speed_text_var.set(f"{self.yatsume_animation_speed_var.get():.0f}%")
        self.yatsume_position_x_text_var.set(f"{self.yatsume_position_x_var.get():.0f}%")
        self.yatsume_position_y_text_var.set(f"{self.yatsume_position_y_var.get():.0f}%")
        self.mad_image_size_text_var.set(f"{self.mad_image_size_var.get():.0f}%")
        self.mad_image_duration_text_var.set(f"{self.mad_image_duration_var.get() / 100.0:.2f}秒")
        self.mad_image_opacity_text_var.set(f"{self.mad_image_opacity_var.get():.0f}%")
        self.mad_image_position_x_text_var.set(f"{self.mad_image_position_x_var.get():.0f}%")
        self.mad_image_position_y_text_var.set(f"{self.mad_image_position_y_var.get():.0f}%")
        self.horizontal_padding_text_var.set(f"{self.horizontal_padding_var.get():.0f}%")
        self.vertical_padding_text_var.set(f"{self.vertical_padding_var.get():.0f}%")
        self.idle_outline_width_text_var.set(f"{self.idle_outline_width_var.get() / 100.0:.2f}x")
        self.active_outline_width_text_var.set(f"{self.active_outline_width_var.get() / 100.0:.2f}x")
        self.afterimage_outline_width_text_var.set(f"{self.afterimage_outline_width_var.get() / 100.0:.2f}x")
        self.afterimage_duration_text_var.set(f"{self.afterimage_duration_var.get() / 100.0:.2f}秒")
        self.afterimage_padding_text_var.set(f"{self.afterimage_padding_var.get() / 100.0:.2f}x")
        self.release_fade_duration_text_var.set(f"{self.release_fade_duration_var.get() / 100.0:.2f}秒")
        self.attack_fade_duration_text_var.set(f"{self.attack_fade_duration_var.get() / 100.0:.2f}秒")
        self.midi_audio_volume_text_var.set(f"{self.midi_audio_volume_var.get():.0f}%")
        self.backing_audio_volume_text_var.set(f"{self.backing_audio_volume_var.get():.0f}%")

    def _schedule_playback_tick(self) -> None:
        self._handle_playback_tick()
        self.root.after(8, self._schedule_playback_tick)

    def _handle_playback_tick(self) -> None:
        if not self.project:
            return

        needs_refresh = False
        if self.playing:
            elapsed = time.perf_counter() - self.playback_started_at
            self.current_time_sec = self.playback_origin_sec + elapsed
            needs_refresh = True
            if self.current_time_sec >= self.project.duration_sec:
                self.current_time_sec = self.project.duration_sec
                self.playing = False
                self._stop_audio_preview()
                self.status_var.set("再生が終了しました。")
                needs_refresh = True

        if needs_refresh:
            self._refresh_preview()

    def _refresh_preview_if_loaded(self) -> None:
        if self.project and self.renderer:
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not self.project or not self.renderer:
            self.preview_label.configure(image="")
            self._refresh_yatsume_piano_roll()
            self.time_var.set("00:00.000 / 00:00.000")
            self.yatsume_seek_time_var.set("00:00.000 / 00:00.000")
            self.measure_var.set("小節: -")
            return

        preview_width, preview_height = self._get_preview_dimensions()
        frame = self.renderer.render_frame(self.current_time_sec, preview_width, preview_height)
        self._preview_image = ImageTk.PhotoImage(frame)
        self.preview_label.configure(image=self._preview_image)

        self._slider_updating = True
        self.timeline.set(self.current_time_sec)
        self.yatsume_seek_var.set(self.current_time_sec)
        self._slider_updating = False

        total_time = self._format_time(self.project.duration_sec)
        current_time = self._format_time(self.current_time_sec)
        self.yatsume_seek_time_var.set(f"{current_time} / {total_time}")
        current_measure = self.renderer.get_measure_for_time(self.current_time_sec)
        self.time_var.set(f"{current_time} / {total_time}")
        self.measure_var.set(
            f"現在小節: {current_measure.index + 1} / {self.project.measure_count} ({current_measure.numerator}/{current_measure.denominator})"
        )

        self._refresh_yatsume_piano_roll()

    def _update_export_progress(self, progress_value: float, message: str) -> None:
        self.progress.configure(value=progress_value * 100.0)
        self.status_var.set(message)

    @staticmethod
    def _format_time(seconds: float) -> str:
        total_milliseconds = max(0, int(round(seconds * 1000)))
        minutes, remainder = divmod(total_milliseconds, 60_000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def main() -> None:
    root = tk.Tk()
    MidiVideoApp(root)
    root.mainloop()
