from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio.v2 as imageio
import numpy as np

from .audio_engine import AudioMixSettings, DEFAULT_AUDIO_SAMPLE_RATE, create_mixed_audio_wav
from .ffmpeg_runtime import get_stable_ffmpeg_exe
from .models import MidiProject
from .renderer import ProjectRenderer


ProgressCallback = Callable[[float, str], None]

EXPORT_FORMAT_H264 = "h264"
EXPORT_FORMAT_MOV = "mov"
EXPORT_FORMAT_PNG_SEQUENCE = "png_sequence"
DEFAULT_EXPORT_FORMAT = EXPORT_FORMAT_H264

EXPORT_ORIENTATION_LANDSCAPE = "landscape"
EXPORT_ORIENTATION_PORTRAIT = "portrait"
DEFAULT_EXPORT_ORIENTATION = EXPORT_ORIENTATION_LANDSCAPE


@dataclass(frozen=True, slots=True)
class ExportResolutionPreset:
    value: str
    label: str
    width: int
    height: int

    def dimensions(self, orientation: str) -> tuple[int, int]:
        normalized_orientation = normalize_export_orientation(orientation)
        if normalized_orientation == EXPORT_ORIENTATION_PORTRAIT:
            return self.height, self.width
        return self.width, self.height


EXPORT_FORMAT_CHOICES: tuple[tuple[str, str], ...] = (
    (EXPORT_FORMAT_H264, "H.264 MP4"),
    (EXPORT_FORMAT_MOV, "MOV"),
    (EXPORT_FORMAT_PNG_SEQUENCE, "連番PNG"),
)

EXPORT_ORIENTATION_CHOICES: tuple[tuple[str, str], ...] = (
    (EXPORT_ORIENTATION_LANDSCAPE, "横動画"),
    (EXPORT_ORIENTATION_PORTRAIT, "縦動画"),
)

EXPORT_RESOLUTION_PRESETS: tuple[ExportResolutionPreset, ...] = (
    ExportResolutionPreset("4k", "4K", 3840, 2160),
    ExportResolutionPreset("1440p", "1440p", 2560, 1440),
    ExportResolutionPreset("1080p", "1080p", 1920, 1080),
    ExportResolutionPreset("720p", "720p", 1280, 720),
)
DEFAULT_EXPORT_RESOLUTION = "4k"

EXPORT_FORMAT_VALUES = {value for value, _ in EXPORT_FORMAT_CHOICES}
EXPORT_ORIENTATION_VALUES = {value for value, _ in EXPORT_ORIENTATION_CHOICES}
EXPORT_RESOLUTION_BY_VALUE = {preset.value: preset for preset in EXPORT_RESOLUTION_PRESETS}


