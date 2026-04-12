from __future__ import annotations

import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import ImageTk

from .exporter import export_video
from .midi_loader import load_midi_project
from .models import (
    AFTERIMAGE_STYLE_CHOICES,
    ANIMATION_STYLE_CHOICES,
    ATTACK_FADE_CURVE_CHOICES,
    ATTACK_FADE_STYLE_CHOICES,
    CORNER_STYLE_CHOICES,
    CUSTOM_THEME_NAME,
    DEFAULT_THEME_NAME,
    GLOW_STYLE_CHOICES,
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


PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 540
EXPORT_WIDTH = 1920
EXPORT_HEIGHT = 1080
DEFAULT_FPS = 120


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

        self._glow_value_to_label = {value: label for value, label in GLOW_STYLE_CHOICES}
        self._glow_label_to_value = {label: value for value, label in GLOW_STYLE_CHOICES}
        self._animation_value_to_label = {value: label for value, label in ANIMATION_STYLE_CHOICES}
        self._animation_label_to_value = {label: value for value, label in ANIMATION_STYLE_CHOICES}
        self._afterimage_value_to_label = {value: label for value, label in AFTERIMAGE_STYLE_CHOICES}
        self._afterimage_label_to_value = {label: value for value, label in AFTERIMAGE_STYLE_CHOICES}
        self._corner_value_to_label = {value: label for value, label in CORNER_STYLE_CHOICES}
        self._corner_label_to_value = {label: value for value, label in CORNER_STYLE_CHOICES}
        self._view_mode_value_to_label = {value: label for value, label in VIEW_MODE_CHOICES}
        self._view_mode_label_to_value = {label: value for value, label in VIEW_MODE_CHOICES}
        self._release_fade_value_to_label = {value: label for value, label in RELEASE_FADE_STYLE_CHOICES}
        self._release_fade_label_to_value = {label: value for value, label in RELEASE_FADE_STYLE_CHOICES}
        self._release_curve_value_to_label = {value: label for value, label in RELEASE_FADE_CURVE_CHOICES}
        self._release_curve_label_to_value = {label: value for value, label in RELEASE_FADE_CURVE_CHOICES}
        self._attack_fade_value_to_label = {value: label for value, label in ATTACK_FADE_STYLE_CHOICES}
        self._attack_fade_label_to_value = {label: value for value, label in ATTACK_FADE_STYLE_CHOICES}
        self._attack_curve_value_to_label = {value: label for value, label in ATTACK_FADE_CURVE_CHOICES}
        self._attack_curve_label_to_value = {label: value for value, label in ATTACK_FADE_CURVE_CHOICES}
        self._theme_names = theme_name_choices()

        self.file_label_var = tk.StringVar(value="MIDIファイルが読み込まれていません")
        self.status_var = tk.StringVar(value="MIDIファイルを選択してください。")
        self.time_var = tk.StringVar(value="00:00.000 / 00:00.000")
        self.measure_var = tk.StringVar(value="小節: -")
        self.fps_var = tk.StringVar(value=str(DEFAULT_FPS))
        self.preset_name_var = tk.StringVar()

        self.theme_var = tk.StringVar(value=DEFAULT_THEME_NAME)
        self.view_mode_var = tk.StringVar(value=self._view_mode_value_to_label[self.render_settings.view_mode])
        self.corner_style_var = tk.StringVar(value=self._corner_value_to_label[self.render_settings.corner_style])
        self.glow_style_var = tk.StringVar(value=self._glow_value_to_label[self.render_settings.glow_style])
        self.animation_style_var = tk.StringVar(value=self._animation_value_to_label[self.render_settings.animation_style])
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
        self.hide_future_notes_var = tk.BooleanVar(value=self.render_settings.hide_future_notes)
        self.show_time_overlay_var = tk.BooleanVar(value=self.render_settings.show_time_overlay)
        self.show_measure_overlay_var = tk.BooleanVar(value=self.render_settings.show_measure_overlay)
        self.show_stats_overlay_var = tk.BooleanVar(value=self.render_settings.show_stats_overlay)
        self.show_chord_overlay_var = tk.BooleanVar(value=self.render_settings.show_chord_overlay)
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
        self.glow_strength_text_var = tk.StringVar()
        self.animation_strength_text_var = tk.StringVar()
        self.animation_speed_text_var = tk.StringVar()
        self.afterimage_strength_text_var = tk.StringVar()
        self.note_length_scale_text_var = tk.StringVar()
        self.note_height_scale_text_var = tk.StringVar()
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

        self._color_labels = {
            "background_color": "背景色",
            "idle_note_color": "通常ノーツ色",
            "active_note_color": "発音中ノーツ色",
            "glow_color": "発光色",
            "animation_accent_color": "アニメ色",
            "outline_color": "輪郭色",
        }
        self._color_value_vars: dict[str, tk.StringVar] = {}
        self._color_swatches: dict[str, tk.Label] = {}

        self._configure_styles()
        self._build_ui()
        self._sync_style_controls_from_settings(selected_theme=DEFAULT_THEME_NAME)
        self._schedule_playback_tick()

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
            text="見た目を詰めながら、1小節ごとの固定表示をそのまま動画にできます。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(outer, style="Surface.TFrame", padding=14)
        controls.pack(fill="x")

        ttk.Button(controls, text="MIDIを開く", command=self.open_midi).pack(side="left")
        ttk.Button(controls, text="再生 / 一時停止", command=self.toggle_playback).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="停止", command=self.stop_playback).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="前の小節へ", command=lambda: self.jump_measure(-1)).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="次の小節へ", command=lambda: self.jump_measure(1)).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="MP4を書き出す", style="Accent.TButton", command=self.export_mp4).pack(side="left", padx=(16, 0))

        fps_frame = ttk.Frame(controls, style="Surface.TFrame")
        fps_frame.pack(side="right")
        ttk.Label(fps_frame, text="FPS", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(fps_frame, width=6, textvariable=self.fps_var).pack(side="left")

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
        ttk.Label(info, text="初期値は 120FPS です。", style="Muted.TLabel").pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill="x", pady=(12, 0))

    def _build_settings_panel(self, panel: ttk.LabelFrame) -> None:
        ttk.Label(
            panel,
            text="テーマを土台にしつつ、ノーツ寸法・残像時間・切り替えフェードまで細かく詰められます。",
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
        detail_tab = ttk.Frame(notebook, padding=12)

        notebook.add(basic_tab, text="基本")
        notebook.add(color_tab, text="色")
        notebook.add(effect_tab, text="演出")
        notebook.add(detail_tab, text="詳細")

        self._build_basic_settings_tab(basic_tab)
        self._build_color_settings_tab(color_tab)
        self._build_effect_settings_tab(effect_tab)
        self._build_detail_settings_tab(detail_tab)

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
        self.file_label_var.set(str(Path(midi_path)))
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
            self.status_var.set("再生を一時停止しました。")
            return

        if self.current_time_sec >= self.project.duration_sec:
            self.current_time_sec = 0.0

        self.playing = True
        self.playback_origin_sec = self.current_time_sec
        self.playback_started_at = time.perf_counter()
        self.status_var.set("再生中...")

    def stop_playback(self) -> None:
        self.playing = False
        self.current_time_sec = 0.0
        self.playback_origin_sec = 0.0
        self.status_var.set("停止しました。")
        self._refresh_preview()

    def jump_measure(self, direction: int) -> None:
        if not self.project or not self.renderer:
            return

        current_measure = self.renderer.get_measure_for_time(self.current_time_sec)
        target_index = max(0, min(current_measure.index + direction, self.project.measure_count - 1))
        self.playing = False
        self.current_time_sec = self.project.measures[target_index].start_sec
        self.playback_origin_sec = self.current_time_sec
        self.status_var.set(f"{target_index + 1}小節目へ移動しました。")
        self._refresh_preview()

    def export_mp4(self) -> None:
        if not self.project or not self.renderer:
            messagebox.showinfo("MIDIを開いてください", "動画を書き出す前にMIDIファイルを読み込んでください。")
            return

        if self._export_thread and self._export_thread.is_alive():
            messagebox.showinfo("書き出し中です", "すでに動画の書き出しを実行中です。")
            return

        try:
            fps = max(1, int(self.fps_var.get()))
        except ValueError:
            messagebox.showerror("FPSが不正です", "FPSには整数を入力してください。")
            return

        default_name = f"{self.project.source_path.stem}_小節切り替え.mp4"
        output_path = filedialog.asksaveasfilename(
            title="MP4の保存先を選択",
            defaultextension=".mp4",
            initialfile=default_name,
            filetypes=[("MP4動画", "*.mp4")],
        )
        if not output_path:
            return

        export_settings = clone_render_settings(self.render_settings)
        export_renderer = ProjectRenderer(self.project, export_settings)

        self.playing = False
        self.progress.configure(value=0.0)
        self.status_var.set("現在の見た目設定で動画を書き出します...")

        def progress_callback(progress_value: float, message: str) -> None:
            self.root.after(0, lambda: self._update_export_progress(progress_value, message))

        def run_export() -> None:
            try:
                export_video(
                    project=self.project,
                    renderer=export_renderer,
                    output_path=output_path,
                    width=EXPORT_WIDTH,
                    height=EXPORT_HEIGHT,
                    fps=fps,
                    progress_callback=progress_callback,
                )
            except Exception as error:
                self.root.after(0, lambda: messagebox.showerror("書き出しに失敗しました", str(error)))
                self.root.after(0, lambda: self.status_var.set("書き出しに失敗しました。"))
                return

            self.root.after(0, lambda: messagebox.showinfo("書き出し完了", f"動画を保存しました:\n{output_path}"))
            self.root.after(0, lambda: self.status_var.set("書き出しが完了しました。"))

        self._export_thread = threading.Thread(target=run_export, daemon=True)
        self._export_thread.start()

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
        self._refresh_preview()

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
        self.render_settings.corner_style = self._corner_label_to_value[self.corner_style_var.get()]
        self.render_settings.glow_style = self._glow_label_to_value[self.glow_style_var.get()]
        self.render_settings.animation_style = self._animation_label_to_value[self.animation_style_var.get()]
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

        self.render_settings.hide_future_notes = bool(self.hide_future_notes_var.get())
        self.render_settings.show_time_overlay = bool(self.show_time_overlay_var.get())
        self.render_settings.show_measure_overlay = bool(self.show_measure_overlay_var.get())
        self.render_settings.show_stats_overlay = bool(self.show_stats_overlay_var.get())
        self.render_settings.show_chord_overlay = bool(self.show_chord_overlay_var.get())
        self.render_settings.show_playhead = bool(self.show_playhead_var.get())
        if self.renderer:
            self.renderer.set_settings(self.render_settings)
        self.theme_var.set(CUSTOM_THEME_NAME)
        self.preset_name_var.set("")
        self._refresh_preview_if_loaded()

    def _on_strength_changed(self, _raw_value=None) -> None:
        if self._updating_style_controls:
            return

        self.render_settings.visible_measure_count = max(1, min(8, int(round(self.visible_measure_count_var.get()))))
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
        self.corner_style_var.set(self._corner_value_to_label[self.render_settings.corner_style])
        self.glow_style_var.set(self._glow_value_to_label[self.render_settings.glow_style])
        self.animation_style_var.set(self._animation_value_to_label[self.render_settings.animation_style])
        self.afterimage_style_var.set(self._afterimage_value_to_label[self.render_settings.afterimage_style])
        self.release_fade_style_var.set(self._release_fade_value_to_label[self.render_settings.release_fade_style])
        self.release_fade_curve_var.set(self._release_curve_value_to_label[self.render_settings.release_fade_curve])
        self.attack_fade_style_var.set(self._attack_fade_value_to_label[self.render_settings.attack_fade_style])
        self.attack_fade_curve_var.set(self._attack_curve_value_to_label[self.render_settings.attack_fade_curve])
        self.visible_measure_count_var.set(float(self.render_settings.visible_measure_count))
        self.hide_future_notes_var.set(self.render_settings.hide_future_notes)
        self.show_time_overlay_var.set(self.render_settings.show_time_overlay)
        self.show_measure_overlay_var.set(self.render_settings.show_measure_overlay)
        self.show_stats_overlay_var.set(self.render_settings.show_stats_overlay)
        self.show_chord_overlay_var.set(self.render_settings.show_chord_overlay)
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

        self._updating_style_controls = False

    def _update_slider_labels(self) -> None:
        self.glow_strength_text_var.set(f"{self.glow_strength_var.get():.0f}%")
        self.animation_strength_text_var.set(f"{self.animation_strength_var.get():.0f}%")
        self.animation_speed_text_var.set(f"{self.animation_speed_var.get():.0f}%")
        self.afterimage_strength_text_var.set(f"{self.afterimage_strength_var.get():.0f}%")
        self.note_length_scale_text_var.set(f"{self.note_length_scale_var.get():.0f}%")
        self.note_height_scale_text_var.set(f"{self.note_height_scale_var.get():.0f}%")
        self.visible_measure_count_text_var.set(f"{int(round(self.visible_measure_count_var.get()))}小節")
        self.horizontal_padding_text_var.set(f"{self.horizontal_padding_var.get():.0f}%")
        self.vertical_padding_text_var.set(f"{self.vertical_padding_var.get():.0f}%")
        self.idle_outline_width_text_var.set(f"{self.idle_outline_width_var.get() / 100.0:.2f}x")
        self.active_outline_width_text_var.set(f"{self.active_outline_width_var.get() / 100.0:.2f}x")
        self.afterimage_outline_width_text_var.set(f"{self.afterimage_outline_width_var.get() / 100.0:.2f}x")
        self.afterimage_duration_text_var.set(f"{self.afterimage_duration_var.get() / 100.0:.2f}秒")
        self.afterimage_padding_text_var.set(f"{self.afterimage_padding_var.get() / 100.0:.2f}x")
        self.release_fade_duration_text_var.set(f"{self.release_fade_duration_var.get() / 100.0:.2f}秒")
        self.attack_fade_duration_text_var.set(f"{self.attack_fade_duration_var.get() / 100.0:.2f}秒")

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
            self.time_var.set("00:00.000 / 00:00.000")
            self.measure_var.set("小節: -")
            return

        frame = self.renderer.render_frame(self.current_time_sec, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self._preview_image = ImageTk.PhotoImage(frame)
        self.preview_label.configure(image=self._preview_image)

        self._slider_updating = True
        self.timeline.set(self.current_time_sec)
        self._slider_updating = False

        total_time = self._format_time(self.project.duration_sec)
        current_time = self._format_time(self.current_time_sec)
        current_measure = self.renderer.get_measure_for_time(self.current_time_sec)
        self.time_var.set(f"{current_time} / {total_time}")
        self.measure_var.set(
            f"現在小節: {current_measure.index + 1} / {self.project.measure_count} ({current_measure.numerator}/{current_measure.denominator})"
        )

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
