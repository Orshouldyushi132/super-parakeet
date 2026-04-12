from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict

import mido

from .models import ChordEvent, Measure, MidiProject, NoteEvent


@dataclass(slots=True)
class _RawNote:
    note: int
    velocity: int
    channel: int
    track: int
    start_tick: int
    end_tick: int


@dataclass(slots=True)
class _TempoSegment:
    start_tick: float
    start_sec: float
    tempo: int


class _TempoMap:
    def __init__(self, ticks_per_beat: int, tempo_changes: list[tuple[int, int]]) -> None:
        self.ticks_per_beat = ticks_per_beat
        sorted_changes = sorted(tempo_changes, key=lambda item: item[0])
        if not sorted_changes or sorted_changes[0][0] != 0:
            sorted_changes.insert(0, (0, 500000))

        normalized: list[tuple[int, int]] = []
        for tick, tempo in sorted_changes:
            if normalized and normalized[-1][0] == tick:
                normalized[-1] = (tick, tempo)
            else:
                normalized.append((tick, tempo))

        self._segments: list[_TempoSegment] = []
        current_sec = 0.0
        for index, (tick, tempo) in enumerate(normalized):
            if index > 0:
                previous_tick, previous_tempo = normalized[index - 1]
                current_sec += self._ticks_to_seconds_delta(tick - previous_tick, previous_tempo)
            self._segments.append(_TempoSegment(start_tick=float(tick), start_sec=current_sec, tempo=tempo))

        self._segment_starts = [segment.start_tick for segment in self._segments]

    def _ticks_to_seconds_delta(self, tick_delta: float, tempo: int) -> float:
        seconds_per_tick = tempo / 1_000_000 / self.ticks_per_beat
        return tick_delta * seconds_per_tick

    def tick_to_seconds(self, tick: float) -> float:
        index = bisect_right(self._segment_starts, tick) - 1
        if index < 0:
            index = 0
        segment = self._segments[index]
        return segment.start_sec + self._ticks_to_seconds_delta(tick - segment.start_tick, segment.tempo)


def load_midi_project(path: str | Path) -> MidiProject:
    midi_path = Path(path)
    midi = mido.MidiFile(midi_path)

    raw_notes: list[_RawNote] = []
    tempo_changes: list[tuple[int, int]] = [(0, 500000)]
    time_signature_changes: list[tuple[int, int, int]] = [(0, 4, 4)]

    for track_index, track in enumerate(midi.tracks):
        absolute_tick = 0
        open_notes: DefaultDict[tuple[int, int], deque[tuple[int, int]]] = defaultdict(deque)
        for message in track:
            absolute_tick += message.time

            if message.is_meta:
                if message.type == "set_tempo":
                    tempo_changes.append((absolute_tick, message.tempo))
                elif message.type == "time_signature":
                    time_signature_changes.append((absolute_tick, message.numerator, message.denominator))
                continue

            if message.type == "note_on" and message.velocity > 0:
                open_notes[(message.channel, message.note)].append((absolute_tick, message.velocity))
                continue

            if message.type not in {"note_off", "note_on"}:
                continue

            key = (message.channel, message.note)
            if not open_notes[key]:
                continue

            start_tick, velocity = open_notes[key].popleft()
            end_tick = max(start_tick + 1, absolute_tick)
            raw_notes.append(
                _RawNote(
                    note=message.note,
                    velocity=velocity,
                    channel=message.channel,
                    track=track_index,
                    start_tick=start_tick,
                    end_tick=end_tick,
                )
            )

        for (channel, note), note_stack in open_notes.items():
            while note_stack:
                start_tick, velocity = note_stack.popleft()
                raw_notes.append(
                    _RawNote(
                        note=note,
                        velocity=velocity,
                        channel=channel,
                        track=track_index,
                        start_tick=start_tick,
                        end_tick=max(start_tick + 1, absolute_tick),
                    )
                )

    if not raw_notes:
        raise ValueError("The selected MIDI file does not contain note events.")

    tempo_map = _TempoMap(midi.ticks_per_beat, tempo_changes)

    notes: list[NoteEvent] = []
    for raw_note in sorted(raw_notes, key=lambda item: (item.start_tick, item.note, item.track)):
        start_beat = raw_note.start_tick / midi.ticks_per_beat
        end_beat = raw_note.end_tick / midi.ticks_per_beat
        notes.append(
            NoteEvent(
                note=raw_note.note,
                velocity=raw_note.velocity,
                channel=raw_note.channel,
                track=raw_note.track,
                start_tick=raw_note.start_tick,
                end_tick=raw_note.end_tick,
                start_beat=start_beat,
                end_beat=end_beat,
                start_sec=tempo_map.tick_to_seconds(raw_note.start_tick),
                end_sec=tempo_map.tick_to_seconds(raw_note.end_tick),
            )
        )

    measures = _build_measures(
        tempo_map=tempo_map,
        ticks_per_beat=midi.ticks_per_beat,
        time_signature_changes=time_signature_changes,
        song_end_beat=max(note.end_beat for note in notes),
    )
    chords = _build_chord_events(notes)

    return MidiProject(
        source_path=midi_path,
        ticks_per_beat=midi.ticks_per_beat,
        notes=notes,
        measures=measures,
        chords=chords,
        min_note=min(note.note for note in notes),
        max_note=max(note.note for note in notes),
        duration_sec=measures[-1].end_sec,
    )


