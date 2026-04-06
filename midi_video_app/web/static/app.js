const boot = window.APP_BOOTSTRAP;

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
  playButton: document.getElementById("playButton"),
  stopButton: document.getElementById("stopButton"),
  prevMeasureButton: document.getElementById("prevMeasureButton"),
  nextMeasureButton: document.getElementById("nextMeasureButton"),
  timelineRange: document.getElementById("timelineRange"),
  timeText: document.getElementById("timeText"),
  measureText: document.getElementById("measureText"),
  themeSelect: document.getElementById("themeSelect"),
  cornerStyleSelect: document.getElementById("cornerStyleSelect"),
  glowStyleSelect: document.getElementById("glowStyleSelect"),
  animationStyleSelect: document.getElementById("animationStyleSelect"),
  afterimageStyleSelect: document.getElementById("afterimageStyleSelect"),
  backgroundColorInput: document.getElementById("backgroundColorInput"),
  idleNoteColorInput: document.getElementById("idleNoteColorInput"),
  activeNoteColorInput: document.getElementById("activeNoteColorInput"),
  glowColorInput: document.getElementById("glowColorInput"),
  animationAccentColorInput: document.getElementById("animationAccentColorInput"),
  outlineColorInput: document.getElementById("outlineColorInput"),
  glowStrengthInput: document.getElementById("glowStrengthInput"),
  animationStrengthInput: document.getElementById("animationStrengthInput"),
  animationSpeedInput: document.getElementById("animationSpeedInput"),
  afterimageStrengthInput: document.getElementById("afterimageStrengthInput"),
  glowStrengthValue: document.getElementById("glowStrengthValue"),
  animationStrengthValue: document.getElementById("animationStrengthValue"),
  animationSpeedValue: document.getElementById("animationSpeedValue"),
  afterimageStrengthValue: document.getElementById("afterimageStrengthValue"),
  fpsInput: document.getElementById("fpsInput"),
};

const settingBindings = {
  background_color: elements.backgroundColorInput,
  idle_note_color: elements.idleNoteColorInput,
  active_note_color: elements.activeNoteColorInput,
  glow_color: elements.glowColorInput,
  animation_accent_color: elements.animationAccentColorInput,
  outline_color: elements.outlineColorInput,
  corner_style: elements.cornerStyleSelect,
  glow_style: elements.glowStyleSelect,
  animation_style: elements.animationStyleSelect,
  afterimage_style: elements.afterimageStyleSelect,
  glow_strength: elements.glowStrengthInput,
  animation_strength: elements.animationStrengthInput,
  animation_speed: elements.animationSpeedInput,
  afterimage_strength: elements.afterimageStrengthInput,
};

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
    if (option.value === selectedValue) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

function applySettings(settings) {
  Object.entries(settingBindings).forEach(([fieldName, element]) => {
    const value = settings[fieldName];
    if (fieldName.endsWith("_strength") || fieldName === "animation_speed") {
      element.value = Math.round(Number(value) * 100);
      return;
    }
    element.value = value;
  });
  syncSliderLabels();
}

function collectSettings() {
  return {
    background_color: elements.backgroundColorInput.value,
    idle_note_color: elements.idleNoteColorInput.value,
    active_note_color: elements.activeNoteColorInput.value,
    glow_color: elements.glowColorInput.value,
    animation_accent_color: elements.animationAccentColorInput.value,
    outline_color: elements.outlineColorInput.value,
    corner_style: elements.cornerStyleSelect.value,
    glow_style: elements.glowStyleSelect.value,
    animation_style: elements.animationStyleSelect.value,
    afterimage_style: elements.afterimageStyleSelect.value,
    glow_strength: Number(elements.glowStrengthInput.value) / 100,
    animation_strength: Number(elements.animationStrengthInput.value) / 100,
    animation_speed: Number(elements.animationSpeedInput.value) / 100,
    afterimage_strength: Number(elements.afterimageStrengthInput.value) / 100,
  };
}

function syncSliderLabels() {
  elements.glowStrengthValue.textContent = `${elements.glowStrengthInput.value}%`;
  elements.animationStrengthValue.textContent = `${elements.animationStrengthInput.value}%`;
  elements.animationSpeedValue.textContent = `${elements.animationSpeedInput.value}%`;
  elements.afterimageStrengthValue.textContent = `${elements.afterimageStrengthInput.value}%`;
}

function setStatus(message) {
  elements.statusText.textContent = message;
}

function markCustomTheme() {
  if (elements.themeSelect.value !== boot.customTheme) {
    elements.themeSelect.value = boot.customTheme;
  }
}