def normalize_export_format(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in EXPORT_FORMAT_VALUES:
        return normalized
    return DEFAULT_EXPORT_FORMAT


def normalize_export_orientation(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in EXPORT_ORIENTATION_VALUES:
        return normalized
    return DEFAULT_EXPORT_ORIENTATION


def get_export_resolution_preset(value: str | None) -> ExportResolutionPreset:
    if value and value in EXPORT_RESOLUTION_BY_VALUE:
        return EXPORT_RESOLUTION_BY_VALUE[value]
    return EXPORT_RESOLUTION_BY_VALUE[DEFAULT_EXPORT_RESOLUTION]


def get_export_dimensions(
    resolution_value: str | None,
    orientation_value: str | None,
) -> tuple[int, int]:
    preset = get_export_resolution_preset(resolution_value)
    return preset.dimensions(orientation_value or DEFAULT_EXPORT_ORIENTATION)


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
    audio_mix_settings: AudioMixSettings | None = None,
) -> Path:
    normalized_format = normalize_export_format(export_format)
    if normalized_format == EXPORT_FORMAT_PNG_SEQUENCE:
        return _export_png_sequence(
            project=project,
            renderer=renderer,
            output_path=output_path,
            width=width,
            height=height,
            fps=fps,
            progress_callback=progress_callback,
            png_sequence_prefix=png_sequence_prefix,
            audio_mix_settings=audio_mix_settings,
        )

    if normalized_format == EXPORT_FORMAT_MOV:
        return _export_mov(
            project=project,
            renderer=renderer,
            output_path=output_path,
            width=width,
            height=height,
            fps=fps,
            progress_callback=progress_callback,
            audio_mix_settings=audio_mix_settings,
        )

    return _export_h264(
        project=project,
        renderer=renderer,
        output_path=output_path,
        width=width,
        height=height,
        fps=fps,
        progress_callback=progress_callback,
        audio_mix_settings=audio_mix_settings,
    )


def _export_h264(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None,
    audio_mix_settings: AudioMixSettings | None,
) -> Path:
    return _export_video_file(
        project=project,
        renderer=renderer,
        output_path=output_path,
        width=width,
        height=height,
        fps=fps,
        progress_callback=progress_callback,
        file_suffix=".mp4",
        temp_file_name="export.mp4",
        codec="libx264",
        pixelformat="yuv420p",
        color_mode="RGB",
        writer_kwargs={"quality": 8},
        progress_label="H.264",
        audio_mix_settings=audio_mix_settings,
    )


def _export_mov(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None,
    audio_mix_settings: AudioMixSettings | None,
) -> Path:
    use_alpha = bool(getattr(renderer.settings, "transparent_background", False))
    pixelformat = "yuva444p10le" if use_alpha else "yuv422p10le"
    profile = "4" if use_alpha else "3"
    color_mode = "RGBA" if use_alpha else "RGB"
    return _export_video_file(
        project=project,
        renderer=renderer,
        output_path=output_path,
        width=width,
        height=height,
        fps=fps,
        progress_callback=progress_callback,
        file_suffix=".mov",
        temp_file_name="export.mov",
        codec="prores_ks",
        pixelformat=pixelformat,
        color_mode=color_mode,
        writer_kwargs={"output_params": ["-profile:v", profile]},
        progress_label="MOV",
        audio_mix_settings=audio_mix_settings,
    )


def _export_video_file(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None,
    *,
    file_suffix: str,
    temp_file_name: str,
    codec: str,
    pixelformat: str,
    color_mode: str,
    writer_kwargs: dict[str, object] | None,
    progress_label: str,
    audio_mix_settings: AudioMixSettings | None,
) -> Path:
    destination = Path(output_path)
    if destination.suffix.lower() != file_suffix:
        destination = destination.with_suffix(file_suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)

    total_frames = _total_frames(project.duration_sec, fps)
    if progress_callback:
        progress_callback(0.0, f"{progress_label}を書き出しています...")

    writer_options = {
        "fps": fps,
        "codec": codec,
        "pixelformat": pixelformat,
        "macro_block_size": None,
        "ffmpeg_log_level": "error",
    }
    if writer_kwargs:
        writer_options.update(writer_kwargs)

    get_stable_ffmpeg_exe()

    with tempfile.TemporaryDirectory(prefix="midi_video_export_") as temp_dir:
        temp_output = Path(temp_dir) / temp_file_name
        with imageio.get_writer(temp_output, **writer_options) as writer:
            for frame_index in range(total_frames):
                current_time = _frame_time(project.duration_sec, fps, frame_index)
                frame = renderer.render_frame(current_time, width, height)
                writer.append_data(np.asarray(frame.convert(color_mode)))

                if progress_callback:
                    progress_callback(
                        ((frame_index + 1) / total_frames) * 0.82,
                        f"{progress_label}を書き出しています... {frame_index + 1}/{total_frames}",
                    )
        final_temp_output = temp_output
        if audio_mix_settings and audio_mix_settings.has_audio():
            if progress_callback:
                progress_callback(0.86, "音声を合成しています...")
            audio_path = create_mixed_audio_wav(
                project,
                audio_mix_settings,
                Path(temp_dir) / "audio_mix.wav",
                sample_rate=DEFAULT_AUDIO_SAMPLE_RATE,
            )
            if audio_path is not None:
                if progress_callback:
                    progress_callback(0.92, "動画と音声を結合しています...")
                muxed_output = Path(temp_dir) / f"muxed{file_suffix}"
                _mux_audio_track(
                    video_path=temp_output,
                    audio_path=audio_path,
                    output_path=muxed_output,
                    export_format=file_suffix,
                )
                final_temp_output = muxed_output

        if destination.exists():
            destination.unlink()
        shutil.move(str(final_temp_output), str(destination))

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
    audio_mix_settings: AudioMixSettings | None,
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
        progress_callback(0.9, f"連番PNGを書き出しています... {total_frames}/{total_frames}")

    if audio_mix_settings and audio_mix_settings.has_audio():
        create_mixed_audio_wav(
            project,
            audio_mix_settings,
            destination_dir / f"{prefix}_audio.wav",
            sample_rate=DEFAULT_AUDIO_SAMPLE_RATE,
        )

    if progress_callback:
        progress_callback(1.0, f"書き出しが完了しました: {destination_dir.name}")
    return destination_dir


def _mux_audio_track(video_path: Path, audio_path: Path, output_path: Path, export_format: str) -> None:
    ffmpeg_exe = get_stable_ffmpeg_exe()
    audio_codec = ["-c:a", "pcm_s16le"] if export_format == ".mov" else ["-c:a", "aac", "-b:a", "192k"]
    extra_params = ["-movflags", "+faststart"] if export_format == ".mp4" else []
    command = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        *audio_codec,
        *extra_params,
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"FFmpeg で音声結合に失敗しました: {stderr or completed.returncode}")


def _total_frames(duration_sec: float, fps: int) -> int:
    return max(1, math.ceil(duration_sec * fps))


def _frame_time(duration_sec: float, fps: int, frame_index: int) -> float:
    return min(frame_index / fps, max(duration_sec - 1e-6, 0.0))


def _sanitize_sequence_prefix(raw_value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_value.strip())
    normalized = normalized.strip("._")
    return normalized or "frame"
