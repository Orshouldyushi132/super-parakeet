from __future__ import annotations

import json
from pathlib import Path

from .models import (
    CUSTOM_THEME_NAME,
    RenderSettings,
    ThemePreset,
    THEME_PRESETS,
    render_settings_from_mapping,
    render_settings_to_dict,
)


PRESET_STORAGE_DIR = Path.home() / ".midi_measure_video_exporter"
PRESET_STORAGE_FILE = PRESET_STORAGE_DIR / "user_presets.json"
BUILT_IN_THEME_NAMES = {preset.name for preset in THEME_PRESETS}


def list_user_presets() -> tuple[ThemePreset, ...]:
    payload = _load_payload()
    presets: list[ThemePreset] = []
    for name, raw_settings in payload.get("presets", {}).items():
        if not isinstance(name, str):
            continue
        normalized_name = _normalize_preset_name(name)
        if not normalized_name or normalized_name in BUILT_IN_THEME_NAMES or normalized_name == CUSTOM_THEME_NAME:
            continue
        presets.append(
            ThemePreset(
                name=normalized_name,
                settings=render_settings_from_mapping(raw_settings),
            )
        )
    presets.sort(key=lambda preset: preset.name.casefold())
    return tuple(presets)


def list_all_presets() -> tuple[ThemePreset, ...]:
    return (*THEME_PRESETS, *list_user_presets())


def theme_name_choices() -> list[str]:
    return [preset.name for preset in list_all_presets()] + [CUSTOM_THEME_NAME]


def is_user_preset(name: str) -> bool:
    normalized_name = _normalize_preset_name(name)
    return any(preset.name == normalized_name for preset in list_user_presets())


def get_render_settings_for_name(name: str) -> RenderSettings | None:
    normalized_name = _normalize_preset_name(name)
    for preset in list_all_presets():
        if preset.name == normalized_name:
            return RenderSettings(**render_settings_to_dict(preset.settings))
    return None


def save_user_preset(name: str, settings: RenderSettings) -> str:
    normalized_name = _normalize_preset_name(name)
    if not normalized_name:
        raise ValueError("プリセット名を入力してください。")
    if normalized_name in BUILT_IN_THEME_NAMES:
        raise ValueError("組み込みプリセットと同じ名前は使えません。")
    if normalized_name == CUSTOM_THEME_NAME:
        raise ValueError("`カスタム` は予約名のため使えません。")

    payload = _load_payload()
    presets = payload.setdefault("presets", {})
    presets[normalized_name] = render_settings_to_dict(settings)
    _save_payload(payload)
    return normalized_name


def delete_user_preset(name: str) -> bool:
    normalized_name = _normalize_preset_name(name)
    payload = _load_payload()
    presets = payload.get("presets", {})
    if normalized_name not in presets:
        return False
    del presets[normalized_name]
    _save_payload(payload)
    return True


def presets_payload() -> dict[str, dict]:
    return {preset.name: render_settings_to_dict(preset.settings) for preset in list_all_presets()}


def preset_order() -> list[str]:
    return [preset.name for preset in list_all_presets()]


def user_preset_names() -> list[str]:
    return [preset.name for preset in list_user_presets()]


def _normalize_preset_name(name: str) -> str:
    return " ".join(str(name).strip().split())


def _load_payload() -> dict:
    if not PRESET_STORAGE_FILE.exists():
        return {"presets": {}}
    try:
        data = json.loads(PRESET_STORAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"presets": {}}
    if not isinstance(data, dict):
        return {"presets": {}}
    presets = data.get("presets")
    if not isinstance(presets, dict):
        data["presets"] = {}
    return data


def _save_payload(payload: dict) -> None:
    PRESET_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    PRESET_STORAGE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
