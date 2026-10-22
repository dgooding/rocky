# Architecture

This document describes the current turn-based app and the seams that the
real-time redesign will replace. For the target design, see
[`REALTIME_PLAN.md`](REALTIME_PLAN.md).

## Process and thread model

```text
Rocky.app (launcher shell)
└── python rocky_desktop_app.py
    ├── main thread: pygame event loop, rendering, typed input
    ├── worker thread: jobs queue → STT / brain / vision → speak()
    ├── TTS producer thread (one per reply): synthesize ahead of playback
    └── startup warmers: voice server, whisper model, brain model

rocky_say.py --server start
└── separate process: XTTS v2 + HTTP server on 127.0.0.1:59720

Ollama
├── qwen3-coder:latest  (brain, streamed)
└── qwen2.5vl:3b        (vision, non-streamed)
```

The main thread never blocks on network or model work. The worker owns the
conversation pipeline. The TTS producer is a per-reply daemon thread feeding a
bounded `queue.Queue(maxsize=3)` so synthesis can run ahead of playback without
unbounded memory growth.

## State

The UI reads module-level state:

- `state` — `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`
- `subtitle` — what was heard or what Rocky is saying
- `note` — transient errors/hints
- `amplitude` — RMS envelope of the currently playing audio
- `eyes_emotion` — selected emotion preset

The worker and audio callback update these; the render loop snapshots them at
60 FPS. This is intentionally simple. A real-time build should replace it with a
small thread-safe state object plus an asyncio event bus.

## Pipeline

### 1. Input

`Mic` opens a 16 kHz mono `sounddevice.InputStream` with 1024-frame blocks and
accumulates float32 frames until `stop()`. There is no VAD and no streaming; the
entire utterance is transcribed after the key is released.

`Transcriber` lazily loads faster-whisper `base.en` on CPU with `int8`. It
rejects audio shorter than 100 ms or quieter than 0.008 peak.

### 2. Brain

`Brain.stream()` sends a system prompt plus the user text to Ollama
`/api/chat`, OpenAI `/chat/completions`, or Anthropic `/messages`, and yields
text deltas. Ollama requests use `num_predict=45`, `temperature=0.8`,
`top_p=0.9`, `num_ctx=8192`, and `keep_alive=30m`.

The system prompt constrains Rocky to one short sentence, plain English, no
markdown, and no mention of being an AI.

### 3. Sentence and clause splitting

`sentence_stream()` buffers deltas until `[.!?]` followed by whitespace/end,
then yields the sentence. `clause_split()` splits at commas; the first chunk is
limited to 38 characters (`first_limit`) and later chunks to 90 (`limit`). This
is the main latency optimization in the current app: the first short clause can
be synthesized while the rest of the reply is still being generated.

### 4. Voice

`synthesize()` applies `rocky_transform()` (the upstream grammar rewrite) and
calls the XTTS server with `POST /` and `{"text": "..."}`. The server returns a
complete WAV. The server caches XTTS conditioning latents at startup:

```python
gpt_cond, spk_emb = model.get_conditioning_latents(audio_path=[REFERENCE])
out = model.inference(text, "en", gpt_cond, spk_emb, speed=SPEED)
```

`ROCKY_SPEED` defaults to 1.25. The server is single-threaded.

### 5. Playback

`play_with_envelope()` writes the WAV to `logs/desk_last.wav`, loads it into
`pygame.mixer.Sound`, plays it, and publishes an RMS envelope for the eyes. It
waits for the channel to become idle. This is blocking and not cancelable at
sample granularity.

### 6. Vision

`Camera.snapshot()` opens OpenCV `VideoCapture`, sets 640×480, discards five
warm-up frames, grabs one frame, JPEG-encodes it at quality 80, and releases the
device. `Brain.vision()` sends it to Ollama (non-streamed) or a hosted
vision-capable model. The reply goes through the same `speak()` path.

### 7. Eyes

`rocky_eyes.Eyes` holds a parameter dict per emotion and interpolates toward the
target. `render()` draws sclera, pupil, lids, and bloom. The pupil is drawn into
the sclera before the lids punch transparent holes, and it follows the visible
band, so sleepy looks down. Bloom is derived from the masked eye.

## Coupling and seams

| Seam | Current | Real-time replacement |
|---|---|---|
| Mic | push-to-talk, whole utterance | continuous 20 ms frames + VAD |
| STT | batch faster-whisper | streaming Nova-3 / Ink 2 / WhisperKit |
| Turn detection | key release | Silero VAD + Smart Turn v3 / semantic VAD |
| Brain | streamed tokens | unchanged, maybe cloud |
| TTS | HTTP full WAV | WebSocket PCM chunks, cancelable |
| Playback | `pygame.mixer` | `sounddevice.RawOutputStream` ring buffer |
| Barge-in | none | VAD during playback + cancel/flush |
| AEC | none | `AVAudioEngine` voice processing |
| Vision | one snapshot | always-on detector + on-demand VLM |
| State | module globals | thread-safe state + asyncio bus |

## Why the current design cannot feel real-time

1. **No overlap between listening and speaking.** The worker blocks in `speak()`
   until playback ends.
2. **Full-WAV TTS.** Playback cannot start until the entire clause is
   synthesized. XTTS takes 2.4–3.8 s per clause here.
3. **No endpointing.** The app waits for a key release, not for a natural pause.
4. **No cancellation.** Stopping mid-reply would require killing the worker or
   the TTS request; there is no audio-buffer flush.
5. **No AEC.** Opening the mic during playback would feed Rocky's own voice back
   into the recognizer.
6. **Camera is a one-shot.** There is no continuous frame source, no scene-change
   gating, and no cheap detector.

The fix is architectural, not a model swap. See the plan.