async function uploadMidi(file) {
  if (!file) {
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  setStatus("MIDIを読み込み中...");
  elements.exportButton.disabled = true;

  const response = await fetch("/api/projects", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "MIDIの読み込みに失敗しました。");
  }

  state.projectId = payload.projectId;
  state.fileName = payload.fileName;
  state.durationSec = payload.durationSec;
  state.measures = payload.measures || [];
  state.currentTime = 0;
  state.playing = false;

  elements.fileName.textContent = payload.fileName;
  elements.timelineRange.max = String(Math.max(payload.durationSec, 0.001));
  elements.timelineRange.value = "0";
  elements.exportButton.disabled = false;
  updateMeta();
  setStatus("MIDIを読み込みました。");
  queuePreview(true);
}

function getPreviewSize() {
  const previewWidth = Math.max(320, Math.min(1280, Math.round(elements.previewImage.clientWidth || 960)));
  return {
    width: previewWidth,
    height: Math.round(previewWidth * 9 / 16),
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
      let message = "プレビューの取得に失敗しました。";
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
  const delay = immediate ? 0 : 90;
  state.previewTimer = window.setTimeout(() => {
    requestPreview();
  }, delay);
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

function jumpMeasure(direction) {
  if (!state.measures.length) {
    return;
  }
  const currentMeasure = getCurrentMeasure();
  const nextIndex = Math.max(0, Math.min(state.measures.length - 1, currentMeasure.index + direction));
  state.currentTime = state.measures[nextIndex].startSec;
  state.playing = false;
  updateMeta();
  queuePreview(true);
}

function togglePlayback() {
  if (!state.projectId) {
    setStatus("先にMIDIを読み込んでください。");
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

    if (now - state.lastPreviewAt > 85) {
      requestPreview();
    }

    if (state.currentTime >= state.durationSec) {
      state.playing = false;
      setStatus("再生が終了しました。");
    }
  }

  window.requestAnimationFrame(animationLoop);
}

async function exportVideo() {
  if (!state.projectId) {
    setStatus("先にMIDIを読み込んでください。");
    return;
  }

  const fps = Math.max(1, Math.min(120, Number(elements.fpsInput.value) || 30));
  setStatus("動画を書き出し中...");
  elements.exportButton.disabled = true;

  try {
    const response = await fetch(`/api/projects/${state.projectId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fps,
        width: 1920,
        height: 1080,
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
    const fileName = decodeURIComponent(filenameMatch?.[1] || filenameMatch?.[2] || `${state.fileName || "export"}.mp4`);
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
    setStatus("動画を書き出しました。");
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

function initialize() {
  populateSelect(elements.themeSelect, boot.choices.themes, boot.defaultTheme);
  populateSelect(elements.cornerStyleSelect, boot.choices.corners, boot.defaultSettings.corner_style);
  populateSelect(elements.glowStyleSelect, boot.choices.glows, boot.defaultSettings.glow_style);
  populateSelect(elements.animationStyleSelect, boot.choices.animations, boot.defaultSettings.animation_style);
  populateSelect(elements.afterimageStyleSelect, boot.choices.afterimages, boot.defaultSettings.afterimage_style);
  applySettings(boot.defaultSettings);
  updateMeta();

  elements.themeSelect.addEventListener("change", () => {
    const selectedTheme = elements.themeSelect.value;
    if (selectedTheme === boot.customTheme) {
      return;
    }
    applySettings(boot.themePresets[selectedTheme]);
    queuePreview(true);
  });

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
    elements.cornerStyleSelect,
    elements.glowStyleSelect,
    elements.animationStyleSelect,
    elements.afterimageStyleSelect,
    elements.backgroundColorInput,
    elements.idleNoteColorInput,
    elements.activeNoteColorInput,
    elements.glowColorInput,
    elements.animationAccentColorInput,
    elements.outlineColorInput,
  ].forEach((element) => {
    element.addEventListener("input", () => {
      markCustomTheme();
      queuePreview();
    });
  });

  [
    elements.glowStrengthInput,
    elements.animationStrengthInput,
    elements.animationSpeedInput,
    elements.afterimageStrengthInput,
  ].forEach((element) => {
    element.addEventListener("input", () => {
      syncSliderLabels();
      markCustomTheme();
      queuePreview();
    });
  });

  elements.timelineRange.addEventListener("input", () => {
    state.playing = false;
    state.currentTime = Number(elements.timelineRange.value);
    updateMeta();
    queuePreview();
  });

  elements.playButton.addEventListener("click", togglePlayback);
  elements.stopButton.addEventListener("click", stopPlayback);
  elements.prevMeasureButton.addEventListener("click", () => jumpMeasure(-1));
  elements.nextMeasureButton.addEventListener("click", () => jumpMeasure(1));
  elements.exportButton.addEventListener("click", exportVideo);

  window.addEventListener("resize", () => {
    queuePreview();
  });

  window.requestAnimationFrame(animationLoop);
}

initialize();
