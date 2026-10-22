# Roadmap

The goal is a desk companion that feels present: sub-second speech, natural
interruption, continuous awareness, and graceful failure. Work is ordered by
risk and by what unlocks the most perceived improvement.

Status: proposal. Nothing below is implemented yet unless marked.

## Phase 0 — Instrument and decide (0.5–1 day)

- [ ] Add latency marks: speech-end, STT-final, LLM-first-token,
  TTS-first-byte, first-audio-played, barge-in-stop.
- [ ] Write a JSONL trace per turn; compute p50/p95 over 20 turns.
- [ ] Keep `qwen3-coder` and `qwen2.5vl` resident; verify `keep_alive`.
- [ ] Record the current XTTS baseline on this machine.
- [ ] Confirm voice-clone consent and a monthly cloud budget cap.
- [ ] Run a one-day A/B: OpenAI Realtime vs Cartesia/ElevenLabs cascade.

**Exit:** measured baseline; primary engine chosen; fallback chosen.

## Phase 1 — Realtime audio core (2–3 days)

- [ ] Continuous 16 kHz mic capture with 20 ms frames.
- [ ] Silero VAD + Smart Turn v3 / semantic endpointing.
- [ ] Replace `pygame.mixer` with `sounddevice`/PyAudio PCM playback.
- [ ] Add a cancelable audio ring buffer.
- [ ] Implement barge-in: stop, flush, cancel, listen.
- [ ] Add macOS AEC via `AVAudioEngine` voice processing (or headphones
  fallback).
- [ ] Pre-generate 5–10 backchannels in Rocky's voice.
- [ ] Add a `LISTENING → THINKING → SPEAKING → INTERRUPTED` state machine.

**Exit:** p95 speech-end → first audio <800 ms; barge-in stop <150 ms; no
self-hearing.

## Phase 2 — Voice engine (2–3 days)

- [ ] Define a `RealtimeSession` interface (audio in/out, cancel, events).
- [ ] Implement the primary engine.
- [ ] Implement the fallback engine.
- [ ] Tune first-clause length and TTS continuations.
- [ ] Measure clone similarity (blind test, 10–20 phrases).
- [ ] Measure cost per 100 turns.
- [ ] Add a voice-consent note to the UI/docs.

**Exit:** primary voice accepted; fallback works; cost is understood.

## Phase 3 — Vision (2–3 days)

- [ ] Continuous camera capture at 640×480/30 FPS in a background thread.
- [ ] MediaPipe/YOLO detector at 5–10 FPS (presence, face, hands, objects).
- [ ] Scene-change gating (perceptual hash or frame diff).
- [ ] On-demand VLM: local Moondream/SmolVLM/qwen2.5vl or the realtime session.
- [ ] Camera indicator, explicit look mode, privacy toggle.
- [ ] Save `logs/last_look.jpg` for debugging.

**Exit:** "what am I holding?" <1.5 s; "did the user leave?" <1 s; no VLM at
30 FPS.

## Phase 4 — Real-world hardening (3–5 days)

- [ ] Wake word (`openWakeWord`) or a clear push-to-talk mode.
- [ ] Conversation memory with a short context window.
- [ ] Offline/local fallback when the cloud is unavailable.
- [ ] Cost caps, per-turn limits, and a kill switch.
- [ ] 30-minute soak; device hot-plug; sleep/wake.
- [ ] Log rotation and local-only crash reporting.
- [ ] Packaging/signing; rebuild instructions.
- [ ] 50-turn scripted conversation in a noisy room.

**Exit:** 50 turns without stuck state; no duplicate replies; stable memory;
fallback works.

## Later / exploratory

- [ ] Full-duplex speech-to-speech with local Moshi/Qwen-Omni for offline.
- [ ] RVC or Piper fine-tune for a fully local cloned voice.
- [ ] Multi-person awareness (who is speaking / who is present).
- [ ] Gesture control (wave to wake, palm to stop).
- [ ] Menu-bar controls and global hotkeys.
- [ ] Optional ESP32 display build (GC9A01 round displays).

## Guiding principles

1. Measure p95, not the demo.
2. Prefer streaming and cancellation over faster batch calls.
3. Keep the local path working; cloud is an enhancement, not a requirement.
4. Never trade privacy for latency without an explicit opt-in.
5. Do not redistribute voice assets.
6. A short backchannel is better than a spinner.

## Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-10-21 | `qwen3-coder:latest` becomes the default brain, `num_ctx=8192` | Warm first token ~0.1 s; 8k keeps memory at ~19 GB |
| 2026-10-22 | Reject XTTS as the real-time path | Measured 2.4–3.8 s/clause; `inference_stream` broken |
| 2026-10-22 | Plan a two-engine realtime core | OpenAI Realtime for speed; Pipecat cascade for voice/control |
| 2026-10-22 | Exclude voice assets from the public repo | CC BY-NC + film IP restrictions |
