# MVTT Battlemap — Python Desktop App

Standalone Python desktop application that replicates `battlemap-local-app` and adds
multi-monitor player window support. Produces a single Windows `.exe` via PyInstaller.

## Requirements

- Python 3.11 or newer
- The packages listed in `requirements.txt`

## Setup

```cmd
REM Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

REM Install dependencies
pip install -r requirements.txt
```

## Run (development)

From the `battlemap-python-app/` directory:

```cmd
python main.py
```

> **Note:** On Windows, CMD must be used. Do not run via PowerShell when a `.venv` is involved
> unless the activation script is loaded correctly.

## Build EXE

```cmd
REM Activate venv first, then:
build.bat
```

Output: `dist\MVTT_Battlemap.exe` — single file, no console window, no Python installation needed.

`build.bat` performs a clean build and bundles `assets/icons` into the EXE.

## Features

| Feature | Details |
|---|---|
| Load Image | Opens any common image format (PNG, JPG, BMP, GIF, WebP) |
| Open Player Window | Detects monitors; shows selector if ≥2 available |
| Monitor guard | GM window's monitor is never selectable for the player window |
| No second monitor | Shows an info message; player window cannot open |
| Rotate | 90° clockwise; viewport and reveals follow the rotation |
| Revert Last | Undo last viewport move, resize, or fog reveal |
| Reset Fog | Clears all reveals (with undo support) |
| Fog of war | 35% black overlay; right-drag to reveal rectangular areas |
| Player fullscreen | Borderless window fills the selected monitor; Escape to close |
| Legend | Shows distinct left/right mouse button symbols for key actions |

## Controls

| Action | Input |
|---|---|
| Move viewport | Left-click + drag inside red rectangle |
| Resize viewport | Left-click + drag corner handle |
| Reveal area | Right-click + drag |
| Close player window | Escape (on player window) |

## Project Structure

```
battlemap-python-app/
├── main.py            Entry point
├── gm_window.py       GM window: toolbar, canvas, interaction
├── player_window.py   Player window: borderless fullscreen display
├── monitor_dialog.py  Monitor detection and selection dialog
├── renderer.py        Pillow-based rendering for both canvases
├── state.py           AppState dataclass and history helpers
├── icons.py           Legend icon loading and fallback generation
├── assets/icons/      Downloaded mouse icon PNG sources
├── requirements.txt   Python dependencies
└── build.bat          PyInstaller EXE build script
```

## Architecture

See [ADR-005](../docs/adr/ADR-005-python-desktop-app.md) for the runtime and technology decisions.

Both windows share the same `AppState` object directly (same Python process).
No inter-process communication, no BroadcastChannel, no localStorage.

## Performance & Rendering

- **GM canvas render**: Throttled to ~30 FPS during drag operations to prevent jank
- **Player window update**: Syncs live during GM drag/resize (minimum 2 FPS for smooth feedback)
- **DPI scaling**: GM window geometry is preserved across monitor selection to prevent unwanted resizing
