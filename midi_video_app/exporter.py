from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path
from typing import Callable

import imageio.v2 as imageio
import numpy as np

from .models import MidiProject
from .renderer import ProjectRenderer


ProgressCallback = Callable[[float, str], None]


def export_video(
    project: MidiProject,
    renderer: ProjectRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    destination = Path(output_path)
    alpha_export = bool(getattr(renderer.settings, "transparent_background", False))
    if alpha_export and destination.suffix.lower() != ".mov":
        destination = destination.with_suffix(".mov")
    total_frames = max(1, math.ceil(project.duration_sec * fps))
    destination.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0.0, "書き出しを準備中...")

    # Windows + imageio-ffmpeg can fail when ffmpeg receives a non-ASCII output filename.
    # Render to a temporary ASCII-only path first, then move the finished MP4 to the user path.
    with tempfile.TemporaryDirectory(prefix="midi_video_export_") as temp_dir:
        temp_output = Path(temp_dir) / ("export.mov" if alpha_export else "export.mp4")

        writer_kwargs = {
            "fps": fps,
            "macro_block_size": None,
            "ffmpeg_log_level": "error",
        }
        if alpha_export:
            writer_kwargs.update(
                {
                    "codec": "png",
                    "pixelformat": "rgba",
                }
            )
        else:
            writer_kwargs.update(
                {
                    "codec": "libx264",
                    "quality": 8,
                }
            )

        with imageio.get_writer(temp_output, **writer_kwargs) as writer:
            for frame_index in range(total_frames):
                current_time = min(frame_index / fps, max(project.duration_sec - 1e-6, 0.0))
                frame = renderer.render_frame(current_time, width, height)
                if alpha_export:
                    writer.append_data(np.asarray(frame.convert("RGBA")))
                else:
                    writer.append_data(np.asarray(frame.convert("RGB")))

                if progress_callback:
                    progress_callback((frame_index + 1) / total_frames, f"動画を書き出し中... {frame_index + 1}/{total_frames}")

        if destination.exists():
            destination.unlink()
        shutil.move(str(temp_output), str(destination))

    if progress_callback:
        progress_callback(1.0, f"書き出し完了 {destination.name}")

    return destination
