from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .models import Measure, MidiProject, NoteEvent


BACKGROUND_COLOR = "#000000"
IDLE_NOTE_COLOR = "#2f2f2f"
ACTIVE_NOTE_COLOR = "#ffffff"


@dataclass(slots=True)
class _VisibleSegment:
    note: int
    start_ratio: float
    end_ratio: float
    note_start_sec: float
    note_end_sec: float


class MeasureRenderer:
    def __init__(self, project: MidiProject) -> None:
        self.project = project
        self._measure_start_seconds = [measure.start_sec for measure in project.measures]
        self._measure_segments = self._build_measure_segments(project)

    def get_measure_for_time(self, time_sec: float) -> Measure:
        if time_sec <= 0:
            return self.project.measures[0]
        index = bisect_right(self._measure_start_seconds, time_sec) - 1
        if index < 0:
            index = 0
        if index >= len(self.project.measures):
            index = len(self.project.measures) - 1
        return self.project.measures[index]

    def render_frame(self, time_sec: float, width: int, height: int) -> Image.Image:
        clamped_time = max(0.0, min(time_sec, max(self.project.duration_sec - 1e-6, 0.0)))
        measure = self.get_measure_for_time(clamped_time)
        note_segments = self._measure_segments[measure.index]

        image = Image.new("RGB", (width, height), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)

        left_padding = width * 0.045
        right_padding = width * 0.045
        top_padding = height * 0.08
        bottom_padding = height * 0.08

        plot_width = max(1.0, width - left_padding - right_padding)
        plot_height = max(1.0, height - top_padding - bottom_padding)

        note_range = max(1, self.project.max_note - self.project.min_note + 1)
        lane_height = plot_height / note_range
        rectangle_height = max(2.0, lane_height * 0.6)
        min_rectangle_width = max(2.0, width * 0.001)

        for segment in note_segments:
            x0 = left_padding + plot_width * segment.start_ratio
            x1 = left_padding + plot_width * segment.end_ratio
            if x1 - x0 < min_rectangle_width:
                x1 = x0 + min_rectangle_width

            pitch_index = self.project.max_note - segment.note
            lane_top = top_padding + pitch_index * lane_height
            y0 = lane_top + (lane_height - rectangle_height) / 2.0
            y1 = y0 + rectangle_height

            color = ACTIVE_NOTE_COLOR if segment.note_start_sec <= clamped_time < segment.note_end_sec else IDLE_NOTE_COLOR
            draw.rectangle((x0, y0, x1, y1), fill=color)

        return image

    def _build_measure_segments(self, project: MidiProject) -> list[list[_VisibleSegment]]:
        segments_by_measure: list[list[_VisibleSegment]] = [[] for _ in project.measures]
        measure_starts = [measure.start_beat for measure in project.measures]
        epsilon = 1e-9

        for note in project.notes:
            measure_index = bisect_right(measure_starts, note.start_beat) - 1
            if measure_index < 0:
                measure_index = 0

            while measure_index < len(project.measures):
                measure = project.measures[measure_index]
                if note.end_beat <= measure.start_beat + epsilon:
                    break
                if note.start_beat >= measure.end_beat - epsilon:
                    measure_index += 1
                    continue

                overlap_start = max(note.start_beat, measure.start_beat)
                overlap_end = min(note.end_beat, measure.end_beat)
                start_ratio = (overlap_start - measure.start_beat) / max(measure.length_beats, epsilon)
                end_ratio = (overlap_end - measure.start_beat) / max(measure.length_beats, epsilon)

                segments_by_measure[measure.index].append(
                    _VisibleSegment(
                        note=note.note,
                        start_ratio=max(0.0, min(1.0, start_ratio)),
                        end_ratio=max(0.0, min(1.0, end_ratio)),
                        note_start_sec=note.start_sec,
                        note_end_sec=note.end_sec,
                    )
                )

                if note.end_beat <= measure.end_beat + epsilon:
                    break
                measure_index += 1

        for measure_segments in segments_by_measure:
            measure_segments.sort(key=lambda segment: (segment.note, segment.start_ratio, segment.end_ratio))

        return segments_by_measure
