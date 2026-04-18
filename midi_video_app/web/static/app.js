const boot = window.APP_BOOTSTRAP || {};

const DEFAULT_EXPORT_FPS = Number(boot.defaultFps) || 120;
const DEFAULT_EXPORT_FORMAT = boot.defaultExportFormat || "h264";
const DEFAULT_EXPORT_ORIENTATION = boot.defaultExportOrientation || "landscape";
const MAX_EXPORT_FPS = 240;
const PREVIEW_INPUT_DEBOUNCE_MS = 16;
const PREVIEW_FRAME_INTERVAL_MS = 16;

const state = {
  projectId: null,
  fileName: "",
  durationSec: 0,
  measures: [],
  currentTime: 0,
  playing: false,
  playbackStartedAt: 0,
  playbackOriginSec: 0,
  previewBusy: false,
  previewQueued: false,
  previewUrl: null,
  lastPreviewAt: 0,
  previewTimer: null,
};

const elements = {
  fileInput: document.getElementById("midiFileInput"),
  exportButton: document.getElementById("exportButton"),
  fileName: document.getElementById("fileName"),
  statusText: document.getElementById("statusText"),
  previewImage: document.getElementById("previewImage"),
  previewEmpty: document.getElementById("previewEmpty"),
  previewFrame: document.getElementById("previewFrame"),
  playButton: document.getElementById("playButton"),
  stopButton: document.getElementById("stopButton"),
  prevMeasureButton: document.getElementById("prevMeasureButton"),
  nextMeasureButton: document.getElementById("nextMeasureButton"),
  timelineRange: document.getElementById("timelineRange"),
  timeText: document.getElementById("timeText"),
  measureText: document.getElementById("measureText"),
  themeBadge: document.getElementById("themeBadge"),
  themePresetGrid: document.getElementById("themePresetGrid"),
  presetNameInput: document.getElementById("presetNameInput"),
  savePresetButton: document.getElementById("savePresetButton"),
  deletePresetButton: document.getElementById("deletePresetButton"),
  themeSelect: document.getElementById("themeSelect"),
  exportFormatSelect: document.getElementById("exportFormatSelect"),
  exportOrientationSelect: document.getElementById("exportOrientationSelect"),
  exportResolutionSelect: document.getElementById("exportResolutionSelect"),
  exportResolutionSummary: document.getElementById("exportResolutionSummary"),
  exportHintText: document.getElementById("exportHintText"),
  viewModeSelect: document.getElementById("viewModeSelect"),
  fontFamilySelect: document.getElementById("fontFamilySelect"),
  customFontPathInput: document.getElementById("customFontPathInput"),
  cornerStyleSelect: document.getElementById("cornerStyleSelect"),
  glowStyleSelect: document.getElementById("glowStyleSelect"),
  animationStyleSelect: document.getElementById("animationStyleSelect"),
  afterimageStyleSelect: document.getElementById("afterimageStyleSelect"),
  releaseFadeStyleSelect: document.getElementById("releaseFadeStyleSelect"),
  releaseFadeCurveSelect: document.getElementById("releaseFadeCurveSelect"),
  hideFutureNotesCheckbox: document.getElementById("hideFutureNotesCheckbox"),
  showPlayheadCheckbox: document.getElementById("showPlayheadCheckbox"),
  showTimeOverlayCheckbox: document.getElementById("showTimeOverlayCheckbox"),
  showMeasureOverlayCheckbox: document.getElementById("showMeasureOverlayCheckbox"),
  showStatsOverlayCheckbox: document.getElementById("showStatsOverlayCheckbox"),
  showChordOverlayCheckbox: document.getElementById("showChordOverlayCheckbox"),
  transparentBackgroundCheckbox: document.getElementById("transparentBackgroundCheckbox"),
  fitToVisibleNoteRangeCheckbox: document.getElementById("fitToVisibleNoteRangeCheckbox"),
  backgroundColorInput: document.getElementById("backgroundColorInput"),
  idleNoteColorInput: document.getElementById("idleNoteColorInput"),
  activeNoteColorInput: document.getElementById("activeNoteColorInput"),
  glowColorInput: document.getElementById("glowColorInput"),
  animationAccentColorInput: document.getElementById("animationAccentColorInput"),
  outlineColorInput: document.getElementById("outlineColorInput"),
  textColorInput: document.getElementById("textColorInput"),
  visibleMeasureCountInput: document.getElementById("visibleMeasureCountInput"),
  noteLengthScaleInput: document.getElementById("noteLengthScaleInput"),
  noteHeightScaleInput: document.getElementById("noteHeightScaleInput"),
  horizontalPaddingInput: document.getElementById("horizontalPaddingInput"),
  verticalPaddingInput: document.getElementById("verticalPaddingInput"),
  glowStrengthInput: document.getElementById("glowStrengthInput"),
  animationStrengthInput: document.getElementById("animationStrengthInput"),
  animationSpeedInput: document.getElementById("animationSpeedInput"),
  afterimageStrengthInput: document.getElementById("afterimageStrengthInput"),
  idleOutlineWidthInput: document.getElementById("idleOutlineWidthInput"),
  activeOutlineWidthInput: document.getElementById("activeOutlineWidthInput"),
  afterimageOutlineWidthInput: document.getElementById("afterimageOutlineWidthInput"),
  afterimageDurationInput: document.getElementById("afterimageDurationInput"),
  afterimagePaddingInput: document.getElementById("afterimagePaddingInput"),
  releaseFadeDurationInput: document.getElementById("releaseFadeDurationInput"),
  visibleMeasureCountValue: document.getElementById("visibleMeasureCountValue"),
  noteLengthScaleValue: document.getElementById("noteLengthScaleValue"),
  noteHeightScaleValue: document.getElementById("noteHeightScaleValue"),
  horizontalPaddingValue: document.getElementById("horizontalPaddingValue"),
  verticalPaddingValue: document.getElementById("verticalPaddingValue"),
  glowStrengthValue: document.getElementById("glowStrengthValue"),
  animationStrengthValue: document.getElementById("animationStrengthValue"),
  animationSpeedValue: document.getElementById("animationSpeedValue"),
  afterimageStrengthValue: document.getElementById("afterimageStrengthValue"),
  idleOutlineWidthValue: document.getElementById("idleOutlineWidthValue"),
  activeOutlineWidthValue: document.getElementById("activeOutlineWidthValue"),
  afterimageOutlineWidthValue: document.getElementById("afterimageOutlineWidthValue"),
  afterimageDurationValue: document.getElementById("afterimageDurationValue"),
  afterimagePaddingValue: document.getElementById("afterimagePaddingValue"),
  releaseFadeDurationValue: document.getElementById("releaseFadeDurationValue"),
  fpsInput: document.getElementById("fpsInput"),
};

