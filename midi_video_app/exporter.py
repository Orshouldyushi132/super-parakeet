from __future__ import annotations

import math
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio.v2 as imageio
import numpy as np

from .models import MidiProject
from .renderer import ProjectRenderer


ProgressCallback = Callable[[float, str], None]

EXPORT_FORMAT_H264 = "h264"
EXPORT_FORMAT_PNG_SEQUENCE = "png_sequence"
DEFAULT_EXPORT_FORMAT = EXPORT_FORMAT_H264


@dataclass(frozen=True, slots=True)
class ExportResolutionPreset:
    value: str
    label: str
    width: int
    height: int


EXPORT_FORMAT_CHOICES: tuple[tuple[str, str], ...] = (
    (EXPORT_FORMAT_H264, "H.264"),
    (EXPORT_FORMAT_PNG_SEQUENCE, "連番PNG"),
)

EXPORT_RESOLUTION_PRESETS: tuple[ExportResolutionPreset, ...] = (
    ExportResolutionPreset("4k_landscape", "4K 横 3840×2160", 3840, 2160),
    ExportResolutionPreset("4k_portrait", "4K 縦 2160×3840", 2160, 3840),
    ExportResolutionPreset("1080p_landscape", "1080p 横 1920×1080", 1920, 1080),
    ExportResolutionPreset("1080p_portrait", "1080p 縦 1080×1920", 1080, 1920),
)
DEFAULT_EXPORT_RESOLUTION = "4k_landscape"
EXPORT_RESOLUTION_BY_VALUE = {preset.value: preset for preset in EXPORT_RESOLUTION_PRESETS}


def get_export_resolution_preset(value: str | None) -> ExportResolutionPreset:
    if value and value in EXPORT_RESOLUTION_BY_VALUE:
        return EXPORT_RESOLUTION_BY_VALUE[value]
    return EXPORT_RESOLUTION_BY_VALUE[DEFAULT_EXPORT_RESOLUTION]


def export_video(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None = None,
    export_format: str = DEFAULT_EXPORT_FORMAT,
    png_sequence_prefix: str = "frame",
) -> Path:
    if export_format == EXPORT_FORMAT_PNG_SEQUENCE:
        return _export_png_sequence(
            project=project,
            renderer=renderer,
            output_path=output_path,
            width=width,
            height=height,
            fps=fps,
            progress_callback=progress_callback,
            png_sequence_prefix=png_sequence_prefix,
        )

    return _export_h264(
        project=project,
        renderer=renderer,
        output_path=output_path,
        width=width,
        height=height,
        fps=fps,
        progress_callback=progress_callback,
    )


def _export_h264(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None,
) -> Path:
    destination = Path(output_path)
    if destination.suffix.lower() != ".mp4":
        destination = destination.with_suffix(".mp4")
    destination.parent.mkdir(parents=True, exist_ok=True)

    total_frames = _total_frames(project.duration_sec, fps)
    if progress_callback:
        progress_callback(0.0, "H.264動画を書き出しています...")

    # Windows + imageio-ffmpeg can fail when ffmpeg receives a non-ASCII output filename.
    # Render to a temporary ASCII-only path first, then move the finished MP4 to the user path.
    with tempfile.TemporaryDirectory(prefix="midi_video_export_") as temp_dir:
        temp_output = Path(temp_dir) / "export.mp4"
        with imageio.get_writer(
            temp_output,
            fps=fps,
            codec="libx264",
            quality=8,
            pixelformat="yuv420p",
            macro_block_size=None,
            ffmpeg_log_level="error",
        ) as writer:
            for frame_index in range(total_frames):
                current_time = _frame_time(project.duration_sec, fps, frame_index)
                frame = renderer.render_frame(current_time, width, height)
                writer.append_data(np.asarray(frame.convert("RGB")))

                if progress_callback:
                    progress_callback(
                        (frame_index + 1) / total_frames,
                        f"H.264動画を書き出しています... {frame_index + 1}/{total_frames}",
                    )

        if destination.exists():
            destination.unlink()
        shutil.move(str(temp_output), str(destination))

    if progress_callback:
        progress_callback(1.0, f"書き出しが完了しました: {destination.name}")
    return destination


def _export_png_sequence(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None,
    png_sequence_prefix: str,
) -> Path:
    destination_dir = Path(output_path)
    destination_dir.mkdir(parents=True, exist_ok=True)

    total_frames = _total_frames(project.duration_sec, fps)
    prefix = _sanitize_sequence_prefix(png_sequence_prefix)
    use_alpha = bool(getattr(renderer.settings, "transparent_background", False))
    color_mode = "RGBA" if use_alpha else "RGB"

    if progress_callback:
        progress_callback(0.0, "連番PNGを書き出しています...")

    for frame_index in range(total_frames):
        current_time = _frame_time(project.duration_sec, fps, frame_index)
        frame = renderer.render_frame(current_time, width, height)
        frame_path = destination_dir / f"{prefix}_{frame_index + 1:06d}.png"
        frame.convert(color_mode).save(frame_path, format="PNG")

        if progress_callback:
            progress_callback(
                (frame_index + 1) / total_frames,
                f"連番PNGを書き出しています... {frame_index + 1}/{total_frames}",
            )

    if progress_callback:
        progress_callback(1.0, f"書き出しが完了しました: {destination_dir.name}")
    return destination_dir


def _total_frames(duration_sec: float, fps: int) -> int:
    return max(1, math.ceil(duration_sec * fps))


def _frame_time(duration_sec: float, fps: int, frame_index: int) -> float:
    return min(frame_index / fps, max(duration_sec - 1e-6, 0.0))


def _sanitize_sequence_prefix(raw_value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_value.strip())
    normalized = normalized.strip("._")
    return normalized or "frame"
