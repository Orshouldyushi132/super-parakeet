from __future__ import annotations

import argparse
import io
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from .exporter import export_video
from .midi_loader import load_midi_project
from .models import (
    AFTERIMAGE_STYLE_CHOICES,
    ANIMATION_STYLE_CHOICES,
    CORNER_STYLE_CHOICES,
    CUSTOM_THEME_NAME,
    DEFAULT_THEME_NAME,
    GLOW_STYLE_CHOICES,
    RELEASE_FADE_CURVE_CHOICES,
    RELEASE_FADE_STYLE_CHOICES,
    MidiProject,
    get_render_settings_for_theme,
    render_settings_from_mapping,
    render_settings_to_dict,
)
from .preset_store import (
    delete_user_preset,
    preset_order,
    presets_payload,
    save_user_preset,
    theme_name_choices,
    user_preset_names,
)
from .renderer import ProjectRenderer


WEB_ROOT = Path(__file__).with_name("web")
TEMP_ROOT = Path(tempfile.gettempdir()) / "midi_measure_video_exporter"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(WEB_ROOT / "templates"),
    static_folder=str(WEB_ROOT / "static"),
)


@dataclass(slots=True)
class _StoredProject:
    project_id: str
    original_name: str
    source_path: Path
    project: MidiProject


_PROJECTS: dict[str, _StoredProject] = {}


@app.get("/")
def index():
    bootstrap = {
        "defaultTheme": DEFAULT_THEME_NAME,
        "customTheme": CUSTOM_THEME_NAME,
        "defaultFps": 120,
        "defaultSettings": render_settings_to_dict(get_render_settings_for_theme(DEFAULT_THEME_NAME)),
        "themePresets": presets_payload(),
        "themeOrder": preset_order(),
        "userThemeNames": user_preset_names(),
        "choices": {
            "themes": theme_name_choices(),
            "corners": _choices_to_payload(CORNER_STYLE_CHOICES),
            "glows": _choices_to_payload(GLOW_STYLE_CHOICES),
            "animations": _choices_to_payload(ANIMATION_STYLE_CHOICES),
            "afterimages": _choices_to_payload(AFTERIMAGE_STYLE_CHOICES),
            "releaseFadeStyles": _choices_to_payload(RELEASE_FADE_STYLE_CHOICES),
            "releaseFadeCurves": _choices_to_payload(RELEASE_FADE_CURVE_CHOICES),
        },
    }
    return render_template("index.html", bootstrap=bootstrap)


@app.post("/api/projects")
def create_project():
    midi_file = request.files.get("file")
    if not midi_file or not midi_file.filename:
        return jsonify({"error": "MIDIファイルを選択してください。"}), 400

    original_name = Path(midi_file.filename).name
    safe_name = secure_filename(original_name) or "upload.mid"
    suffix = Path(safe_name).suffix or ".mid"
    project_id = uuid.uuid4().hex
    source_path = TEMP_ROOT / f"{project_id}{suffix}"
    midi_file.save(source_path)

    try:
        project = load_midi_project(source_path)
    except Exception as error:
        source_path.unlink(missing_ok=True)
        return jsonify({"error": str(error)}), 400

    _PROJECTS[project_id] = _StoredProject(
        project_id=project_id,
        original_name=original_name,
        source_path=source_path,
        project=project,
    )

    return jsonify(
        {
            "projectId": project_id,
            "fileName": original_name,
            "durationSec": project.duration_sec,
            "measureCount": project.measure_count,
            "measures": [
                {
                    "index": measure.index,
                    "startSec": measure.start_sec,
                    "endSec": measure.end_sec,
                    "numerator": measure.numerator,
                    "denominator": measure.denominator,
                }
                for measure in project.measures
            ],
        }
    )


@app.post("/api/presets")
def create_preset():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", ""))
    settings = render_settings_from_mapping(payload.get("settings"))
    try:
        normalized_name = save_user_preset(name, settings)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify(
        {
            "savedName": normalized_name,
            "themePresets": presets_payload(),
            "themeOrder": preset_order(),
            "userThemeNames": user_preset_names(),
            "choices": {"themes": theme_name_choices()},
        }
    )


@app.delete("/api/presets/<path:preset_name>")
def remove_preset(preset_name: str):
    if not delete_user_preset(preset_name):
        return jsonify({"error": "保存済みプリセットが見つかりません。"}), 404

    return jsonify(
        {
            "themePresets": presets_payload(),
            "themeOrder": preset_order(),
            "userThemeNames": user_preset_names(),
            "choices": {"themes": theme_name_choices()},
        }
    )


@app.post("/api/projects/<project_id>/preview")
def preview_project(project_id: str):
    stored_project = _PROJECTS.get(project_id)
    if not stored_project:
        return jsonify({"error": "MIDIが見つかりません。再読み込みしてください。"}), 404

    payload = request.get_json(silent=True) or {}
    settings = render_settings_from_mapping(payload.get("settings"))
    width = _coerce_int(payload.get("width"), 960, 240, 1920)
    height = _coerce_int(payload.get("height"), 540, 180, 1080)
    time_sec = _coerce_float(payload.get("timeSec"), 0.0, 0.0, stored_project.project.duration_sec)

    renderer = ProjectRenderer(stored_project.project, settings)
    frame = renderer.render_frame(time_sec, width, height)

    buffer = io.BytesIO()
    frame.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png", max_age=0)


@app.post("/api/projects/<project_id>/export")
def export_project(project_id: str):
    stored_project = _PROJECTS.get(project_id)
    if not stored_project:
        return jsonify({"error": "MIDIが見つかりません。再読み込みしてください。"}), 404

    payload = request.get_json(silent=True) or {}
    settings = render_settings_from_mapping(payload.get("settings"))
    fps = _coerce_int(payload.get("fps"), 120, 1, 240)
    width = _coerce_int(payload.get("width"), 1920, 320, 3840)
    height = _coerce_int(payload.get("height"), 1080, 180, 2160)

    output_path = TEMP_ROOT / f"{project_id}_{uuid.uuid4().hex}.mp4"
    renderer = ProjectRenderer(stored_project.project, settings)
    export_video(
        project=stored_project.project,
        renderer=renderer,
        output_path=output_path,
        width=width,
        height=height,
        fps=fps,
    )

    download_name = f"{Path(stored_project.original_name).stem}_小節切り替え.mp4"
    response = send_file(output_path, as_attachment=True, download_name=download_name, mimetype="video/mp4")
    response.call_on_close(lambda: output_path.unlink(missing_ok=True))
    return response


def _choices_to_payload(choices: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in choices]


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _coerce_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def main() -> None:
    parser = argparse.ArgumentParser(description="MIDI小節切り替え動画ツールのブラウザ版を起動します。")
    parser.add_argument("--host", default="127.0.0.1", help="待ち受けホスト。スマホから使うなら 0.0.0.0 を指定します。")
    parser.add_argument("--port", type=int, default=8000, help="待ち受けポート番号。")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