const settingBindings = {
  background_color: elements.backgroundColorInput,
  idle_note_color: elements.idleNoteColorInput,
  active_note_color: elements.activeNoteColorInput,
  glow_color: elements.glowColorInput,
  animation_accent_color: elements.animationAccentColorInput,
  outline_color: elements.outlineColorInput,
  text_color: elements.textColorInput,
  view_mode: elements.viewModeSelect,
  font_family: elements.fontFamilySelect,
  custom_font_path: elements.customFontPathInput,
  corner_style: elements.cornerStyleSelect,
  glow_style: elements.glowStyleSelect,
  animation_style: elements.animationStyleSelect,
  afterimage_style: elements.afterimageStyleSelect,
  release_fade_style: elements.releaseFadeStyleSelect,
  release_fade_curve: elements.releaseFadeCurveSelect,
  visible_measure_count: elements.visibleMeasureCountInput,
  hide_future_notes: elements.hideFutureNotesCheckbox,
  show_time_overlay: elements.showTimeOverlayCheckbox,
  show_measure_overlay: elements.showMeasureOverlayCheckbox,
  show_stats_overlay: elements.showStatsOverlayCheckbox,
  show_chord_overlay: elements.showChordOverlayCheckbox,
  show_playhead: elements.showPlayheadCheckbox,
  transparent_background: elements.transparentBackgroundCheckbox,
  fit_to_visible_note_range: elements.fitToVisibleNoteRangeCheckbox,
  glow_strength: elements.glowStrengthInput,
  animation_strength: elements.animationStrengthInput,
  animation_speed: elements.animationSpeedInput,
  afterimage_strength: elements.afterimageStrengthInput,
  note_length_scale: elements.noteLengthScaleInput,
  note_height_scale: elements.noteHeightScaleInput,
  horizontal_padding_ratio: elements.horizontalPaddingInput,
  vertical_padding_ratio: elements.verticalPaddingInput,
  idle_outline_width: elements.idleOutlineWidthInput,
  active_outline_width: elements.activeOutlineWidthInput,
  afterimage_outline_width: elements.afterimageOutlineWidthInput,
  afterimage_duration_sec: elements.afterimageDurationInput,
  afterimage_padding_scale: elements.afterimagePaddingInput,
  release_fade_duration_sec: elements.releaseFadeDurationInput,
};

