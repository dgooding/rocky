# Rocky

A desk companion built around a local voice clone, a local brain, a local
vision model, and a pair of animated eyes. It is the on-screen version of
Casey Grothaus's [desk robot](https://github.com/cgro00/desk-robot) (see it in
action: [YouTube short](https://www.youtube.com/shorts/aHSusA0xXjU)): say
"hey Rocky", and he looks at you and answers in character.

Talk to him, type to him, show him things. Nothing leaves the machine unless
you explicitly configure a hosted brain or a cloud voice.

![Rocky idle](shots/app_idle.png)

## Status

| Piece | State |
|---|---|
| Voice clone (XTTS v2, Rocky) | Working, but **too slow for real-time** (~2.4–3.8 s per clause on an M1 Max) |
| Hearing: hands-free, "hey Rocky" wake, sleep command | Working (energy-based speech detection; untested on hardware yet) |
| Mic → speech-to-text (faster-whisper) | Working, ~0.4 s after you stop talking |
| Brain (Ollama `qwen3-coder:latest`, streaming) | Working, ~0.1 s warm first token |
| Sentence/Clause pipelining | Working, speech starts on the first completed clause |
| Eyes, 7 emotions, white sclera + black pupil | Working; doze off when ignored |
| Sight: "what do you see?" / F3 + local vision | Working, `qwen2.5vl:3b` |
| Sight: watch mode, eyes follow your face | Working (opt-in; OpenCV face detection, local) |
| macOS camera + mic permission | Working **only via a real `.app` bundle** |
| GUI text input | Working |
| Barge-in / echo cancellation / streaming playback | **Not implemented yet** (he stops listening while he speaks) |

The current app is turn-based. The real-time redesign is documented in
[`docs/REALTIME_PLAN.md`](docs/REALTIME_PLAN.md); the measured bottlenecks are in
[`docs/LATENCY.md`](docs/LATENCY.md).

## Quick start (macOS, Apple Silicon)

```sh
# 1. Python 3.11 (TTS caps at <3.12)
brew install python@3.11 ffmpeg

# 2. Dependencies
./setup.sh

# 3. Large files that are not in git: Rocky's voice files (from the upstream
#    author's links), Ollama models, speech and voice models. ~23 GB, once.
./scripts/fetch_assets.sh

# 4. Voice server (first load ~20 s)
COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start

# 5. Build and launch the app bundle
./scripts/make_app.sh
open -n ./Rocky.app
```

Have your own backup of the voice files? `./scripts/restore_assets.sh
/path/to/your/rocky-assets` copies them instead of downloading.

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
Watch mode keeps the camera open (its light stays on) and is off unless you
ask for it.

## Controls

```
F1 hold / F2 toggle   push-to-talk (works alongside hands-free)
F3 or Space           look through the camera
F4                    hands-free listening on/off
F5                    watch mode on/off (eyes follow your face)
type + Enter          talk by keyboard
1 – 7                 force an emotion (when the input line is empty)
Esc                   quit
```

Flags: `--push-to-talk` starts with hands-free off; `--watch` starts in watch
mode; `--no-camera` disables the camera entirely.

## How it works

```
mic ──► speech detection ──► "hey Rocky"? ──► faster-whisper ──► qwen3-coder (Ollama, streamed)
                                                                        │
                                                                        ▼
                                                              sentence / clause split
                                                                        │
                                                                        ▼
                                                    XTTS v2 voice clone ──► pygame playback
                                                                        │
                                                                        ▼
                                                               eyes react to amplitude

camera ──► one JPEG on request ──► qwen2.5vl:3b (Ollama) ──► one spoken sentence
camera ──► watch mode: face detection (OpenCV, 4 fps) ──► eyes follow you
```

The app is deliberately local-first: no API keys are required. Hosted
OpenAI-compatible or Anthropic brains are supported via CLI flags.

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
