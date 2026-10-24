# Architecture

This document describes the current turn-based app and the seams that the
real-time redesign will replace. For the target design, see
[`REALTIME_PLAN.md`](REALTIME_PLAN.md).

## Process and thread model

```text
Rocky.app (launcher shell)
└── python rocky_desktop_app.py
    ├── main thread: pygame event loop, rendering, typed input
    ├── worker thread: jobs queue → STT / wake check / brain / vision → speak()
    ├── ears thread: continuous mic frames → Endpointer → jobs (hands-free)
    ├── watcher thread (watch mode only): webcam → face detection → face_pos, jobs
    ├── TTS producer thread (one per reply): synthesize ahead of playback
    └── startup warmers: whisper model, brain model

rocky_say.py --server start (standalone legacy tool)
└── separate process: XTTS v2 + HTTP server on 127.0.0.1:59720

rocky_drama3_worker.py (started lazily for default speech)
└── isolated MLX runtime: Drama 3 model + local British voice reference

Ollama
├── qwen3-coder:latest  (brain, streamed)
└── qwen2.5vl:3b        (vision, non-streamed)
```

The main thread never blocks on network or model work. The worker owns the
conversation pipeline. The TTS producer is a per-reply daemon thread feeding a
bounded `queue.Queue(maxsize=3)` so synthesis can run ahead of playback without
unbounded memory growth. Speech is generated locally by Drama 3 by default;
Kokoro and macOS `say` are alternatives. The legacy XTTS tool is separate.

## State

The UI reads module-level state:

- `state` — `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`
- `subtitle` — what was heard or what Rocky is saying
- `note` — transient errors/hints
- `amplitude` — RMS envelope of the currently playing audio
- `eyes_emotion` — selected emotion preset

The worker and audio callback update these; the render loop snapshots them at
60 FPS. This is intentionally simple. F1 can cancel the active text response
and playback to start push-to-talk. A Drama 3 synthesis request already in
flight may finish in the background. Automatic voice interruption is not enabled
because the microphone remains paused during playback to avoid self-hearing.
A real-time build should replace this with a small thread-safe state object plus
an asyncio event bus.

## Pipeline

### 1. Input

Two paths feed the same `jobs` queue:

- **Hands-free (`Ears`, default).** A continuous 16 kHz mono stream in 20 ms
  frames goes to `Endpointer`, which tracks an adaptive noise floor, starts an
  utterance after 80 ms of loud frames (keeping 300 ms of pre-roll), and ends
  it after a configurable quiet interval (700 ms by default, 200–2000 ms);
  utterances under 250 ms of speech are dropped. Ears
  ignore the mic unless Rocky is idle or listening, and for 0.4 s after his
  audio stops, because there is no echo cancellation. In the worker, an
  utterance is answered only if it contains "hey Rocky" or he is still awake
  (`awake_until`, 60 s after each exchange); "Rocky, sleep" resets it. Common
  faster-whisper phantoms in room noise ("thank you", "you") are ignored. This
  mirrors the [desk robot](https://github.com/cgro00/desk-robot), which uses
  Silero VAD and Smart Turn for the same job.
- **Push-to-talk (`Mic`).** F1/F2 open a 1024-frame stream and transcribe the
  whole utterance when the key is released; no wake phrase is needed.

`Transcriber` lazily loads faster-whisper `base.en` on CPU with `int8`. It
rejects audio shorter than 100 ms or quieter than 0.008 peak.

### 2. Brain

`Brain.stream()` sends a system prompt plus the user text to Ollama
`/api/chat`, OpenAI `/chat/completions`, or Anthropic `/messages`, and yields
text deltas. Ollama requests use a 48-token limit by default and 220 tokens
when the user explicitly asks for detail or continuation. Other settings are
`temperature=0.8`, `top_p=0.9`, `num_ctx=8192`, and `keep_alive=30m`.

The system prompt requests a short answer for straightforward questions and
enough concrete detail when the user asks for a description or explanation.

### 3. Sentence and clause splitting

`sentence_stream()` buffers deltas until `[.!?]` followed by whitespace/end,
then yields the sentence. `clause_split()` splits at commas; the first chunk is
limited to 38 characters (`first_limit`) and later chunks to 90 (`limit`). This
is the main latency optimization in the current app: the first short clause can
be synthesized while the rest of the reply is still being generated.

### 4. Voice

By default, `synthesize()` sends text to a persistent local worker running
Fish Audio Drama 3 through MLX. The worker loads the model once, conditions
generation on a locally generated Kokoro `bf_emma` British female voice
reference, and returns WAV audio to the app. The app adds no breathing effects
and applies a 1.15x pitch-preserving tempo adjustment.
The worker uses an isolated Python environment and model cache at
`~/.cache/rocky`; run `./scripts/setup_drama3.sh` to prepare them. The
22 GiB model peaks around 26 GiB of memory, so other large models may compete
for unified memory.

Kokoro remains available with `--tts-engine kokoro` and `--kokoro-voice`.
`--tts-engine macos` uses an installed system voice. The separate legacy
`rocky_say.py` tool continues to use XTTS and voice assets.

### 5. Playback

`play_with_envelope()` decodes the complete AIFF/WAV to float PCM, then writes 20 ms
blocks to `sounddevice.OutputStream` and publishes each block's RMS for the
eyes. Cancellation is checked between writes, so stop latency is bounded by a
small audio block plus the device buffer. This streams playback, not synthesis:
the selected voice engine produces its audio for the clause before the first
block can play.

### 6. Vision

`Camera.snapshot()` opens OpenCV `VideoCapture`, sets 640×480, discards five
warm-up frames, grabs one frame, JPEG-encodes it at quality 80, and releases the
device. When watch mode is on it reuses the watcher's latest frame instead of
reopening the camera. `Brain.vision()` sends it to Ollama (non-streamed) or a
hosted vision-capable model. The reply goes through the same `speak()` path.

A look is triggered by F3/Space or by speech or typing that matches
`LOOK_PATTERN` ("what do you see?", "what am I holding?", "look left", ...); the
question itself is passed to the vision model. "look left/right/up/down" first
points his eyes that way (`gaze_override`), standing in for the desk robot's
head turn.

**Watch mode** (`Watcher`, opt-in: F5, "track me", or `--watch`) keeps the
camera open and runs OpenCV's bundled Haar frontal-face cascade at 4 fps on a
320×240 grayscale frame. The largest face sets `face_pos` (-1..1), which the
render loop turns into gaze so his eyes follow you. Two detections in a row post
an `arrived` event (his eyes perk up); 8 s without a face posts `left` (they get
sleepy). Nothing is sent anywhere unless you ask what he sees.

### 7. Eyes

`rocky_eyes.Eyes` holds a parameter dict per emotion and interpolates toward the
target. `render()` draws sclera, pupil, lids, and bloom. The pupil is drawn into
the sclera before the lids punch transparent holes, and it follows the visible
band, so sleepy looks down. Bloom is derived from the masked eye. When hands-free
is on and he is asleep, idle, and nobody is in view, he dozes (sleepy preset).
The top-right of the window always shows which senses are on.

## Coupling and seams

| Seam | Current | Real-time replacement |
|---|---|---|
| Mic | continuous 20 ms frames + energy endpointer (hands-free); push-to-talk | add Silero VAD |
| STT | batch faster-whisper | streaming Nova-3 / Ink 2 / WhisperKit |
| Turn detection | configurable 200–2000 ms energy silence (700 ms default), or key release | Silero VAD + Smart Turn v3 / semantic VAD |
| Brain | streamed tokens | unchanged, maybe cloud |
| TTS | HTTP full WAV | WebSocket PCM chunks, cancelable |
| Playback | per-clip `sounddevice.OutputStream`, 20 ms PCM writes | persistent output stream / PCM ring buffer |
| Barge-in | none (mic ignored while he speaks) | VAD during playback + cancel/flush |
| AEC | none | `AVAudioEngine` voice processing |
| Vision | on-request snapshot + opt-in face watcher | scene gating + on-demand VLM |
| State | module globals | thread-safe state + asyncio bus |

## Why the current design cannot feel real-time

1. **No overlap between listening and speaking.** The worker blocks in `speak()`
   until playback ends, and hands-free listening is paused meanwhile.
2. **Full-clause TTS.** Playback streams small PCM blocks, but cannot start
   until the clause is synthesized. One Kokoro smoke check measured 0.30 s for
   a subsequent phrase in the same process; the 2.4–3.8 s XTTS figures are
   legacy-tool results, and neither is a statistical benchmark.
3. **Simple endpointing.** A configurable energy pause (700 ms default) ends a
   turn; it cannot tell a finished sentence from a thinking pause the way Smart
   Turn can.
4. **No cancellation.** Stopping mid-reply would require killing the worker or
   the TTS request; there is no audio-buffer flush.
5. **No AEC.** Opening the mic during playback would feed Rocky's own voice back
   into the recognizer, which is why hands-free listening pauses while he speaks.
   F1 provides manual interruption; automatic voice barge-in still requires AEC.
6. **Vision is still on request.** Watch mode follows faces, but there is no
   scene-change gating to decide when a fresh look is worth a VLM call.

The fix is architectural, not a model swap. See the plan.