const scaledSettingFields = new Set([
  "glow_strength",
  "animation_strength",
  "animation_speed",
  "afterimage_strength",
  "note_length_scale",
  "note_height_scale",
  "horizontal_padding_ratio",
  "vertical_padding_ratio",
  "idle_outline_width",
  "active_outline_width",
  "afterimage_outline_width",
  "afterimage_duration_sec",
  "afterimage_padding_scale",
  "release_fade_duration_sec",
]);

const integerSettingFields = new Set(["visible_measure_count"]);

const booleanSettingFields = new Set([
  "hide_future_notes",
  "show_time_overlay",
  "show_measure_overlay",
  "show_stats_overlay",
  "show_chord_overlay",
  "show_playhead",
  "transparent_background",
  "fit_to_visible_note_range",
]);

const exportResolutionPresets = Array.isArray(boot.exportResolutions) ? boot.exportResolutions : [];
const exportResolutionMap = new Map(exportResolutionPresets.map((preset) => [preset.value, preset]));
const defaultExportResolution = boot.defaultExportResolution || exportResolutionPresets[0]?.value || "4k";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function getSelectedExportFormat() {
  return elements.exportFormatSelect.value || DEFAULT_EXPORT_FORMAT;
}

function getSelectedExportOrientation() {
  return elements.exportOrientationSelect.value || DEFAULT_EXPORT_ORIENTATION;
}

function getSelectedExportPreset() {
  return exportResolutionMap.get(elements.exportResolutionSelect.value)
    || exportResolutionMap.get(defaultExportResolution)
    || {
      value: "4k",
      label: "4K",
      landscapeWidth: 3840,
      landscapeHeight: 2160,
      portraitWidth: 2160,
      portraitHeight: 3840,
    };
}

function getSelectedExportDimensions() {
  const preset = getSelectedExportPreset();
  if (getSelectedExportOrientation() === "portrait") {
    return {
      width: preset.portraitWidth,
      height: preset.portraitHeight,
    };
  }
  return {
    width: preset.landscapeWidth,
    height: preset.landscapeHeight,
  };
}

function updatePreviewAspect() {
  const { width, height } = getSelectedExportDimensions();
  elements.previewFrame.style.aspectRatio = `${width} / ${height}`;
}

function syncExportUiState({ queue = false } = {}) {
  const exportFormat = getSelectedExportFormat();
  const exportOrientation = getSelectedExportOrientation();
  const { width, height } = getSelectedExportDimensions();
  const allowTransparency = exportFormat === "mov" || exportFormat === "webm_vp9" || exportFormat === "png_sequence";
  if (!allowTransparency) {
    elements.transparentBackgroundCheckbox.checked = false;
  }
  elements.transparentBackgroundCheckbox.disabled = !allowTransparency;
  elements.exportResolutionSummary.textContent = `${width} x ${height} / ${exportOrientation === "portrait" ? "縦動画" : "横動画"}`;
  if (exportFormat === "mov") {
    elements.exportButton.textContent = "MOVを書き出し";
    elements.exportHintText.textContent = "MOV は背景透過ありでも書き出せます。編集ソフト向けに使いやすい形式です。";
  } else if (exportFormat === "webm_vp9") {
    elements.exportButton.textContent = "WebM VP9を書き出し";
    elements.exportHintText.textContent = "WebM VP9 は背景透過に対応した圧縮動画です。Windows では Edge / Chrome などで確認しやすい形式です。";
  } else if (exportFormat === "png_sequence") {
    elements.exportButton.textContent = "連番PNGを書き出し";
    elements.exportHintText.textContent = "連番PNGは1フレームずつ保存します。背景透過にも対応します。";
  } else {
    elements.exportButton.textContent = "H.264を書き出し";
    elements.exportHintText.textContent = "H.264 は MP4 で書き出します。背景透過は使えません。";
  }
  updatePreviewAspect();
  if (queue) {
    queuePreview(true);
  }
}

function populateSelect(select, items, selectedValue) {
  select.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    if (typeof item === "string") {
      option.value = item;
      option.textContent = item;
    } else {
      option.value = item.value;
      option.textContent = item.label;
    }
    option.selected = option.value === selectedValue;
    select.appendChild(option);
  });
}

function wrapViewTransition(update) {
  if ("startViewTransition" in document) {
    document.startViewTransition(update);
    return;
  }
  update();
}

function hexToRgbString(hex) {
  const normalized = String(hex || "").replace("#", "");
  const full = normalized.length === 3
    ? normalized.split("").map((value) => value + value).join("")
    : normalized.padEnd(6, "0").slice(0, 6);
  const values = [0, 2, 4].map((index) => Number.parseInt(full.slice(index, index + 2), 16));
  return values.join(" ");
}

