from __future__ import annotations

from dataclasses import dataclass
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
