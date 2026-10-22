# Project structure

## Project type

Rocky is primarily a Python desktop application, with two supporting CLI
surfaces and an older local browser interface. It is a single-repository
project, not a multi-package monorepo. The default experience is macOS-first and
local-first.

## Functional areas and layers

| Area | Files | Responsibility |
|---|---|---|
| Desktop application | `rocky_desktop_app.py` | pygame event loop and UI; microphone capture; transcription; brain/provider calls; camera snapshots; speech synthesis orchestration and playback. |
| Voice service and CLI | `rocky_say.py` | Rocky text transform; TTS model/provider selection; persistent XTTS HTTP server lifecycle; CLI synthesis and playback. |
| Eyes renderer | `rocky_eyes.py` | Emotion presets, mood selection, procedural drawing, and PNG self-test output. |
| Browser interface | `app.py` | Embedded HTML/JavaScript UI and stdlib HTTP routes; delegates speech transformation and synthesis to `rocky_say.py`. |
| Packaging and setup | `setup.sh`, `scripts/`, `Makefile`, `requirements.txt` | Python environment setup, private asset restoration, macOS `.app` packaging, local checks, and dependency pins. |
| Documentation and evidence | `README.md`, `PROJECT.md`, `HANDOFF.md`, `docs/` | Current behavior, setup, measured latency, research, redesign proposal, roadmap, and operational guidance. |
| Local-only assets | `assets/`, `logs/`, `shots/` | Voice assets are private/not redistributed; logs and generated images/audio are runtime or test outputs. |

There is no database/persistence layer. Conversation state is held in process
memory; audio, camera snapshots, logs, and self-test images are written to
files. The browser UI and voice server communicate over loopback HTTP.

## Entry points

| Entry point | Trigger | Role |
|---|---|---|
| `rocky_desktop_app.py:771` | `python rocky_desktop_app.py [options]` | Main desktop companion; includes `--selftest` and `--snap` modes. |
| `app.py:243` | `python app.py [--host] [--port] [--warm]` | Legacy browser companion, serving the embedded page and HTTP API. |
| `rocky_say.py:556` | `python rocky_say.py [options]` | Voice CLI and persistent XTTS server management via `--server`. |
| `rocky_eyes.py:245` | `python rocky_eyes.py --selftest DIR` | Standalone eye-renderer image generation. |

## Source/configuration inventory

The root Python application consists of four source files: the desktop app,
browser app, voice service, and eyes renderer. The repository also contains
three shell scripts, one pinned Python dependency file, one Makefile, and
documentation under `docs/`. See `git ls-files` for the complete tracked-file
inventory.

Important configuration surfaces:

- `requirements.txt`: exact Python package pins and compatibility constraints.
- `setup.sh`: Python 3.11 and `ffmpeg` prerequisites; creates the virtual
  environment and installs the pinned dependencies.
- `rocky_desktop_app.py` CLI: brain provider/model, API URL/key, vision model,
  camera index, STT model, and feature switches.
- `rocky_say.py`: `ROCKY_SPEED`, fixed loopback server port, local asset paths,
  and CLI voice/model options.
- `app.py` CLI: browser-server host/port and optional model warmup.
- `scripts/make_app.sh`: macOS app bundle and permission identity behavior.

## Runtime flow

The main desktop path is push-to-talk or typed input → local transcription
(speech only) → local/optional hosted brain → sentence/clause splitting →
XTTS synthesis → WAV playback and animated eye response. F3 requests a
one-shot camera image and a vision description. The browser path accepts typed
text or browser speech recognition and delegates voice generation to the
loopback XTTS server.

The documented objective is a real-time desktop companion with sub-second
first audio, interruption/barge-in, echo cancellation, continuous local
perception with on-demand vision, and graceful offline/network fallback. That
objective is documented as a proposal in `docs/REALTIME_PLAN.md`; it is not
current behavior.
