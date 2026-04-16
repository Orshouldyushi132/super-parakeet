from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe


_STABLE_FFMPEG_EXE: str | None = None


def get_stable_ffmpeg_exe() -> str:
    global _STABLE_FFMPEG_EXE
    if _STABLE_FFMPEG_EXE and Path(_STABLE_FFMPEG_EXE).exists():
        os.environ["IMAGEIO_FFMPEG_EXE"] = _STABLE_FFMPEG_EXE
        return _STABLE_FFMPEG_EXE

    source_exe = Path(get_ffmpeg_exe())
    stable_exe = _copy_ffmpeg_to_ascii_temp(source_exe) if _should_relocate_ffmpeg(source_exe) else source_exe
    _STABLE_FFMPEG_EXE = str(stable_exe)
    os.environ["IMAGEIO_FFMPEG_EXE"] = _STABLE_FFMPEG_EXE
    return _STABLE_FFMPEG_EXE


def _should_relocate_ffmpeg(path: Path) -> bool:
    if getattr(sys, "frozen", False):
        return True
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return True
    return False


def _copy_ffmpeg_to_ascii_temp(source_exe: Path) -> Path:
    target_dir = Path(tempfile.gettempdir()) / "midi_video_exporter_ffmpeg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_exe = target_dir / "ffmpeg.exe"
    try:
        if not target_exe.exists() or target_exe.stat().st_size != source_exe.stat().st_size:
            shutil.copy2(source_exe, target_exe)
    except OSError:
        return source_exe
    return target_exe