function getThemeOrder() {
  if (Array.isArray(boot.themeOrder) && boot.themeOrder.length) {
    return boot.themeOrder;
  }
  return Object.keys(boot.themePresets || {});
}

function getUserThemeNames() {
  return Array.isArray(boot.userThemeNames) ? boot.userThemeNames : [];
}

function isUserTheme(themeName) {
  return getUserThemeNames().includes(themeName);
}

function syncThemeAtmosphere(settings) {
  const rootStyle = document.documentElement.style;
  rootStyle.setProperty("--theme-bg-rgb", hexToRgbString(settings.background_color));
  rootStyle.setProperty("--theme-idle-rgb", hexToRgbString(settings.idle_note_color));
  rootStyle.setProperty("--theme-active-rgb", hexToRgbString(settings.active_note_color));
  rootStyle.setProperty("--theme-glow-rgb", hexToRgbString(settings.glow_color));
  rootStyle.setProperty("--theme-accent-rgb", hexToRgbString(settings.animation_accent_color));
  rootStyle.setProperty("--theme-outline-rgb", hexToRgbString(settings.outline_color));
}

function syncSliderLabels() {
  elements.visibleMeasureCountValue.textContent = `${elements.visibleMeasureCountInput.value}小節`;
  elements.noteLengthScaleValue.textContent = `${elements.noteLengthScaleInput.value}%`;
  elements.noteHeightScaleValue.textContent = `${elements.noteHeightScaleInput.value}%`;
  elements.horizontalPaddingValue.textContent = `${elements.horizontalPaddingInput.value}%`;
  elements.verticalPaddingValue.textContent = `${elements.verticalPaddingInput.value}%`;
  elements.glowStrengthValue.textContent = `${elements.glowStrengthInput.value}%`;
  elements.animationStrengthValue.textContent = `${elements.animationStrengthInput.value}%`;
  elements.animationSpeedValue.textContent = `${elements.animationSpeedInput.value}%`;
  elements.afterimageStrengthValue.textContent = `${elements.afterimageStrengthInput.value}%`;
  elements.idleOutlineWidthValue.textContent = `${(Number(elements.idleOutlineWidthInput.value) / 100).toFixed(2)}x`;
  elements.activeOutlineWidthValue.textContent = `${(Number(elements.activeOutlineWidthInput.value) / 100).toFixed(2)}x`;
  elements.afterimageOutlineWidthValue.textContent = `${(Number(elements.afterimageOutlineWidthInput.value) / 100).toFixed(2)}x`;
  elements.afterimageDurationValue.textContent = `${(Number(elements.afterimageDurationInput.value) / 100).toFixed(2)}秒`;
  elements.afterimagePaddingValue.textContent = `${(Number(elements.afterimagePaddingInput.value) / 100).toFixed(2)}x`;
  elements.releaseFadeDurationValue.textContent = `${(Number(elements.releaseFadeDurationInput.value) / 100).toFixed(2)}秒`;
}

function updateThemeBadge() {
  const themeName = elements.themeSelect.value || boot.defaultTheme;
  elements.themeBadge.textContent = themeName;
  elements.themeBadge.dataset.mode = themeName === boot.customTheme
    ? "custom"
    : isUserTheme(themeName)
      ? "saved"
      : "builtin";
}

function highlightActivePreset() {
  const currentTheme = elements.themeSelect.value;
  elements.themePresetGrid.querySelectorAll(".preset-card").forEach((card) => {
    const active = card.dataset.theme === currentTheme;
    card.classList.toggle("is-active", active);
    card.setAttribute("aria-pressed", String(active));
  });
}

function updatePresetActionState() {
  const currentTheme = elements.themeSelect.value;
  elements.deletePresetButton.disabled = !isUserTheme(currentTheme);
}

function applySettings(settings) {
  Object.entries(settingBindings).forEach(([fieldName, element]) => {
    const value = settings[fieldName];
    if (booleanSettingFields.has(fieldName)) {
      element.checked = Boolean(value);
      return;
    }
    if (integerSettingFields.has(fieldName)) {
      element.value = String(Math.round(Number(value)));
      return;
    }
    if (scaledSettingFields.has(fieldName)) {
      element.value = Math.round(Number(value) * 100);
      return;
    }
    element.value = value;
  });

  syncSliderLabels();
  syncThemeAtmosphere(settings);
  updateThemeBadge();
  highlightActivePreset();
  updatePresetActionState();
  syncExportUiState();
}

