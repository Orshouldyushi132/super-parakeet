from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import imageio.v2 as imageio
import numpy as np

from .models import MidiProject
from .renderer import MeasureRenderer


ProgressCallback = Callable[[float, str], None]


def export_video(
    project: MidiProject,
    renderer: MeasureRenderer,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    destination = Path(output_path)
    total_frames = max(1, math.ceil(project.duration_sec * fps))

    if progress_callback:
        progress_callback(0.0, "Preparing export...")

    with imageio.get_writer(
        destination,
        fps=fps,
        codec="libx264",
        quality=8,
        macro_block_size=None,
        ffmpeg_log_level="error",
    ) as writer:
        for frame_index in range(total_frames):
            current_time = min(frame_index / fps, max(project.duration_sec - 1e-6, 0.0))
            frame = renderer.render_frame(current_time, width, height)
            writer.append_data(np.asarray(frame))

            if progress_callback:
                progress_callback((frame_index + 1) / total_frames, f"Exporting frame {frame_index + 1}/{total_frames}")

    if progress_callback:
        progress_callback(1.0, f"Finished: {destination.name}")

    return destination
