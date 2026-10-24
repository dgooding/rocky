# Real-time redesign plan

Status: **proposal, not implemented**

**Current voice decision (2026-10-23):** the desktop app uses local Kokoro
`bf_emma` with a neutral assistant personality. This document preserves earlier
hosted and cloned-voice research; none of those options are approved for
implementation without explicit user opt-in.

Goal: make Rocky feel like a real-time presence — speech starts in well under a
second, he can be interrupted, the camera is aware of the scene, and the whole
thing survives real-world noise and network problems.

The current app is turn-based and blocking. Historical XTTS measurements
(2.4–3.8 s per clause) apply only to the legacy standalone tool, not the
desktop app's current Kokoro voice path. Replacing the model alone will not
fix the feel; the audio path and orchestration have to change.

## Foundation decision

Rocky's own app is the foundation (owner decision, 2026-10-22). Outside apps
were surveyed in [`OPEN_SOURCE_OPTIONS.md`](OPEN_SOURCE_OPTIONS.md) and not
adopted. The behaviour target is the
[desk robot](https://github.com/cgro00/desk-robot) Rocky is modelled on, whose
brain uses faster-whisper, Silero VAD, and Smart Turn; those remain the
preferred upgrades for the listening path below. Pipecat is still the
preferred orchestration framework to evaluate before writing custom
audio/VAD/cancellation plumbing.

## 1. Target experience

- You start talking; Rocky shows listening immediately.
- When you pause for ~200–300 ms, he starts responding.
- First audio arrives in **500–800 ms** (cascade) or **300–700 ms**
  (speech-to-speech).
- You can interrupt him at any point; audio stops in **<150 ms** and he listens.
- He does not hear himself (AEC + residual echo suppression).
- He can glance at the camera continuously without a 6 s model swap.
- A network failure or missing cloud key falls back to a local mode instead of
  freezing.

## 2. Architecture

```text
mic ──► AEC ──► VAD / turn detection ──┬─ Realtime engine (OpenAI Realtime / Gemini Live)
                                       └─ Cascade engine (STT → LLM → cloned TTS)
                                                  │
                                                  ▼
                                    cancelable PCM playback ──► eyes/UI

camera ──► always-on detector ──► scene gate ──► VLM / realtime vision
```

Build one **realtime core** and two interchangeable engines. The UI, eyes,
camera, and audio device stay the same; the engine can be swapped for a bake-off
or fallback.

### 2.1 Harness

Use [Pipecat](https://github.com/pipecat-ai/pipecat) for the cascade:

- `LocalAudioTransport` (PyAudio) for macOS mic/speakers
- Silero VAD (local, no network round trip)
- Smart Turn v3 (local turn-completion model)
- interruption/barge-in handling
- adapters for Deepgram, Cartesia, ElevenLabs, OpenAI
- `Pipeline` / `FrameProcessor` model for audio and video frames

Pipecat also has an OpenAI Realtime service, so the same harness can run both
engines. LiveKit Agents is an alternative if you want WebRTC/remote clients;
TEN is overkill for a single desktop app.

### 2.2 Engine A — OpenAI Realtime

- Model: `gpt-realtime` family (use the latest available).
- Voice: a **custom voice** created from a consented Rocky audio sample.
- Turn detection: semantic VAD.
- Input: mic audio; `input_image` for camera frames on demand.
- Output: audio; interruption is native (`response.cancel`).
- Pros: one session replaces STT + LLM + TTS; native barge-in; least code;
  fastest path to the target feel.
- Cons: cloud dependency, per-minute cost, voice-clone quality is not guaranteed
  to match XTTS, and the voice IP/consent constraints still apply.

This was the recommended **v1 baseline** when this proposal was written; it is
not the current implementation plan.

### 2.3 Engine B — Pipecat cascade

```text
Deepgram Nova-3 or Cartesia Ink 2
        ↓
local qwen3-coder (or a cloud LLM)
        ↓
Cartesia Sonic 3.6 or ElevenLabs Flash v2.5 (cloned voice)
```

- STT: Deepgram Nova-3 streaming with `endpointing=300` (300–500 ms is the
  documented conversational range), or Cartesia Ink 2 with native turn
  detection.
- LLM: keep the local `qwen3-coder`; it is already ~0.1 s warm.
- TTS: Cartesia Sonic 3.6 (~90 ms first byte, instant clone from 10 s) or
  ElevenLabs Flash v2.5 (~75 ms excluding app/network, instant clone).
- Pros: keeps Rocky's voice; provider-swappable; local LLM; can fall back to
  local TTS.
- Cons: more moving parts; realistic p95 is 500–800 ms; needs AEC and cancel
  logic.

This is the recommended **v2 / quality** path.

### 2.4 Engine C — local fallback

- STT: WhisperKit/CoreML or Parakeet TDT; or faster-whisper small model.
- VAD/turn: Silero + Smart Turn v3.
- LLM: local qwen3-coder.
- TTS: Piper fine-tuned on Rocky's voice, or Kokoro + RVC. XTTS streaming is not
  currently viable (see [`LATENCY.md`](LATENCY.md)).
- Pros: privacy, offline.
- Cons: lower voice quality; more setup; not the primary experience.

## 3. Audio core

### 3.1 Capture

- 16 kHz mono, 20 ms frames, `sounddevice` or PyAudio callback.
- Keep a ring buffer; never block the audio callback.
- Device selection and hot-plug; handle sample-rate changes.

### 3.2 AEC

macOS provides acoustic echo cancellation through AVFAudio voice processing:

```swift
let engine = AVAudioEngine()
try engine.inputNode.setVoiceProcessingEnabled(true)
```

`sounddevice`/PortAudio alone does **not** provide AEC. Options:

1. A small Swift helper using `AVAudioEngine` voice processing, exposed to
   Python (pipe/Unix socket or PyObjC).
2. WebRTC's audio processing module (AEC/NS/AGC) if you already run a WebRTC
   transport.
3. Headphones as the initial fallback; do not ship always-on barge-in without
   AEC.

### 3.3 Playback

Replace `pygame.mixer` with a streaming output:

- `sounddevice.RawOutputStream` (or PyAudio) with a PCM ring buffer.
- 20–50 ms buffer target; adaptive if underruns.
- On barge-in: stop pulling, flush the ring buffer, cancel the TTS request, and
  transition to LISTENING.
- Keep eyes/amplitude in sync from the same PCM chunks.

### 3.4 Barge-in

- VAD runs continuously, including during playback.
- If speech is detected while SPEAKING: stop audio within 150 ms, cancel the
  LLM/TTS tasks, and send a cancel event to the engine (OpenAI
  `response.cancel`, Cartesia context cancel, etc.).
- Debounce coughs/noise; require 100–150 ms of speech energy before interrupting.
- Do not reopen the mic until the AEC filter has adapted; otherwise Rocky hears
  his own tail.

## 4. Turn detection

Use two layers:

1. **Energy VAD** (Silero) for speech start/stop.
2. **Semantic turn detection** (Pipecat Smart Turn v3, LiveKit turn detector,
   Deepgram endpointing, or OpenAI semantic VAD) to decide whether a pause is a
   real end-of-turn.

Target 200–300 ms after speech end. A fixed 1 s silence timeout feels sluggish;
a 100 ms timeout cuts people off. Make it adaptive and expose a "hold to talk"
mode for noisy rooms.

### Advanced: speculative start

Streaming STT gives partial transcripts. You can start the LLM on a
likely-complete partial and cancel if the user keeps talking. This can save
200–300 ms but risks false starts. Prototype behind a flag; do not make it the
default until measured.

## 5. Voice output

### 5.1 Required properties

- streaming PCM/WebSocket chunks, not a full WAV
- first chunk <150 ms (model + network)
- cancelable context
- instant voice clone from a short sample
- stable prosody across short clauses

### 5.2 Candidates

| Engine | Claim | Clone | Notes |
|---|---|---|---|
| Cartesia Sonic 3.6 | ~90 ms first byte | Instant, 10 s | WebSocket continuations; strong candidate |
| ElevenLabs Flash v2.5 | ~75 ms (excl. app/network) | Instant, short sample | Mature SDK; per-character pricing |
| OpenAI Realtime | native audio | Custom voice from sample + consent | One session; cloud |
| XTTS v2 | 2.4–3.8 s/clause here | Zero-shot, 15 s | Too slow; streaming broken |
| Piper | fast local | **No zero-shot clone** | Fine-tune on Rocky for offline |
| Kokoro | fast local | **No clone** | Pair with RVC if needed |

Do not repeat the claim that Piper does zero-shot cloning; it does not. It can
be fine-tuned, which is a different workflow.

### 5.3 Latency masking

- Pre-generate 5–10 neutral local assistant backchannels ("Mm", "Yes", "Okay",
  "Hm?").
  Play one immediately when the user stops speaking, then replace it with the
  real answer when ready.
- Start TTS on the first 3–6 words, not the first full sentence.
- Stream subtitles and eye reactions immediately.
- Use a short earcon or thinking animation only if it does not add delay.

## 6. Camera and vision

### 6.1 Always-on, cheap layer

- Capture 640×480 @ 30 FPS in a background thread; keep the latest frame.
- Run MediaPipe Face/Hands/Pose or YOLOv8n/YOLO11n on a downscaled frame at
  5–10 FPS.
- Detect presence, face, hands, held objects, and scene changes.
- This layer is local, low-power, and privacy-preserving.

### 6.2 On-demand VLM

- Send a JPEG (320–512 px, quality 70) only when:
  - the user asks a visual question,
  - the scene changes significantly, or
  - the cheap detector sees an unknown object/gesture.
- Local candidates: Moondream 2, SmolVLM2, qwen2.5vl:3b kept warm.
- Cloud candidates: Gemini Live (JPEG frames up to 1 FPS) or OpenAI Realtime
  `input_image`.
- Never run a VLM at 30 FPS. It is wasteful and will melt the machine.

### 6.3 Privacy UX

- Camera indicator is mandatory; macOS also shows a green LED.
- Default to explicit "look" mode; always-on mode is opt-in.
- Keep detection local; cloud frames require a clear toggle.
- Add a physical shutter or a one-key "camera off".

## 7. Latency budget

| Stage | Current | Target | Mechanism |
|---|---:|---:|---|
| Speech-end detection | key release | 200–300 ms | Silero + Smart Turn / endpointing |
| STT final | ~0.4 s | 100–250 ms | Streaming Nova-3 / Ink 2 / WhisperKit |
| LLM first token | 0.07–0.15 s | 100–300 ms | Streamed, short prompt |
| TTS first audio | 2.4–3.8 s | 75–150 ms + network | Cartesia / ElevenLabs |
| Playback buffer | full WAV | 20–50 ms | PCM ring buffer |
| **First sound** | **3–5 s** | **500–800 ms / 300–700 ms** | Overlap + streaming |

## 8. Phases

### Phase 0 — Instrument the local path (0.5–1 day)

- Add timestamps: speech-end, STT-final, LLM-first-token, TTS-first-byte,
  first-audio-played, barge-in-stop.
- Log p50/p95 over 20 turns; store a small JSONL trace.
- Keep brain and vision models warm; avoid Ollama swaps.
- Benchmark warm Kokoro synthesis and first-audio latency.
- Compare local British Kokoro presets with the user.

**Exit:** a measured baseline for the selected local voice path.

### Phase 1 — Realtime audio core (2–3 days)

- Continuous mic + Silero VAD.
- Streaming PCM playback.
- Cancelable TTS/LLM tasks.
- Barge-in state machine.
- macOS AEC helper (or headphones fallback).
- Pre-generated local assistant backchannels.

**Exit:** p95 speech-end → first audio <800 ms; barge-in stop <150 ms; no
self-hearing.

### Phase 2 — Local voice responsiveness (2–3 days)

- Optimize and benchmark Kokoro for the default British preset.
- Keep the macOS system voice available as a local fallback.
- Tune first-clause length and TTS continuations.

**Exit:** local voice is accepted; fallback works; warm latency is measured.

### Phase 3 — Vision (2–3 days)

- Continuous capture + cheap detector.
- Scene-change gating.
- On-demand VLM (local or same realtime session).
- Camera UX: indicator, explicit look mode, privacy toggle.

**Exit:** "what am I holding?" <1.5 s; "did the user leave?" <1 s; no VLM at
30 FPS.

### Phase 4 — Real-world hardening (3–5 days)

- Wake word (`openWakeWord`) or push-to-talk.
- Conversation memory and persona tuning.
- Network-loss/offline fallback.
- Cost caps and per-turn limits.
- 30-minute soak, device hot-plug, sleep/wake.
- Packaging/signing, logs, crash reporting (local only).

**Exit:** 50-turn scripted conversation in a noisy room with no stuck state.

## 9. Acceptance criteria

- p95 speech-end → first audio <800 ms (cascade) / <700 ms (S2S).
- Barge-in stops audio <150 ms.
- No self-hearing with speakers at normal volume.
- 50 turns without a stuck state or duplicate reply.
- Camera answer <1.5 s for "what am I holding?".
- 30-minute soak with stable memory and no audio underruns.
- Offline fallback still responds (even if slower).
- No camera frame leaves the machine unless the user enabled cloud vision.

## 10. Decision points

1. **Cloud or local-first?** Cloud buys latency; local buys privacy.
2. **Voice fidelity vs latency?** OpenAI Realtime is simplest; Cartesia /
   ElevenLabs give more control over the clone.
3. **Always-listening or wake word/push-to-talk?** Always-on needs AEC and a
   privacy UX.
4. **Budget cap?** Realtime audio is per-minute; video adds cost.
5. **Voice rights?** Rocky's voice is film IP; personal/non-commercial only.

## 11. What not to do

- Do not try to tune XTTS into sub-second by shrinking chunks; fixed overhead
  dominates and `inference_stream` is broken here.
- Do not use `pygame.mixer` for streaming playback; it cannot cancel cleanly.
- Do not run a VLM on every camera frame.
- Do not enable always-on camera without an indicator and consent.
- Do not rely on Ollama keeping two models resident unless you set
  `keep_alive` and verify memory.
- Do not ship barge-in without AEC; the feedback loop will be obvious.

## 12. Sources

- [Cartesia overview](https://docs.cartesia.ai/get-started/overview) — Sonic 3.6
  ~90 ms first byte, instant clone from 10 s.
- [ElevenLabs models](https://elevenlabs.io/docs/overview/models) — Flash v2.5
  ~75 ms excluding app/network.
- [ElevenLabs instant voice cloning](https://elevenlabs.io/docs/eleven-api/concepts/voice-cloning)
- [Deepgram endpointing](https://developers.deepgram.com/docs/understand-endpointing-interim-results)
- [Pipecat local audio transport](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/transports/local/audio.py)
- [Pipecat Smart Turn](https://github.com/pipecat-ai/docs/blob/main/pipecat-cloud/guides/smart-turn.mdx)
- [OpenAI Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [OpenAI custom voices](https://developers.openai.com/api/docs/guides/custom-voices)
- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk)
- [AVAudioEngine voice processing](https://developer.apple.com/documentation/avfaudio/avaudionode/setvoiceprocessingenabled(_:))

See [`RESEARCH.md`](RESEARCH.md) for the verification notes and caveats.
