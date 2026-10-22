# Existing technology stack

## Language and runtime

- Python 3.11 is the documented and tested runtime.
- Coqui TTS is pinned at 0.22.0 and requires Python below 3.12.
- The primary target platform is macOS on Apple Silicon. The repository has
  Windows-specific process-launch/stop branches in `rocky_say.py`, but setup,
  packaging, and permission guidance are macOS-focused.
- Shell setup and packaging scripts use Bash.
- The browser interface is embedded HTML, CSS, and JavaScript in `app.py`;
  there is no separate frontend build.

## Pinned Python dependencies

| Package | Version | Use |
|---|---:|---|
| `numpy` | 1.26.4 | Audio/image numeric arrays; pinned below 2 for the TTS dependency graph. |
| `opencv-python-headless` | 4.11.0.86 | Camera capture and JPEG encoding. |
| `TTS` | 0.22.0 | Coqui XTTS and related TTS model support. |
| `transformers` | 4.44.0 | TTS model dependency. |
| `torch` | 2.5.1 | Model inference. |
| `torchaudio` | 2.5.1 | Audio/model dependency. |
| `faster-whisper` | 1.2.1 | Speech recognition. |
| `sounddevice` | 0.5.6 | Microphone capture. |
| `soundfile` | 0.14.0 | WAV reading/writing. |
| `pygame` | 2.6.1 | Desktop window, drawing, and audio playback. |
| `scipy` | 1.17.1 | Signal/audio utility dependency. |

The Python standard library supplies HTTP servers/clients, JSON, threading,
queues, argument parsing, and process management. `app.py` uses
`ThreadingHTTPServer`; the XTTS server uses `HTTPServer`.

## External runtimes and services

- Ollama is the default local model runtime: `qwen3-coder:latest` for the
  brain and `qwen2.5vl:3b` for vision.
- Optional brain integrations use OpenAI-compatible chat completions or the
  Anthropic Messages API. These are configured through CLI arguments and
  `BRAIN_API_KEY`; no cloud provider is required for the local path.
- The XTTS server listens on loopback port 59720; the legacy browser server
  defaults to loopback port 8765.
- `ffmpeg` is required by the documented setup process.
- Voice reference/model assets are intentionally not included in the
  repository.

## Build, packaging, and checks

- `setup.sh` creates a Python 3.11 virtual environment and installs
  `requirements.txt`.
- `scripts/make_app.sh` creates the macOS `.app` bundle used to obtain stable
  microphone/camera permissions.
- `Makefile` exposes setup, TTS server, app packaging, self-tests, and
  `compileall` lint targets.

## Constraints recorded by the project

- NumPy must remain below 2 for the pinned `gruut`/TTS dependency compatibility.
- XTTS currently uses complete-WAV synthesis; measured clause generation takes
  multiple seconds and its streaming inference path is documented as broken for
  the pinned Torch/Transformers versions.
- The camera path and microphone permissions are documented as reliable only
  through a real macOS `.app` bundle.
- No target stack has been selected by this analysis. The streaming STT/TTS,
  realtime session, VAD, AEC, and playback options in `docs/REALTIME_PLAN.md`
  remain proposals.
