
# FrameFlow Studio 2.0

A Python-first video editing workspace. The interface and application logic are written in Python with [NiceGUI](https://nicegui.io/). FFmpeg performs MP4 rendering.

## Features

- Python-rendered web interface
- Import video, image and audio files
- Local server-side media library
- Sequential video and image timeline
- Select and trim clip source ranges
- Split clips at their midpoint
- Remove clips from the timeline
- Assign a soundtrack
- Add timed text overlays
- Save project state as JSON
- Export MP4 (H.264) with FFmpeg
- Landscape, portrait, square and 4:5 output canvases

## Requirements

- Python 3.10 or newer
- FFmpeg installed and available on `PATH`
- pip

## Run locally

### Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py app.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:8080>.

## Install FFmpeg

- Windows: install an FFmpeg build and add its `bin` directory to `PATH`.
- macOS: `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt install ffmpeg`

Check availability:

```bash
ffmpeg -version
```

## Project storage

- `data/uploads/` stores imported media.
- `data/exports/` stores rendered MP4 files.
- `data/project.json` stores the current editable project.

Back up the `data/` directory. This first Python release stores files on the server filesystem and is designed for a single workspace. Do not expose an unprotected public instance to untrusted users.

## Deploy

This is a Python server application, not a static GitHub Pages site. Deploy it to a Python-capable host or VPS. Set:

- `PORT` to the port supplied by your host.
- `FRAMEFLOW_SECRET` to a long, random secret value.

The host must provide FFmpeg and persistent disk storage if uploaded media and projects should survive restarts.

## Current scope

This is a functional Python MVP, not yet a full professional NLE. It currently renders a sequential video/image sequence, optional soundtrack and timed text overlays. Advanced multitrack compositing, waveform editing, transitions, keyframes, AI generation, cloud accounts and collaboration are not included yet.

## License

MIT. See `LICENSE`.
