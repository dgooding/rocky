# Rocky

A local-first desktop assistant with a British English Kokoro voice, a local
brain, a local vision model, and animated eyes inspired by Casey Grothaus's
[desk robot](https://github.com/cgro00/desk-robot) (see it in action:
[YouTube short](https://www.youtube.com/shorts/aHSusA0xXjU)). Say "hey Rocky"
and the assistant looks at you and responds conversationally.

Talk to him, type to him, show him things. Nothing leaves the machine unless
you explicitly configure a hosted brain or a cloud voice.

![Rocky idle](shots/app_idle.png)

## Status

| Piece | State |
|---|---|
| Speech voice | Local MLX Drama 3 with a generic British female voice reference; Kokoro fallback |
| Hearing: hands-free, "hey Rocky" wake, sleep command | Working (energy-based speech detection; untested on hardware yet) |
| Mic → speech-to-text (faster-whisper) | Working, ~0.4 s after you stop talking |
| Brain (Ollama `qwen3-coder:latest`, streaming) | Working, ~0.1 s warm first token |
| Sentence/Clause pipelining | Working, speech starts on the first completed clause |
| Eyes, 7 emotions, white sclera + black pupil | Working; doze off when ignored |
| Sight: "what do you see?" / F3 + local vision | Working, `qwen2.5vl:3b` |
| Sight: watch mode, eyes follow your face | Working (opt-in; OpenCV face detection, local) |
| macOS camera + mic permission | Working **only via a real `.app` bundle** |
| GUI text input | Working |
| Voice interruption | F1 cancels a response and starts push-to-talk; automatic voice barge-in and echo cancellation are not implemented |
| PCM playback | Speech audio is played as 20 ms PCM blocks |

The current app is turn-based. The real-time redesign is documented in
[`docs/REALTIME_PLAN.md`](docs/REALTIME_PLAN.md); the measured bottlenecks are in
[`docs/LATENCY.md`](docs/LATENCY.md).

## Quick start (macOS, Apple Silicon)

```sh
# 1. Python 3.11 (TTS caps at <3.12)
brew install python@3.11 ffmpeg

# 2. Dependencies
./setup.sh

# 3. Set up the local expressive Drama 3 voice (~22 GiB, one-time download).
./scripts/setup_drama3.sh

# 4. Build and launch
./scripts/make_app.sh
open -n ./Rocky.app
```

Drama 3 is Rocky's default voice: it runs locally through MLX and references a
generic British female voice generated locally with Kokoro, with no inserted
breathing effects and a slightly faster speaking pace. The one-time setup keeps its
22 GiB model and separate Python environment in `~/.cache/rocky`; neither is
added to this repository. The app loads Drama 3 on first speech and keeps it
resident while running. This uses about 26 GiB of memory during synthesis, so
large Ollama models may compete for unified memory.

Kokoro remains available with `--tts-engine kokoro`; try another preset with
`--kokoro-voice`. An installed macOS voice remains available with
`--tts-engine macos`. The separate `rocky_say.py` legacy voice tool is not used
by the desktop app.

Run from the project instead of the bundle if you do not need the camera:

```sh
./venv/bin/python rocky_desktop_app.py
```

## Talking to him

He listens hands-free, like the desk robot:

| Say | What happens |
|---|---|
| "hey Rocky" | He wakes and looks up. His name alone does not wake him. |
| anything, while he is awake | He answers. He stays awake for a minute after each exchange. |
| "what do you see?" / "what am I holding?" | He takes one camera picture and answers about it. |
| "Rocky, look left" | His eyes turn that way, then he looks. |
| "track me" / "stop tracking" | Watch mode on or off: his eyes follow your face. |
| "Rocky, sleep" / "goodnight" | He says goodnight and stops answering until you say "hey Rocky". |

He stops listening while he is thinking or speaking, so he never hears himself.
Hold F1 to interrupt a response and speak with push-to-talk; automatic voice
barge-in is not enabled without echo cancellation. Watch mode keeps the camera
open (its light stays on) and is off unless you ask for it.

## Controls

```
F1 hold / F2 toggle   push-to-talk; holding F1 interrupts Rocky
F3 or Space           look through the camera
F4                    hands-free listening on/off
F5                    watch mode on/off (eyes follow your face)
F6                    run local setup diagnostics
F7                    test the mic briefly (audio is not saved)
F8                    test the camera with one frame (not saved/uploaded)
F9                    run safe local brain/voice recovery checks
type + Enter          talk by keyboard
1 – 7                 force an emotion (when the input line is empty)
Esc                   quit
```

Run a terminal diagnosis with `./venv/bin/python rocky_desktop_app.py --diagnose`.
It checks dependencies, model/runtime files, Ollama model availability, and
audio-device enumeration without opening the mic or camera. The report is saved
to `logs/diagnostics.txt`. Add `--diagnose-live` to also make a local brain
request and synthesize a short voice sample (not played; may load large models).
Use `--diagnose-mic` or `--diagnose-camera` only when you want those devices
opened for a brief test; captured media is not saved or sent anywhere.
Say "Rocky, diagnose yourself" for a spoken summary, or "Rocky, fix this" /
"fix the slow response" to run local brain and voice checks and warm them. A
specific "fix the microphone" or "fix the camera" request also runs that
device's brief, unsaved test.
This recovery path never executes model-generated shell commands, installs
packages, changes macOS permissions, or deletes files; it reports the
remaining issue and saved diagnostic details instead.

Flags: `--push-to-talk` starts with hands-free off; `--watch` starts in watch
mode; `--no-camera` disables the camera entirely. Tune hands-free silence
endpointing with `--end-silence-ms 500` (200–2000 ms; default 700).

## How it works

```
mic ──► speech detection ──► "hey Rocky"? ──► faster-whisper ──► qwen3-coder (Ollama, streamed)
                                                                        │
                                                                        ▼
                                                              sentence / clause split
                                                                        │
                                                                        ▼
                                                    Kokoro British voice / macOS alternative ──► PCM playback
                                                                        │
                                                                        ▼
                                                               eyes react to amplitude

camera ──► one JPEG on request ──► qwen2.5vl:3b (Ollama) ──► one spoken sentence
camera ──► watch mode: face detection (OpenCV, 4 fps) ──► eyes follow you
```

The app is deliberately local-first: no API keys are required. The default
Kokoro voice is generated on-device. Hosted OpenAI-compatible or Anthropic
brains are supported via CLI flags.

## Documentation

| Document | What |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | Current agent handoff: state, constraints, phases, next action |
| [`AGENTS.md`](AGENTS.md) | Instructions AI coding agents read automatically: current task, rules, commands |
| [`PROJECT.md`](PROJECT.md) | The full project handbook: setup, architecture, configuration, performance, gotchas, roadmap, licensing |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Component and threading model |
| [`docs/SETUP.md`](docs/SETUP.md) | Detailed install, permissions, assets, and app bundle |
| [`docs/LATENCY.md`](docs/LATENCY.md) | Measured latency and how to reproduce it |
| [`docs/REALTIME_PLAN.md`](docs/REALTIME_PLAN.md) | Research-backed plan for sub-second speech, barge-in, and continuous vision |
| [`docs/RESEARCH.md`](docs/RESEARCH.md) | Verified sources, model comparison, and caveats |
| [`docs/OPEN_SOURCE_OPTIONS.md`](docs/OPEN_SOURCE_OPTIONS.md) | Survey of existing open-source assistant apps (research record) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phased implementation plan |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Camera, audio, Ollama, TTS, and packaging fixes |
| [`docs/GUIDE.md`](docs/GUIDE.md) | Upstream voice-script guide (grammar transform, RVC, etc.) |
| [`docs/HANDOFF-2026-10-21.md`](docs/HANDOFF-2026-10-21.md) | Original build handoff, preserved for history |

## Project layout

```text
.
├── rocky_desktop_app.py   # the desktop app: mic, STT, brain, vision, TTS, eyes, UI
├── rocky_eyes.py          # emotion presets, renderer, --selftest
├── rocky_say.py           # voice script + persistent XTTS server
├── app.py                 # older browser UI (port 8765), not the primary path
├── setup.sh               # Python 3.11 venv + dependencies
├── scripts/
│   ├── fetch_assets.sh    # download voice files + models that are not in git
│   ├── restore_assets.sh  # copy voice assets from your private backup instead
│   └── make_app.sh        # build the macOS .app bundle
├── assets/                # voice assets live here (not committed)
├── shots/                 # rendered eye / app reference images
└── docs/                  # architecture, setup, latency, research, roadmap
```

## Privacy

- Default brain and vision run through local Ollama at `127.0.0.1:11434`.
- Hands-free listening keeps the microphone open while it is on; audio is
  processed on this machine and never saved. The window always shows whether
  he is listening ("say hey Rocky" / "awake"). F4 or `--push-to-talk` turns it off.
- The camera opens only for an explicit look, unless you turn on watch mode
  (F5, "track me", or `--watch`). In watch mode face detection runs locally,
  the window shows "watching", and the camera light stays on. Frames go to the
  vision model only when you ask what he sees.
- Logs are written to `~/Library/Logs/Rocky.log` (bundle) or `$TMPDIR/rocky-desk.log`.

## License and attribution

This project is a derivative of
[`Kuberwastaken/rocky-tts`](https://github.com/Kuberwastaken/rocky-tts) and is
released under **CC BY-NC 4.0**. The Rocky character and voice are the
intellectual property of the *Project Hail Mary* film production; the voice
assets are for personal, non-commercial use only and are **not** included in
this repository. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).

Do not use this project or its voice assets commercially.