def _build_measures(
    tempo_map: _TempoMap,
    ticks_per_beat: int,
    time_signature_changes: list[tuple[int, int, int]],
    song_end_beat: float,
) -> list[Measure]:
    normalized_changes = sorted(
        {(tick, numerator, denominator) for tick, numerator, denominator in time_signature_changes},
        key=lambda item: item[0],
    )
    if not normalized_changes or normalized_changes[0][0] != 0:
        normalized_changes.insert(0, (0, 4, 4))

    beat_changes = [(tick / ticks_per_beat, numerator, denominator) for tick, numerator, denominator in normalized_changes]

    measures: list[Measure] = []
    current_beat = 0.0
    change_index = 0
    epsilon = 1e-9

    while current_beat < song_end_beat - epsilon:
        while change_index + 1 < len(beat_changes) and beat_changes[change_index + 1][0] <= current_beat + epsilon:
            change_index += 1

        _, numerator, denominator = beat_changes[change_index]
        measure_length_beats = numerator * 4.0 / denominator
        next_change_beat = beat_changes[change_index + 1][0] if change_index + 1 < len(beat_changes) else float("inf")
        next_beat = current_beat + measure_length_beats
        if next_change_beat < next_beat - epsilon:
            next_beat = next_change_beat

        measures.append(
            Measure(
                index=len(measures),
                start_beat=current_beat,
                end_beat=next_beat,
                start_sec=tempo_map.tick_to_seconds(current_beat * ticks_per_beat),
                end_sec=tempo_map.tick_to_seconds(next_beat * ticks_per_beat),
                numerator=numerator,
                denominator=denominator,
            )
        )
        current_beat = next_beat

    return measures