function collectSettings() {
  return Object.fromEntries(
    Object.entries(settingBindings).map(([fieldName, element]) => {
      if (booleanSettingFields.has(fieldName)) {
        return [fieldName, Boolean(element.checked)];
      }
      if (integerSettingFields.has(fieldName)) {
        return [fieldName, Math.round(Number(element.value))];
      }
      if (scaledSettingFields.has(fieldName)) {
        return [fieldName, Number(element.value) / 100];
      }
      return [fieldName, element.value];
    }),
  );
}

function setStatus(message) {
  elements.statusText.textContent = message;
}

function refreshThemeChoices(selectedTheme) {
  populateSelect(elements.themeSelect, boot.choices.themes || [], selectedTheme);
  if (!Array.from(elements.themeSelect.options).some((option) => option.value === selectedTheme)) {
    elements.themeSelect.value = boot.defaultTheme;
  }
}

function markCustomTheme() {
  if (elements.themeSelect.value !== boot.customTheme) {
    elements.themeSelect.value = boot.customTheme;
  }
  updateThemeBadge();
  highlightActivePreset();
  updatePresetActionState();
}

function syncSelectionToTheme(themeName) {
  elements.themeSelect.value = themeName;
  elements.presetNameInput.value = isUserTheme(themeName) ? themeName : "";
  applySettings(boot.themePresets[themeName] || boot.defaultSettings);
}

function syncPresetBootstrap(payload) {
  if (payload.themePresets) {
    boot.themePresets = payload.themePresets;
  }
  if (payload.themeOrder) {
    boot.themeOrder = payload.themeOrder;
  }
  if (payload.userThemeNames) {
    boot.userThemeNames = payload.userThemeNames;
  }
  if (payload.choices?.themes) {
    boot.choices.themes = payload.choices.themes;
  }
}

function renderPresetCards() {
  elements.themePresetGrid.innerHTML = "";

  getThemeOrder().forEach((themeName) => {
    const settings = boot.themePresets[themeName];
    if (!settings) {
      return;
    }

    const isSaved = isUserTheme(themeName);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset-card";
    button.dataset.theme = themeName;
    button.setAttribute("aria-pressed", "false");
    button.innerHTML = `
      <div class="preset-card-header">
        <div>
          <span class="preset-card-title">${escapeHtml(themeName)}</span>
          <span class="preset-card-subtitle">${isSaved ? "保存済みプリセットです。" : "標準プリセットです。"}</span>
        </div>
        <div class="preset-card-meta">
          <span class="preset-card-pill ${isSaved ? "user" : "builtin"}">${isSaved ? "保存済み" : "標準"}</span>
        </div>
      </div>
      <div class="preset-swatches">
        <span class="preset-swatch" style="background:${settings.background_color}"></span>
        <span class="preset-swatch" style="background:${settings.glow_color}"></span>
        <span class="preset-swatch" style="background:${settings.animation_accent_color}"></span>
        <span class="preset-swatch" style="background:${settings.active_note_color}"></span>
      </div>
    `;
    button.addEventListener("click", () => {
      wrapViewTransition(() => {
        syncSelectionToTheme(themeName);
      });
      queuePreview(true);
    });
    elements.themePresetGrid.appendChild(button);
  });

  highlightActivePreset();
}

