from __future__ import annotations

import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from .exporter import export_video
from .midi_loader import load_midi_project
from .models import MidiProject
from .renderer import ProjectRenderer


PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 540
EXPORT_WIDTH = 1920
EXPORT_HEIGHT = 1080
DEFAULT_FPS = 30


class MidiVideoApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MIDI動画書き出しツール")
        self.root.geometry("1120x820")
        self.root.minsize(980, 720)

        self.project: MidiProject | None = None
        self.renderer: ProjectRenderer | None = None
        self.current_time_sec = 0.0
        self.playing = False
        self.playback_started_at = 0.0
        self.playback_origin_sec = 0.0
        self._slider_updating = False
        self._preview_image: ImageTk.PhotoImage | None = None
        self._export_thread: threading.Thread | None = None

        self.file_label_var = tk.StringVar(value="MIDIファイルが読み込まれていません")
        self.status_var = tk.StringVar(value="MIDIファイルを選択してください。")
        self.time_var = tk.StringVar(value="00:00.000 / 00:00.000")
        self.measure_var = tk.StringVar(value="小節: -")
        self.fps_var = tk.StringVar(value=str(DEFAULT_FPS))

        self._build_ui()
        self._schedule_playback_tick()

    def _build_ui(self) -> None:
        self.root.configure(background="#111111")

        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        controls = ttk.Frame(outer)
        controls.pack(fill="x")

        ttk.Button(controls, text="MIDIを開く", command=self.open_midi).pack(side="left")
        ttk.Button(controls, text="再生 / 一時停止", command=self.toggle_playback).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="停止", command=self.stop_playback).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="前の小節へ", command=lambda: self.jump_measure(-1)).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="次の小節へ", command=lambda: self.jump_measure(1)).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="MP4を書き出す", command=self.export_mp4).pack(side="left", padx=(16, 0))

        fps_frame = ttk.Frame(controls)
        fps_frame.pack(side="right")
        ttk.Label(fps_frame, text="FPS").pack(side="left", padx=(0, 6))
        ttk.Entry(fps_frame, width=6, textvariable=self.fps_var).pack(side="left")

        ttk.Label(outer, textvariable=self.file_label_var).pack(fill="x", pady=(12, 8))

        preview_frame = ttk.Frame(outer)
        preview_frame.pack(fill="both", expand=True)

        self.preview_label = ttk.Label(preview_frame)
        self.preview_label.pack(fill="both", expand=True)

        timeline_frame = ttk.Frame(outer)
        timeline_frame.pack(fill="x", pady=(10, 0))

        self.timeline = ttk.Scale(timeline_frame, from_=0.0, to=1.0, orient="horizontal", command=self.on_timeline_changed)
        self.timeline.pack(fill="x")

        info = ttk.Frame(outer)
        info.pack(fill="x", pady=(12, 0))

        ttk.Label(info, textvariable=self.time_var).pack(side="left")
        ttk.Label(info, textvariable=self.measure_var).pack(side="left", padx=(20, 0))
        ttk.Label(info, textvariable=self.status_var).pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill="x", pady=(12, 0))

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
            self.renderer = ProjectRenderer(self.project)
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

        self.playing = False
        self.progress.configure(value=0.0)
        self.status_var.set("小節ごとの切り替え表示で動画を書き出します...")

        def progress_callback(progress_value: float, message: str) -> None:
            self.root.after(0, lambda: self._update_export_progress(progress_value, message))

        def run_export() -> None:
            try:
                export_video(
                    project=self.project,
                    renderer=self.renderer,
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

    def _schedule_playback_tick(self) -> None:
        self._handle_playback_tick()
        self.root.after(33, self._schedule_playback_tick)

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
    app = MidiVideoApp(root)
    root.mainloop()
