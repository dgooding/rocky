# Roadmap

The goal is a local assistant that feels present: responsive natural speech,
interruption, opt-in awareness, and graceful failure. It has animated eyes
inspired by Casey Grothaus's [desk robot](https://github.com/cgro00/desk-robot).

**Voice decision (2026-10-23):** Kokoro `bf_emma` is the local default, with a
neutral conversational assistant personality. Older voice-clone and hosted
provider experiments below are historical research, not approved work; do not
route speech or other data to a cloud service without explicit user opt-in.

Status: in progress. Items are not implemented unless checked.

## Phase 0 — Instrument and decide (0.5–1 day)

- [x] Decide the foundation: build on Rocky's own app (owner decision,
  2026-10-22). The outside-app survey is in
  [`OPEN_SOURCE_OPTIONS.md`](OPEN_SOURCE_OPTIONS.md) for reference.
- [x] Senses in the app: hearing (hands-free, "hey Rocky") and sight (webcam).
- [ ] Verify hearing and sight on the Mac (see `AGENTS.md`).
- [ ] Add latency marks: speech-end, STT-final, LLM-first-token,
  TTS-first-byte, first-audio-played, barge-in-stop.
- [ ] Write a JSONL trace per turn; compute p50/p95 over 20 turns.
- [ ] Keep `qwen3-coder` and `qwen2.5vl` resident; verify `keep_alive`.
- [ ] Benchmark warm Kokoro synthesis and first-audio latency.
- [ ] Compare local British Kokoro presets with the user.

**Exit:** local pipeline baseline measured; Kokoro default and macOS fallback
characterized.

## Phase 1 — Realtime audio core (2–3 days)

- [x] Continuous 16 kHz mic capture with 20 ms frames.
- [ ] Silero VAD + Smart Turn v3 / semantic endpointing (today: adaptive
  energy endpointing, configurable 200–2000 ms pause; 700 ms default).
- [x] Stream playback as 20 ms PCM blocks from each synthesized WAV.
- [ ] Keep one output stream open and add a cancelable audio ring buffer.
- [x] F1 manually stops playback, cancels the text stream, and starts
  push-to-talk.
- [ ] Add automatic voice barge-in: detect speech while playing, flush, cancel,
  and listen (requires AEC first).
- [ ] Add macOS AEC via `AVAudioEngine` voice processing (or headphones
  fallback).
- [ ] Pre-generate 5–10 neutral assistant backchannels locally.
- [ ] Add a complete `LISTENING → THINKING → SPEAKING → INTERRUPTED` state
  machine; current cancellation is an event over the existing states.

**Exit:** p95 speech-end → first audio <800 ms; barge-in stop <150 ms; no
self-hearing.

## Phase 2 — Local voice responsiveness (2–3 days)

- [ ] Optimize and benchmark Kokoro synthesis for the default British preset.
- [ ] Keep the macOS system voice available as a local fallback.
- [ ] Tune first-clause length and TTS continuations.

**Exit:** local voice is accepted; fallback works; warm latency is measured.

## Phase 3 — Vision (2–3 days)

- [x] Background camera capture (opt-in watch mode), latest frame shared.
- [x] Local face detector (OpenCV Haar cascade, 4 fps): eyes follow you,
  arrive/leave events. MediaPipe/YOLO for hands and objects is still open.
- [ ] Scene-change gating (perceptual hash or frame diff).
- [x] On-demand VLM from speech ("what am I holding?") via local `qwen2.5vl:3b`.
- [x] Camera indicator ("watching"), explicit look mode, privacy toggle (F5).
- [x] Save `logs/last_look.jpg` for debugging.

**Exit:** "what am I holding?" <1.5 s; "did the user leave?" <1 s; no VLM at
30 FPS.

## Phase 4 — Real-world hardening (3–5 days)

- [x] Wake phrase "hey Rocky" + push-to-talk + "Rocky, sleep" (`openWakeWord`
  is an option to avoid transcribing room talk while asleep).
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
- [ ] RVC or Piper fine-tune for a fully local cloned voice (out of current
  scope; revisit only after an explicit owner decision).
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
| 2026-10-22 | Build on Rocky's own app; no outside app | Owner decision after the survey; outside candidates were Chinese-first or off-target |
| 2026-10-22 | Senses: hearing (hands-free, "hey Rocky") and sight (webcam) | Match the desk robot (cgro00/desk-robot) Rocky is modelled on |
| 2026-10-22 | Watch mode is opt-in; mic pauses while he speaks | No hidden camera capture; no AEC yet, so he must not hear himself |
| 2026-10-22 | Large files via `scripts/fetch_assets.sh`, never git | Voice files are restricted IP; models are tens of GB |
