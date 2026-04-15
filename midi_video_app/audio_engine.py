from __future__ import annotations

import math
import subprocess
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe

from .models import MidiProject, NoteEvent


DEFAULT_AUDIO_SAMPLE_RATE = 44_100


@dataclass(slots=True)
class AudioMixSettings:
    enable_midi_audio: bool = True
    midi_volume: float = 0.7
    backing_track_path: Path | None = None
    backing_track_volume: float = 0.85
    loop_backing_track: bool = False

    def normalized_backing_track_path(self) -> Path | None:
        if self.backing_track_path is None:
            return None
        path = Path(self.backing_track_path)
        if not path.exists():
            raise FileNotFoundError(f"音声ファイルが見つかりません: {path}")
        return path

    def has_audio(self) -> bool:
        return (self.enable_midi_audio and self.midi_volume > 0.0) or (
            self.backing_track_path is not None and self.backing_track_volume > 0.0
        )


def create_mixed_audio_wav(
    project: MidiProject,
    mix_settings: AudioMixSettings,
    output_path: str | Path,
    *,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
) -> Path | None:
    if not mix_settings.has_audio():
        return None
    mix = render_audio_mix(
        project,
        mix_settings,
        sample_rate=sample_rate,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )
    if mix.size == 0:
        return None
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_wave(destination, mix, sample_rate)
    return destination


def render_audio_mix(
    project: MidiProject,
    mix_settings: AudioMixSettings,
    *,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
) -> np.ndarray:
    clamped_start = max(0.0, float(start_sec))
    remaining_duration = max(0.0, project.duration_sec - clamped_start)
    target_duration = remaining_duration if duration_sec is None else max(0.0, min(float(duration_sec), remaining_duration))
    sample_count = max(0, int(math.ceil(target_duration * sample_rate)))
    if sample_count <= 0:
        return np.zeros((0, 2), dtype=np.float32)

    mix = np.zeros((sample_count, 2), dtype=np.float32)

    if mix_settings.enable_midi_audio and mix_settings.midi_volume > 0.0:
        mix += _synthesize_midi_audio(
            project.notes,
            sample_count=sample_count,
            sample_rate=sample_rate,
            start_sec=clamped_start,
            gain=max(0.0, float(mix_settings.midi_volume)),
        )

    backing_track_path = mix_settings.normalized_backing_track_path()
    if backing_track_path is not None and mix_settings.backing_track_volume > 0.0:
        mix += _prepare_backing_track(
            backing_track_path,
            sample_count=sample_count,
            sample_rate=sample_rate,
            start_sec=clamped_start,
            gain=max(0.0, float(mix_settings.backing_track_volume)),
            loop_audio=bool(mix_settings.loop_backing_track),
        )

    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.98:
        mix *= 0.98 / peak
    mix = np.clip(mix, -1.0, 1.0)
    return mix.astype(np.float32, copy=False)


def _synthesize_midi_audio(
    notes: list[NoteEvent],
    *,
    sample_count: int,
    sample_rate: int,
    start_sec: float,
    gain: float,
) -> np.ndarray:
    audio = np.zeros((sample_count, 2), dtype=np.float32)
    clip_end_sec = start_sec + sample_count / sample_rate

    for note in notes:
        clip_start = max(note.start_sec, start_sec)
        clip_end = min(note.end_sec, clip_end_sec)
        if clip_end <= clip_start:
            continue

        start_index = max(0, int(math.floor((clip_start - start_sec) * sample_rate)))
        end_index = min(sample_count, int(math.ceil((clip_end - start_sec) * sample_rate)))
        frame_count = end_index - start_index
        if frame_count <= 0:
            continue

        absolute_note_offset = clip_start - note.start_sec
        local_times = absolute_note_offset + np.arange(frame_count, dtype=np.float32) / sample_rate
        note_duration = max(1e-4, note.end_sec - note.start_sec)
        frequency = 440.0 * (2.0 ** ((note.note - 69) / 12.0))

        # A light multi-sine blend keeps it simple but fuller than a pure sine.
        waveform = (
            0.62 * np.sin(2.0 * math.pi * frequency * local_times)
            + 0.24 * np.sin(2.0 * math.pi * frequency * 2.0 * local_times + 0.15)
            + 0.14 * np.sin(2.0 * math.pi * frequency * 3.0 * local_times + 0.33)
        )

        attack_sec = min(0.012, note_duration * 0.35)
        release_sec = min(0.08, note_duration * 0.45)
        attack_curve = np.ones(frame_count, dtype=np.float32)
        if attack_sec > 1e-4:
            attack_curve = np.minimum(1.0, local_times / attack_sec)

        remaining = np.maximum(0.0, note.end_sec - (clip_start + np.arange(frame_count, dtype=np.float32) / sample_rate))
        release_curve = np.ones(frame_count, dtype=np.float32)
        if release_sec > 1e-4:
            release_curve = np.minimum(1.0, remaining / release_sec)

        envelope = np.clip(attack_curve * release_curve, 0.0, 1.0)
        velocity_gain = ((max(1, note.velocity) / 127.0) ** 1.18) * 0.55 * gain
        pan = max(-0.35, min(0.35, (note.note - 60) / 24.0 * 0.22))
        left_gain = 1.0 - pan
        right_gain = 1.0 + pan

        shaped = waveform.astype(np.float32) * envelope * velocity_gain
        audio[start_index:end_index, 0] += shaped * left_gain
        audio[start_index:end_index, 1] += shaped * right_gain

    return audio


def _prepare_backing_track(
    audio_path: Path,
    *,
    sample_count: int,
    sample_rate: int,
    start_sec: float,
    gain: float,
    loop_audio: bool,
) -> np.ndarray:
    source_audio = _decode_audio_file(str(audio_path.resolve()), sample_rate)
    if source_audio.size == 0:
        return np.zeros((sample_count, 2), dtype=np.float32)

    source_length = source_audio.shape[0]
    start_sample = max(0, int(math.floor(start_sec * sample_rate)))
    if loop_audio:
        if source_length <= 0:
            return np.zeros((sample_count, 2), dtype=np.float32)
        tiled = np.zeros((sample_count, 2), dtype=np.float32)
        cursor = 0
        offset = start_sample % source_length
        while cursor < sample_count:
            chunk = source_audio[offset:] if offset else source_audio
            copy_count = min(sample_count - cursor, chunk.shape[0])
            tiled[cursor : cursor + copy_count] = chunk[:copy_count]
            cursor += copy_count
            offset = 0
        return tiled * gain

    if start_sample >= source_length:
        return np.zeros((sample_count, 2), dtype=np.float32)

    sliced = source_audio[start_sample : start_sample + sample_count]
    if sliced.shape[0] == sample_count:
        return sliced * gain

    padded = np.zeros((sample_count, 2), dtype=np.float32)
    padded[: sliced.shape[0]] = sliced
    return padded * gain


@lru_cache(maxsize=6)
def _decode_audio_file(path_str: str, sample_rate: int) -> np.ndarray:
    ffmpeg_exe = get_ffmpeg_exe()
    command = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        path_str,
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "2",
        "-ar",
        str(sample_rate),
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"音声ファイルを読み込めませんでした: {stderr or path_str}")

    data = np.frombuffer(completed.stdout, dtype=np.float32)
    if data.size == 0:
        return np.zeros((0, 2), dtype=np.float32)
    frame_count = data.size // 2
    return data[: frame_count * 2].reshape(frame_count, 2).copy()


def _write_wave(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