def _build_chord_events(notes: list[NoteEvent]) -> list[ChordEvent]:
    if not notes:
        return []

    epsilon = 1e-9
    indexed_notes = list(enumerate(notes))
    events = sorted(
        [
            (note.start_sec, note.start_beat, 1, index)
            for index, note in indexed_notes
        ]
        + [
            (note.end_sec, note.end_beat, -1, index)
            for index, note in indexed_notes
        ],
        key=lambda item: (item[0], item[2]),
    )

    grouped_events: list[tuple[float, float, list[int], list[int]]] = []
    cursor = 0
    while cursor < len(events):
        sec, beat, _, _ = events[cursor]
        starts: list[int] = []
        ends: list[int] = []
        while cursor < len(events) and abs(events[cursor][0] - sec) <= epsilon:
            _, event_beat, direction, note_index = events[cursor]
            beat = min(beat, event_beat)
            if direction < 0:
                ends.append(note_index)
            else:
                starts.append(note_index)
            cursor += 1
        grouped_events.append((sec, beat, starts, ends))

    active_note_indices: set[int] = set()
    chord_events: list[ChordEvent] = []
    for group_index, (sec, beat, starts, ends) in enumerate(grouped_events):
        for note_index in ends:
            active_note_indices.discard(note_index)
        for note_index in starts:
            active_note_indices.add(note_index)

        if group_index + 1 >= len(grouped_events):
            continue

        next_sec, next_beat, _, _ = grouped_events[group_index + 1]
        if next_sec <= sec + epsilon or not active_note_indices:
            continue

        active_pitches = sorted({notes[note_index].note for note_index in active_note_indices})
        chord_name, note_names = _detect_chord(active_pitches)
        if not chord_name:
            continue

        if chord_events and chord_events[-1].chord_name == chord_name and chord_events[-1].note_names == note_names:
            chord_events[-1].end_sec = next_sec
            chord_events[-1].end_beat = next_beat
            chord_events[-1].active_note_count = len(active_pitches)
            continue

        chord_events.append(
            ChordEvent(
                start_sec=sec,
                end_sec=next_sec,
                start_beat=beat,
                end_beat=next_beat,
                chord_name=chord_name,
                note_names=note_names,
                active_note_count=len(active_pitches),
            )
        )

    return chord_events


def _detect_chord(active_pitches: list[int]) -> tuple[str, tuple[str, ...]]:
    if not active_pitches:
        return "", ()

    unique_pitches = sorted(dict.fromkeys(active_pitches))
    note_names = tuple(_midi_note_name(pitch) for pitch in unique_pitches)
    pitch_classes = sorted({pitch % 12 for pitch in unique_pitches})
    bass_pc = unique_pitches[0] % 12

    if len(pitch_classes) == 1:
        return _pitch_class_name(bass_pc), note_names

    chord_patterns = (
        ("maj7", {0, 4, 7, 11}),
        ("m7", {0, 3, 7, 10}),
        ("7", {0, 4, 7, 10}),
        ("mMaj7", {0, 3, 7, 11}),
        ("dim7", {0, 3, 6, 9}),
        ("m7b5", {0, 3, 6, 10}),
        ("6", {0, 4, 7, 9}),
        ("m6", {0, 3, 7, 9}),
        ("add9", {0, 2, 4, 7}),
        ("madd9", {0, 2, 3, 7}),
        ("sus2", {0, 2, 7}),
        ("sus4", {0, 5, 7}),
        ("aug", {0, 4, 8}),
        ("dim", {0, 3, 6}),
        ("m", {0, 3, 7}),
        ("", {0, 4, 7}),
        ("5", {0, 7}),
    )

    best_score = float("-inf")
    best_name = ""
    for root_pc in pitch_classes:
        intervals = {(pitch_class - root_pc) % 12 for pitch_class in pitch_classes}
        for suffix, pattern in chord_patterns:
            if not pattern.issubset(intervals):
                continue
            extras = len(intervals - pattern)
            bass_bonus = 3 if bass_pc == root_pc else 0
            score = len(pattern) * 12 - extras * 4 + bass_bonus
            if score <= best_score:
                continue

            chord_name = f"{_pitch_class_name(root_pc)}{suffix}"
            if bass_pc != root_pc:
                chord_name = f"{chord_name}/{_pitch_class_name(bass_pc)}"
            best_score = score
            best_name = chord_name

    if best_name:
        return best_name, note_names
    return "N.C.", note_names


def _pitch_class_name(pitch_class: int) -> str:
    names = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    return names[pitch_class % 12]


def _midi_note_name(note_number: int) -> str:
    octave = note_number // 12 - 1
    return f"{_pitch_class_name(note_number)}{octave}"
