# MIDI Measure Video Exporter

This Windows desktop app loads a MIDI file, shows one measure at a time as a fixed layout, highlights currently sounding notes in white, and exports the animation to an MP4 video without audio.

## Visual Style

- Resolution: `1920x1080`
- Background: black
- Idle notes: dark gray
- Active notes: white
- Layout: one measure at a time, fixed on screen

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

Or double-click `run.bat`.

## Use

1. Open a `.mid` or `.midi` file.
2. Preview the animation with the play controls.
3. Use `Export MP4` to write a video file.

## Notes

- Audio is not included in the exported video.
- All MIDI tracks are merged into a single note view.
- Time signature changes are supported. Each measure is rendered as its own fixed screen.
