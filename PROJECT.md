# Rocky — full project handbook

> A desk companion with a local voice clone, a local brain, a local vision
> model, and animated eyes. Talk to him, type to him, show him things.

This is the single document that explains the whole project: what works, how it
is put together, how to run it, what is slow, what is next, and what the legal
constraints are. The short version is in [`README.md`](README.md).

> Picking up development? Start with [`HANDOFF.md`](HANDOFF.md) for the current
> state, constraints, phases, and next action.

Last updated: 2026-10-22

---

## 1. What it is

Rocky is a macOS desktop companion inspired by Rocky, the Eridian engineer from
*Project Hail Mary*. The app combines:

- **Speech input** — microphone capture and faster-whisper transcription.
- **A local brain** — an Ollama chat model, streamed token by token.
- **A cloned voice** — Coqui XTTS v2 conditioned on a short Rocky reference clip.
- **A face** — a pygame window with procedural eyes, blinking, gaze, and seven
  emotion presets driven by the reply text and audio amplitude.
- **Local vision** — a webcam snapshot sent to a small VLM when you press F3.

Everything runs on the machine by default. Hosted OpenAI-compatible and
Anthropic brains are supported, but no keys are required for the local path.

The project started as a fork of
[`Kuberwastaken/rocky-tts`](https://github.com/Kuberwastaken/rocky-tts), which
provides the voice-transform script and the XTTS/RVC voice pipeline. The desktop
app, eyes, camera path, streaming brain integration, and documentation in this
repository are the local build.

---

## 2. Current status

| Piece | State | Notes |
|---|---|---|
| Voice clone (XTTS v2) | Working, slow | ~2.4–3.8 s per clause measured on an M1 Max; not real-time |
| Mic capture | Working | 16 kHz mono, push-to-talk; not streaming |
| Speech-to-text | Working | faster-whisper `base.en`, ~0.4 s after release |
| Brain | Working | Ollama `qwen3-coder:latest`, streamed; ~0.1 s warm first token |
| Sentence/clause pipelining | Working | TTS starts on the first completed clause |
| Eyes / emotions | Working | 7 presets, blink, gaze, amplitude bloom |
| Camera + vision | Working | F3 snapshot → `qwen2.5vl:3b`; model swap can cost ~6 s |
| macOS permissions | Working | Camera/mic only work through a real `.app` bundle |
| Text input | Working | Type + Enter in the app window |
| Barge-in | **Missing** | Playback and listening are mutually exclusive |
| Echo cancellation | **Missing** | Rocky can hear himself if the mic stays open |
| Streaming playback | **Missing** | `pygame.mixer` plays a complete WAV file |
| Continuous vision | **Missing** | Camera opens only for a snapshot |
| Wake word | **Missing** | F1 hold / F2 toggle only |

The detailed redesign is in [`docs/REALTIME_PLAN.md`](docs/REALTIME_PLAN.md).
Measured numbers are in [`docs/LATENCY.md`](docs/LATENCY.md).

---

## 3. Quick start

### 3.1 Prerequisites

- macOS 13+ on Apple Silicon (tested on an M1 Max, 64 GB, macOS 27.0.1).
- Python **3.11** (TTS caps at `<3.12`).
- `ffmpeg`.
- [Ollama](https://ollama.com/) running locally.
- A private copy of the Rocky voice assets (not included; see §10).

```sh
brew install python@3.11 ffmpeg
```

### 3.2 Install dependencies

```sh
git clone https://github.com/dgooding/rocky.git
cd rocky
./setup.sh
```

`setup.sh` creates `./venv`, installs the pinned requirements, and prints the
next steps. It does **not** download voice assets.

### 3.3 Restore the voice assets

The repo intentionally does not redistribute the voice model or reference
audio. Put these files in `assets/`:

```text
assets/rocky_ref_15s.wav
assets/rocky_training_audio_scrubbed.wav
assets/rocky_voice.pth
```

Use your own backup, the original upstream download, or:

```sh
./scripts/restore_assets.sh /path/to/your/rocky-assets
./scripts/restore_assets.sh ../archives/rocky-tts-2026-10-21.tar.gz
```

See [`assets/README.md`](assets/README.md) for the licensing warning.

### 3.4 Pull the local models

```sh
ollama pull qwen3-coder
ollama pull qwen2.5vl:3b
```

`llama3.2:3b` is a smaller/faster fallback:

```sh
ollama pull llama3.2:3b
./venv/bin/python rocky_desktop_app.py --brain-model llama3.2:3b
```

### 3.5 Start the voice server

```sh
COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start
```

First load takes ~20 s and writes `logs/rocky_server.log`. Check it with:

```sh
curl -s http://127.0.0.1:59720/health
# {"status":"ok","voice":"rocky"}
```

Stop it with:

```sh
./venv/bin/python rocky_say.py --server stop
```

### 3.6 Build and launch the app

```sh
./scripts/make_app.sh
open -n ./Rocky.app
```

The `.app` bundle is what gives macOS a stable identity for camera and
microphone permission. A bare `python` process is silently denied camera access.
The launcher must **not** use `exec`; see §7.

For development without the camera:

```sh
./venv/bin/python rocky_desktop_app.py
```

---

## 4. Controls

```
F1 hold / F2 toggle   talk (release F1 to send)
F3 or Space           look through the camera
type + Enter          talk by keyboard
1 – 7                 force an emotion (when the input line is empty)
Esc                   quit
```

Emotions: neutral, happy, sad, angry, surprised, sleepy, thinking. The reply
text also selects a mood automatically via `rocky_eyes.mood_for()`.

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ pygame window (main thread)                                         │
│  eyes, subtitles, typed input, state badge, amplitude bloom         │
└───────────────▲─────────────────────────────────────────────────────┘
                │ shared state + jobs queue
┌───────────────┴─────────────────────────────────────────────────────┐
│ worker thread                                                       │
│  job = text | audio | look                                          │
│                                                                     │
│  audio ─► faster-whisper ─► text                                    │
│  text  ─► Brain.stream() ─► sentence_stream() ─► clause_split()     │
│                                      │                              │
│                                      ▼                              │
│                         synthesize() ─► XTTS HTTP server (59720)    │
│                                      │                              │
│                                      ▼                              │
│                         speak() ─► pygame.mixer.Sound.play()        │
│                                                                     │
│  look  ─► Camera.snapshot() ─► Brain.vision() ─► speak()            │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.1 Processes

| Process | Role |
|---|---|
| `rocky_desktop_app.py` | UI, mic, STT, brain client, camera, TTS client, playback |
| `rocky_say.py --server start` | Persistent XTTS server on `127.0.0.1:59720` |
| Ollama | `qwen3-coder` (brain) and `qwen2.5vl:3b` (vision) |
| `Rocky.app` | Launcher bundle that preserves macOS camera/mic identity |

### 5.2 Threads inside the app

- **Main thread** — pygame event loop and rendering at 60 FPS.
- **Worker thread** — consumes `jobs` (`text`, `audio`, `look`), runs the
  pipeline, and calls `speak()`.
- **TTS producer thread** — started per reply by `speak()`; synthesizes ahead of
  playback into a bounded queue (`maxsize=3`).
- **Startup warmers** — voice server, whisper model, and brain model load in
  background daemon threads.

The worker is intentionally simple. It is also why there is no barge-in: while
`speak()` is running, the worker cannot consume a new job, and the microphone is
not open.

### 5.3 Brain client

`Brain` supports three APIs:

- `ollama` (default) — `POST /api/chat`, streaming JSON lines.
- `openai` — any OpenAI-compatible `/chat/completions` endpoint.
- `anthropic` — `/v1/messages` streaming SSE.

Ollama requests set:

```json
{
  "stream": true,
  "keep_alive": "30m",
  "options": {
    "num_predict": 45,
    "temperature": 0.8,
    "top_p": 0.9,
    "num_ctx": 8192
  }
}
```

`num_ctx=8192` matters for `qwen3-coder`: its default 262k context reserves
~45 GB of unified memory. At 8k it is ~19 GB, with no quality loss for one-line
replies. Override with `--brain-context`.

### 5.4 Voice pipeline

1. `Brain.stream()` yields text deltas.
2. `sentence_stream()` yields completed sentences.
3. `clause_split()` splits at commas; the first chunk is capped at 38
   characters so the first sound arrives sooner.
4. `synthesize()` applies the Rocky grammar transform (`rocky_transform`) and
   calls the XTTS server.
5. `speak()` plays each WAV as it arrives and publishes an RMS envelope for the
   eyes.

The server computes XTTS conditioning latents once at startup and reuses them
for every request. `ROCKY_SPEED` (default `1.25`) shortens both audio length and
generation time.

### 5.5 Vision pipeline

`Camera.snapshot()` opens the webcam, discards five warm-up frames, grabs one
640×480 frame, JPEG-encodes it at quality 80, and closes the device. The JPEG is
sent to `Brain.vision()`; local Ollama requests are non-streamed because small
vision models drop their first character when streamed. The reply is spoken as
one sentence and `logs/last_look.jpg` is kept for debugging.

### 5.6 Eyes

`rocky_eyes.py` maintains a parameter dictionary per emotion and interpolates
toward the target each frame. The pupil is drawn into the sclera before the lids
punch transparent holes, so it is clipped cleanly. The pupil follows the visible
band, which is why sleepy looks down rather than smiling. Bloom is derived from
the masked eye, so the lids do not glow.

Run the eye-only self-test:

```sh
./venv/bin/python rocky_eyes.py --selftest shots/eyes
```

---

## 6. Configuration

### 6.1 CLI flags

| Flag | Default | Meaning |
|---|---|---|
| `--no-brain` | off | Echo mode: repeat the user in Rocky grammar |
| `--brain-model` | `qwen3-coder:latest` | Ollama model or hosted model name |
| `--brain-context` | `8192` | Ollama `num_ctx`; lower = less memory |
| `--brain-api` | `ollama` | `ollama`, `openai`, or `anthropic` |
| `--brain-url` | local Ollama | Hosted base URL |
| `--brain-key` | `$BRAIN_API_KEY` | Hosted API key |
| `--vision-model` | `qwen2.5vl:3b` | Vision model |
| `--camera-index` | `0` | Webcam index |
| `--no-camera` | off | Disable F3 |
| `--snap PATH` | — | Grab one frame, save, exit (permission test) |
| `--stt-model` | `base.en` | `tiny.en`, `base.en`, `small.en` |
| `--selftest` | off | Headless STT/brain/vision/UI check |

### 6.2 Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `COQUI_TOS_AGREED` | unset | Required by Coqui TTS to download/run XTTS |
| `ROCKY_SPEED` | `1.25` | XTTS speed factor; higher = faster/shorter |
| `BRAIN_API_KEY` | unset | Hosted brain key |

### 6.3 Hosted brain examples

```sh
./venv/bin/python rocky_desktop_app.py --brain-api openai \
  --brain-url https://api.deepseek.com/v1 \
  --brain-model deepseek-chat --brain-key "$KEY"

./venv/bin/python rocky_desktop_app.py --brain-api anthropic \
  --brain-url https://api.anthropic.com/v1 \
  --brain-model claude-sonnet-4-5 --brain-key "$KEY"
```

Hosted vision uses `--vision-model` with the same API.

---

## 7. Packaging and macOS permissions

`scripts/make_app.sh` generates:

```
Rocky.app/
└── Contents/
    ├── Info.plist
    └── MacOS/
        └── Rocky
```

The launcher is a shell script that `cd`s to the repository and runs
`./venv/bin/python rocky_desktop_app.py "$@"`. It deliberately **does not** use
`exec`: replacing the bundle process would throw away the bundle identity, and
macOS would attribute camera capture to bare Python and silently deny it.

Build, sign ad-hoc, and launch:

```sh
./scripts/make_app.sh
codesign --force --sign - --identifier com.aiserver.rocky ./Rocky.app
open -n ./Rocky.app
```

If macOS prompts for camera or microphone, allow it once. If you re-sign the
bundle and the prompt returns, allow it again; the bundle ID stays
`com.aiserver.rocky`.

---

## 8. Performance

Measured on the development machine (M1 Max, 64 GB, macOS 27.0.1, Python
3.11.17). These are wall-clock measurements, not vendor claims.

| Stage | Measurement |
|---|---|
| XTTS server load | ~22 s cold |
| XTTS synthesis, `"Hi."` | ~3.8 s |
| XTTS synthesis, `"Hello friend."` | ~2.8 s |
| XTTS synthesis, 36 characters | ~2.4 s |
| XTTS synthesis, 47 characters | ~3.5 s |
| `qwen3-coder` first token (warm) | ~0.07–0.15 s |
| `qwen3-coder` full one-line reply | ~0.2 s |
| faster-whisper `base.en` | ~0.4 s after release |
| `qwen2.5vl:3b` vision (warm) | ~0.4 s; ~6 s after a model swap |
| End-to-end first sound | ~3–5 s |

The dominant cost is XTTS, not the brain. The original handoff estimated 2–3 s
to first sound; the per-clause measurements above are more pessimistic and
closer to the observed experience under load.

### 8.1 The `inference_stream` problem

`TTS 0.22.0` exposes `Xtts.inference_stream()`, which should reduce
time-to-first-audio. With the pinned stack (`transformers==4.44.0`,
`torch==2.5.1`), it currently raises:

```text
TypeError: isin() received an invalid combination of arguments
```

The non-streaming `inference()` path used by the server works. Do not assume
`inference_stream` is a drop-in win without pinning or patching the
transformers/torch combination. This is one reason the real-time plan
recommends replacing XTTS rather than tuning it.

---

## 9. Known issues and gotchas

1. **`exec` in the `.app` launcher breaks camera permission.** Keep the
   launcher alive as the parent process.
2. **numpy must stay `<2`.** `gruut` (a TTS dependency) requires it. Installing
   current OpenCV can silently upgrade numpy and break XTTS on the next restart.
   Keep `numpy==1.26.4` and `opencv-python-headless==4.11.0.86`.
3. **The voice server is single-threaded.** Two callers queue behind each
   other; a 1.2 s synthesis can look like 12 s. This is not a bug.
4. **XTTS conditioning is cached.** The server computes latents once at startup;
   the original per-request `tts_to_file` was slower.
5. **Local vision models:** non-streamed requests only. `moondream` drops its
   first character when streamed. `qwen2.5vl` hallucinates at temperature 0.6
   ("you are holding a guitar"); 0.1 with a neutral prompt is accurate.
6. **Ollama model swaps are expensive.** Loading `qwen2.5vl` after
   `qwen3-coder` can take ~6 s. Keep both resident with `keep_alive`, or use a
   single multimodal session in the real-time redesign.
7. **`pygame.mixer` is not a streaming API.** It loads a complete WAV and has
   no sample-accurate cancellation. Barge-in requires `sounddevice`/PyAudio.
8. **The mic is closed while Rocky speaks.** There is no self-hearing loop today
   only because the app is half-duplex. Adding barge-in without AEC will create
   one.
9. **The app is macOS-first.** The voice script runs on Windows, but the camera
   permission model, `.app` bundle, and F-key UI are macOS-specific.

---

## 10. Voice assets and licensing

This repository **does not include**:

```text
assets/rocky_ref_15s.wav
assets/rocky_training_audio_scrubbed.wav
assets/rocky_voice.pth
```

Why:

- The upstream license is **CC BY-NC 4.0** (non-commercial).
- Rocky's voice design is the intellectual property of the *Project Hail Mary*
  film production.
- The training audio and RVC model are for personal, non-commercial use only.
- XTTS v2 / Coqui TTS is licensed under the Coqui Public Model License (CPML),
  which is non-commercial only.

Use `scripts/restore_assets.sh` with your own private copy. Do not commit the
assets, do not redistribute them, and do not use this project commercially.

See [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md), and
[`assets/README.md`](assets/README.md).

---

## 11. Realtime redesign (summary)

The full research-backed plan is in
[`docs/REALTIME_PLAN.md`](docs/REALTIME_PLAN.md). The short version:

- The current pipeline is turn-based, blocking, and full-WAV. Replacing the
  model alone will not fix the feel.
- Build one realtime core with two interchangeable engines:
  1. **OpenAI Realtime** — custom voice, semantic VAD, native interruption,
     image input; fastest path, cloud dependency.
  2. **Pipecat cascade** — Deepgram Nova-3 or Cartesia Ink 2 → local LLM →
     Cartesia Sonic 3.6 or ElevenLabs Flash v2.5 cloned voice; keeps Rocky's
     voice, more control, 500–800 ms target.
- Add macOS AEC via `AVAudioEngine.setVoiceProcessingEnabled(true)`, streaming
  PCM playback, and cancelable TTS.
- Replace the snapshot-only camera with a cheap always-on detector plus an
  on-demand VLM; never run a VLM at 30 FPS.
- Target: p95 speech-end → first audio < 800 ms (cascade) or < 700 ms
  (speech-to-speech), barge-in stop < 150 ms.

Verified facts used in the plan:

- Cartesia Sonic 3.6 streams first audio in ~90 ms and supports instant voice
  cloning from a 10 s clip.
- ElevenLabs Flash v2.5 advertises ~75 ms latency (excluding app/network) and
  instant voice cloning from short samples.
- Deepgram Nova-3 streaming endpointing is configurable (300–500 ms recommended
  for conversational pauses).
- Pipecat provides `LocalAudioTransport`, Silero VAD, Smart Turn v3, and
  interruption handling in Python.
- OpenAI Realtime supports custom voices (audio sample + consent), semantic VAD,
  and `input_image` content.
- Gemini Live accepts JPEG/PNG video frames at up to 1 FPS and returns native
  audio.
- macOS AEC is available through AVFAudio voice processing; `sounddevice` alone
  does not provide it.

---

## 12. Roadmap

The phased plan, acceptance criteria, and decision points are in
[`docs/ROADMAP.md`](docs/ROADMAP.md). In order:

1. **Phase 0** — instrument latency; keep models warm; run a TTS bake-off.
2. **Phase 1** — streaming audio core, VAD, AEC, barge-in, cancelable playback.
3. **Phase 2** — pick the realtime voice engine; stream cloned TTS or use
   OpenAI Realtime.
4. **Phase 3** — continuous camera perception with a cheap detector plus an
   on-demand VLM.
5. **Phase 4** — wake word, memory, offline fallback, cost caps, soak tests,
   packaging.

---

## 13. Testing and verification

```sh
# Eye presets only
./venv/bin/python rocky_eyes.py --selftest shots/eyes

# STT + brain reachability + vision + UI states (no mic/camera)
./venv/bin/python rocky_desktop_app.py --selftest

# Camera permission check through the bundle
open -n ./Rocky.app --args --snap /tmp/cam.jpg
ls -lh /tmp/cam.jpg

# Voice server health
curl -s http://127.0.0.1:59720/health

# Compile check (CI)
python3.11 -m compileall -q rocky_desktop_app.py rocky_eyes.py rocky_say.py app.py
```

The `--selftest` path uses a synthetic 320×240 frame for the vision check, so it
does not need a camera.

---

## 14. Privacy and security

- Local by default: Ollama at `127.0.0.1:11434`, XTTS at `127.0.0.1:59720`.
- No telemetry, no analytics, no cloud calls unless you configure a hosted
  brain or cloud voice.
- The camera is opened only for an explicit look in the current build. A
  planned always-on mode should keep detection local and send frames only on
  demand.
- Do not put API keys in the repository. Use `BRAIN_API_KEY` or a local `.env`
  that is git-ignored.
- Logs may contain transcripts and camera frame paths; treat them as private.

---

## 15. File map

| Path | What |
|---|---|
| `rocky_desktop_app.py` | The app: mic, STT, brain, vision, TTS pipeline, eyes, UI |
| `rocky_eyes.py` | Emotion presets, renderer, `--selftest DIR` |
| `rocky_say.py` | Upstream voice script + persistent XTTS server |
| `app.py` | Older browser version (port 8765), not the primary path |
| `setup.sh` | Python 3.11 venv + dependencies |
| `requirements.txt` | Pinned direct dependencies |
| `scripts/restore_assets.sh` | Copy/verify private voice assets |
| `scripts/make_app.sh` | Build the macOS `.app` bundle |
| `assets/README.md` | Asset placement + licensing warning |
| `shots/` | Rendered eye/emotion/app reference images |
| `docs/` | Architecture, setup, latency, research, roadmap, troubleshooting |
| `LICENSE` | CC BY-NC 4.0 with additional voice-IP restrictions |
| `NOTICE.md` | Attribution and restrictions |

---

## 16. FAQ

**Does it work without internet?**
Yes, if the models and assets are already local. Ollama and XTTS are local. The
default brain and vision paths do not call the internet.

**Why is speech so slow?**
XTTS is the bottleneck. On this machine each clause takes 2.4–3.8 s to
synthesize. The brain is ~0.1–0.2 s. See §8.

**Can I use a different brain?**
Yes: `--brain-model`, `--brain-api`, `--brain-url`, `--brain-key`. Any
OpenAI-compatible endpoint works.

**Can I use a different voice?**
The voice path is XTTS with a reference clip. Replace `assets/rocky_ref_15s.wav`
and restart the server. The upstream `GUIDE.md` covers RVC and other models.

**Why does the camera not work from `python`?**
macOS attributes camera access to the app bundle. Launch `Rocky.app`, not a bare
Python process.

**Why does `inference_stream` fail?**
It is incompatible with the pinned `transformers==4.44.0` / `torch==2.5.1`
combination in this environment (`torch.isin` signature). The non-streaming
server path works. See §8.1.

**Is the voice mine to use?**
Only for personal, non-commercial use. See §10.

---

## 17. Credits

- Original `rocky_say.py` and voice training assets: **Pedram Amini**.
- Upstream repository: **Kuberwastaken/rocky-tts**.
- Eye presets inspired by Casey Grothaus's desk robot
  (`github.com/cgro00/desk-robot`, MIT).
- Rocky character and voice: *Project Hail Mary* film production.
- Coqui XTTS v2: Coqui Public Model License (non-commercial).
- Desktop app, eyes, camera path, and documentation: the local build
  contributors.