async function saveCurrentPreset() {
  const presetName = elements.presetNameInput.value.trim();
  if (!presetName) {
    window.alert("保存するプリセット名を入力してください。");
    elements.presetNameInput.focus();
    return;
  }

  if (isUserTheme(presetName) && !window.confirm(`「${presetName}」を上書き保存しますか？`)) {
    return;
  }

  elements.savePresetButton.disabled = true;
  try {
    const response = await fetch("/api/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: presetName, settings: collectSettings() }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "プリセットの保存に失敗しました。");
    }
    syncPresetBootstrap(payload);
    wrapViewTransition(() => {
      refreshThemeChoices(payload.savedName);
      renderPresetCards();
      syncSelectionToTheme(payload.savedName);
    });
    setStatus(`プリセット「${payload.savedName}」を保存しました。`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    elements.savePresetButton.disabled = false;
  }
}

async function deleteSelectedPreset() {
  const presetName = elements.themeSelect.value;
  if (!isUserTheme(presetName)) {
    setStatus("削除できるのは保存済みプリセットだけです。");
    return;
  }

  if (!window.confirm(`「${presetName}」を削除しますか？`)) {
    return;
  }

  elements.deletePresetButton.disabled = true;
  try {
    const response = await fetch(`/api/presets/${encodeURIComponent(presetName)}`, { method: "DELETE" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "プリセットの削除に失敗しました。");
    }
    syncPresetBootstrap(payload);
    wrapViewTransition(() => {
      refreshThemeChoices(boot.defaultTheme);
      renderPresetCards();
      syncSelectionToTheme(boot.defaultTheme);
    });
    setStatus(`プリセット「${presetName}」を削除しました。`);
    queuePreview(true);
  } catch (error) {
    setStatus(error.message);
  } finally {
    updatePresetActionState();
  }
}

async function uploadMidi(file) {
  if (!file) {
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  setStatus("MIDI を読み込んでいます...");
  elements.exportButton.disabled = true;

  const response = await fetch("/api/projects", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "MIDI の読み込みに失敗しました。");
  }

  state.projectId = payload.projectId;
  state.fileName = payload.fileName;
  state.durationSec = payload.durationSec;
  state.measures = payload.measures || [];
  state.currentTime = 0;
  state.playing = false;
  state.lastPreviewAt = 0;

  elements.fileName.textContent = payload.fileName;
  elements.timelineRange.max = String(Math.max(payload.durationSec, 0.001));
  elements.timelineRange.value = "0";
  elements.exportButton.disabled = false;
  elements.previewFrame.dataset.loaded = "true";
  document.body.classList.add("has-project");
  updateMeta();
  setStatus("MIDI を読み込みました。");
  queuePreview(true);
}

function getPreviewSize() {
  const { width, height } = getSelectedExportDimensions();
  const aspectRatio = width / Math.max(height, 1);
  const frameWidth = elements.previewFrame.clientWidth || elements.previewImage.clientWidth || 960;
  const previewWidth = Math.max(240, Math.min(1280, Math.round(frameWidth)));
  return {
    width: previewWidth,
    height: Math.max(180, Math.round(previewWidth / aspectRatio)),
  };
}

async function requestPreview() {
  if (!state.projectId) {
    return;
  }
  if (state.previewBusy) {
    state.previewQueued = true;
    return;
  }

  state.previewBusy = true;
  state.previewQueued = false;

  try {
    const previewSize = getPreviewSize();
    const response = await fetch(`/api/projects/${state.projectId}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        timeSec: state.currentTime,
        width: previewSize.width,
        height: previewSize.height,
        settings: collectSettings(),
      }),
    });

    if (!response.ok) {
      let message = "プレビューの更新に失敗しました。";
      try {
        const payload = await response.json();
        message = payload.error || message;
      } catch (_error) {
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    if (state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
    }
    state.previewUrl = URL.createObjectURL(blob);
    elements.previewImage.src = state.previewUrl;
    elements.previewEmpty.hidden = true;
    state.lastPreviewAt = performance.now();
    updateMeta();
  } catch (error) {
    setStatus(error.message);
  } finally {
    state.previewBusy = false;
    if (state.previewQueued) {
      requestPreview();
    }
  }
}

function queuePreview(immediate = false) {
  if (!state.projectId) {
    return;
  }
  window.clearTimeout(state.previewTimer);
  const delay = immediate ? 0 : PREVIEW_INPUT_DEBOUNCE_MS;
  state.previewTimer = window.setTimeout(() => {
    requestPreview();
  }, delay);
}

function getCurrentMeasure() {
  if (!state.measures.length) {
    return null;
  }
  let current = state.measures[0];
  for (const measure of state.measures) {
    if (state.currentTime + 1e-6 >= measure.startSec) {
      current = measure;
      continue;
    }
    break;
  }
  return current;
}

function updateMeta() {
  elements.timelineRange.value = String(state.currentTime);
  elements.timeText.textContent = `${formatTime(state.currentTime)} / ${formatTime(state.durationSec)}`;

  const measure = getCurrentMeasure();
  if (!measure) {
    elements.measureText.textContent = "小節: -";
    return;
  }
  elements.measureText.textContent = `現在小節: ${measure.index + 1} / ${state.measures.length} (${measure.numerator}/${measure.denominator})`;
}

function jumpMeasure(direction) {
  const currentMeasure = getCurrentMeasure();
  if (!currentMeasure) {
    return;
  }
  const nextIndex = Math.max(0, Math.min(state.measures.length - 1, currentMeasure.index + direction));
  state.currentTime = state.measures[nextIndex].startSec;
  state.playing = false;
  updateMeta();
  queuePreview(true);
}

function togglePlayback() {
  if (!state.projectId) {
    setStatus("先に MIDI を読み込んでください。");
    return;
  }

  if (state.playing) {
    state.playing = false;
    setStatus("再生を一時停止しました。");
    return;
  }

  if (state.currentTime >= state.durationSec) {
    state.currentTime = 0;
  }

  state.playing = true;
  state.playbackOriginSec = state.currentTime;
  state.playbackStartedAt = performance.now();
  setStatus("再生中...");
}

function stopPlayback() {
  state.playing = false;
  state.currentTime = 0;
  updateMeta();
  queuePreview(true);
  setStatus("停止しました。");
}

function animationLoop(now) {
  if (state.playing) {
    const elapsedSec = (now - state.playbackStartedAt) / 1000;
    state.currentTime = Math.min(state.durationSec, state.playbackOriginSec + elapsedSec);
    updateMeta();

    if (now - state.lastPreviewAt >= PREVIEW_FRAME_INTERVAL_MS) {
      requestPreview();
    }

    if (state.currentTime >= state.durationSec) {
      state.playing = false;
      setStatus("再生が終了しました。");
    }
  }

  window.requestAnimationFrame(animationLoop);
}

function normalizeFpsInput() {
  const normalized = clamp(Number(elements.fpsInput.value) || DEFAULT_EXPORT_FPS, 1, MAX_EXPORT_FPS);
  elements.fpsInput.value = String(Math.round(normalized));
  return normalized;
}

async function exportVideo() {
  if (!state.projectId) {
    setStatus("先に MIDI を読み込んでください。");
    return;
  }

  const fps = normalizeFpsInput();
  const exportFormat = getSelectedExportFormat();
  const { width, height } = getSelectedExportDimensions();
  const exportLabel = exportFormat === "png_sequence" ? "連番PNG" : exportFormat === "mov" ? "MOV" : exportFormat === "webm_vp9" ? "WebM VP9" : "H.264";
  setStatus(`${exportLabel}を書き出しています... ${fps}FPS / ${width}x${height}`);
  elements.exportButton.disabled = true;

  try {
    const response = await fetch(`/api/projects/${state.projectId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        format: exportFormat,
        fps,
        width,
        height,
        settings: collectSettings(),
      }),
    });

    if (!response.ok) {
      let message = "書き出しに失敗しました。";
      try {
        const payload = await response.json();
        message = payload.error || message;
      } catch (_error) {
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?/i);
    const defaultExtension = exportFormat === "png_sequence" ? ".zip" : exportFormat === "mov" ? ".mov" : ".mp4";
    const fileName = decodeURIComponent(
      filenameMatch?.[1] || filenameMatch?.[2] || `${state.fileName || "export"}${defaultExtension}`,
    );
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
    setStatus(`${exportLabel}の書き出しが完了しました。`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    elements.exportButton.disabled = false;
  }
}

function formatTime(seconds) {
  const totalMilliseconds = Math.max(0, Math.round(seconds * 1000));
  const minutes = Math.floor(totalMilliseconds / 60000);
  const remainder = totalMilliseconds % 60000;
  const secs = Math.floor(remainder / 1000);
  const milliseconds = remainder % 1000;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
}

function handleManualStyleChange() {
  markCustomTheme();
  syncThemeAtmosphere(collectSettings());
  syncExportUiState();
  queuePreview(true);
}

function installPointerLighting() {
  const rootStyle = document.documentElement.style;
  window.addEventListener("pointermove", (event) => {
    rootStyle.setProperty("--cursor-x", `${event.clientX}px`);
    rootStyle.setProperty("--cursor-y", `${event.clientY}px`);
  }, { passive: true });
}

function initialize() {
  populateSelect(elements.themeSelect, boot.choices.themes || [], boot.defaultTheme);
  populateSelect(elements.exportFormatSelect, boot.exportFormats || [], DEFAULT_EXPORT_FORMAT);
  populateSelect(elements.exportOrientationSelect, boot.exportOrientations || [], DEFAULT_EXPORT_ORIENTATION);
  populateSelect(elements.exportResolutionSelect, boot.exportResolutions || [], defaultExportResolution);
  populateSelect(elements.viewModeSelect, boot.choices.viewModes || [], boot.defaultSettings.view_mode);
  populateSelect(elements.fontFamilySelect, boot.choices.fonts || [], boot.defaultSettings.font_family);
  populateSelect(elements.cornerStyleSelect, boot.choices.corners || [], boot.defaultSettings.corner_style);
  populateSelect(elements.glowStyleSelect, boot.choices.glows || [], boot.defaultSettings.glow_style);
  populateSelect(elements.animationStyleSelect, boot.choices.animations || [], boot.defaultSettings.animation_style);
  populateSelect(elements.afterimageStyleSelect, boot.choices.afterimages || [], boot.defaultSettings.afterimage_style);
  populateSelect(elements.releaseFadeStyleSelect, boot.choices.releaseFadeStyles || [], boot.defaultSettings.release_fade_style);
  populateSelect(elements.releaseFadeCurveSelect, boot.choices.releaseFadeCurves || [], boot.defaultSettings.release_fade_curve);

  elements.fpsInput.value = String(DEFAULT_EXPORT_FPS);
  elements.exportButton.disabled = true;

  renderPresetCards();
  syncSelectionToTheme(boot.defaultTheme);
  updateMeta();
  installPointerLighting();
  syncExportUiState();

  elements.themeSelect.addEventListener("change", () => {
    const selectedTheme = elements.themeSelect.value;
    if (selectedTheme === boot.customTheme) {
      markCustomTheme();
      return;
    }
    wrapViewTransition(() => {
      syncSelectionToTheme(selectedTheme);
    });
    queuePreview(true);
  });

  elements.exportFormatSelect.addEventListener("change", () => {
    syncExportUiState({ queue: true });
  });
  elements.exportOrientationSelect.addEventListener("change", () => {
    syncExportUiState({ queue: true });
  });
  elements.exportResolutionSelect.addEventListener("change", () => {
    syncExportUiState({ queue: true });
  });

  elements.savePresetButton.addEventListener("click", saveCurrentPreset);
  elements.deletePresetButton.addEventListener("click", deleteSelectedPreset);

  elements.fileInput.addEventListener("change", async (event) => {
    const [file] = event.target.files || [];
    if (!file) {
      return;
    }
    try {
      await uploadMidi(file);
    } catch (error) {
      setStatus(error.message);
      elements.exportButton.disabled = false;
    }
  });

  [
    elements.viewModeSelect,
    elements.fontFamilySelect,
    elements.customFontPathInput,
    elements.cornerStyleSelect,
    elements.glowStyleSelect,
    elements.animationStyleSelect,
    elements.afterimageStyleSelect,
    elements.releaseFadeStyleSelect,
    elements.releaseFadeCurveSelect,
    elements.backgroundColorInput,
    elements.idleNoteColorInput,
    elements.activeNoteColorInput,
    elements.glowColorInput,
    elements.animationAccentColorInput,
    elements.outlineColorInput,
    elements.textColorInput,
  ].forEach((element) => {
    element.addEventListener("input", handleManualStyleChange);
  });

  [
    elements.visibleMeasureCountInput,
    elements.noteLengthScaleInput,
    elements.noteHeightScaleInput,
    elements.horizontalPaddingInput,
    elements.verticalPaddingInput,
    elements.glowStrengthInput,
    elements.animationStrengthInput,
    elements.animationSpeedInput,
    elements.afterimageStrengthInput,
    elements.idleOutlineWidthInput,
    elements.activeOutlineWidthInput,
    elements.afterimageOutlineWidthInput,
    elements.afterimageDurationInput,
    elements.afterimagePaddingInput,
    elements.releaseFadeDurationInput,
  ].forEach((element) => {
    element.addEventListener("input", () => {
      syncSliderLabels();
      handleManualStyleChange();
    });
  });

  [
    elements.hideFutureNotesCheckbox,
    elements.showPlayheadCheckbox,
    elements.showTimeOverlayCheckbox,
    elements.showMeasureOverlayCheckbox,
    elements.showStatsOverlayCheckbox,
    elements.showChordOverlayCheckbox,
    elements.transparentBackgroundCheckbox,
    elements.fitToVisibleNoteRangeCheckbox,
  ].forEach((element) => {
    element.addEventListener("input", handleManualStyleChange);
  });

  elements.timelineRange.addEventListener("input", () => {
    state.playing = false;
    state.currentTime = Number(elements.timelineRange.value);
    updateMeta();
    queuePreview();
  });

  elements.fpsInput.addEventListener("change", normalizeFpsInput);
  elements.playButton.addEventListener("click", togglePlayback);
  elements.stopButton.addEventListener("click", stopPlayback);
  elements.prevMeasureButton.addEventListener("click", () => jumpMeasure(-1));
  elements.nextMeasureButton.addEventListener("click", () => jumpMeasure(1));
  elements.exportButton.addEventListener("click", exportVideo);

  window.addEventListener("resize", () => {
    updatePreviewAspect();
    queuePreview();
  });

  window.addEventListener("beforeunload", () => {
    if (state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
    }
  });

  window.requestAnimationFrame(animationLoop);
}

initialize();
