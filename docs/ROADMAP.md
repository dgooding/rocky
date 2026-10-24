# Roadmap

The goal is a local assistant that feels present: responsive natural speech,
interruption, opt-in awareness, and graceful failure. It has animated eyes
inspired by Casey Grothaus's [desk robot](https://github.com/cgro00/desk-robot).

**Voice decision (2026-10-23):** local Drama 3 through MLX is the default,
conditioned on a locally generated generic British female Kokoro reference
without inserted breathing effects and with a slightly faster speaking pace.
Kokoro remains a local fallback. Older hosted provider experiments below are historical research;
the local-only requirement still applies.

Status: in progress. Items are not implemented unless checked.

## Adoption plan from the 2026-10-23 project review

Apply one change at a time inside Rocky's existing app. Do not replace the
app, voice stack, or local models based on project descriptions alone. Keep
audio, transcripts, and camera frames local; traces must not contain raw
captures or conversation text by default.

1. **Bounded recovery actions — incorporated.** Spoken/typed recovery requests
   map to a typed request and only run the requested local device check or
   brain/voice checks. Keep OS changes, installs, permission changes, file
   deletion, arbitrary shell execution, and cloud calls out of this path.
   Extend this action surface only with explicit allowlisted behavior and
   tests for both supported and rejected requests.
2. **Make turns observable — next.** Add local structured turn events for
   capture, wake/endpoint, STT, action/brain, TTS, first playback, completion,
   cancellation, and errors. Record stage durations and outcome, not audio,
   frames, or transcript content. Use the traces to establish p50/p95 and
   failure counts over at least 20 turns before changing speech models.
   Rotate logs and make trace collection easy to disable.
3. **Compare endpointing — after the baseline.** Benchmark the current
   energy-based endpoint against Silero VAD on the same opt-in local test
   utterances, including quiet speech, pauses, and room noise. Track missed
   speech, false endpoints, pause-to-submit latency, and CPU/startup cost.
   Keep the current endpoint as the fallback; adopt VAD only if it improves
   real Mac results without regressions and its model terms are verified.
4. **Test wake detection separately.** If asleep-state transcription or false
   wakeups are a problem, compare an optional openWakeWord prefilter against
   the current transcribed "hey Rocky" path. Measure false wakes, missed
   wakes, idle CPU, and model startup cost. Do not enable it by default until
   it passes the same real-room test and its model terms are checked.
5. **Revisit pipeline frameworks only if needed.** Use Hugging Face
   speech-to-speech and Pipecat as references for streaming, turn-taking, and
   cancellation. First prove a specific unmet requirement with the existing
   pipeline; then make a small, reversible integration spike and compare it
   against the trace baseline. No framework or full companion replacement is
   approved by this plan.

**Order/gate:** finish step 2 first, then choose either step 3 or step 4 based
on measured user pain; do not run both experiments or change production
defaults in the same iteration. Step 5 requires evidence that Rocky's current
architecture cannot meet a measured requirement.

## App review and issue plan (2026-10-24)

This is a source review plus the current self-test, not a claim that every
hardware path has passed. `make lint`, `git diff --check`, and
`./venv/bin/python rocky_desktop_app.py --selftest` passed. The self-test
reported local Ollama reachable and a synthetic vision answer; microphone,
webcam, live wake/sleep/watch behavior, long-running stability, and speaker
self-echo are not thereby verified.

### Confirmed implementation issues

1. **Hosted brain options do not work as advertised — fix before relying on
   them.** The OpenAI-compatible chat and vision requests send the literal
   `******` instead of the configured API key. The Anthropic text request falls
   through to Ollama's `/api/chat` path without Anthropic headers, although its
   vision request has a separate Anthropic implementation. The local Ollama
   default is unaffected. Either repair each supported provider with request
   construction tests, or remove/disable provider options that are not
   implemented; do not send any real credentials during a test.
2. **Drama 3 failure does not fall back to Kokoro or macOS speech.** The
   current synthesis path raises an error when the Drama 3 worker, model,
   reference, or FFmpeg fails; Kokoro and macOS `say` are selectable engines,
   not automatic recovery paths. Add explicit fallback policy and tests, or
   correct all user-facing claims to describe manual engine selection.
3. **`--selftest` can give a green exit despite Ollama being unavailable.** It
   prints the reachability result but does not include it in the final exit
   status; synthetic-only checks can therefore pass while the configured
   brain/vision integration is down. Separate offline unit checks from an
   explicit integration test and make each result and exit code unambiguous.

### Risks and unverified behavior

- **Camera-image retention:** an explicit look writes `logs/last_look.jpg`.
  This is local and used for debugging, but remains on disk after the request.
  Make retention opt-in or time-bounded and document how to remove it; never
  include frames in diagnostic traces.
- **Voice responsiveness and resource use:** Drama 3 is the default and can
  incur a cold model load with substantial memory use. The worker gathers
  generated audio chunks before returning a WAV, so playback is not yet
  streaming from the first generated chunk. Measure cold/warm first-audio
  latency and peak memory on the target Mac before promising the sub-800 ms
  goal.
- **Device and lifecycle behavior:** existing automated checks use synthetic
  audio and camera frames. Confirm real permissions, device disconnect/reopen,
  graceful app shutdown, cancellation latency, and that watch mode closes the
  camera promptly and visibly.
- **Listening quality:** the endpointer uses loudness thresholds and currently
  pauses the microphone during playback. Validate quiet speech, room noise,
  false wakes, long pauses, and speaker echo in person; preserve push-to-talk
  as a reliable fallback.
- **Observability:** stage-by-stage latency, failure counts, and a 20-turn
  baseline are still missing. Add privacy-safe local turn traces before
  selecting VAD/wake-word changes; no raw audio, images, or transcript text in
  traces by default.

### Prioritized sequence and exit gates

1. **P1 — Correct advertised behavior:** test provider request URLs, headers,
   and streaming parsers with fake local HTTP servers; cover each advertised
   provider or stop advertising unsupported modes. Define and test the local
   voice fallback behavior. Do not use real API keys in tests.
2. **P1 — Make health results trustworthy:** distinguish offline self-tests
   from Ollama/model integration checks; ensure each reports clear pass,
   fail, and skipped states with meaningful process exit codes.
3. **P1 — Establish privacy-safe evidence:** add stage events/durations and
   bounded log retention, excluding content and captures. Make saved look
   images opt-in or automatically expire.
4. **P2 — Run the real-Mac acceptance pass:** exercise hands-free wake,
   response, one-shot vision, opt-in tracking, stop tracking, sleep,
   push-to-talk, and long-answer speaker echo. Record outcomes/errors in
   `HANDOFF.md`; distinguish failures from items not yet tested.
5. **P2 — Soak and performance gate:** run a 30-minute session plus at least
   20 turns. Record cold/warm stage latency, memory, device restarts,
   cancellation, and errors. Only then select one endpoint or wake-word
   experiment; retain the current working path as fallback.

Do not bundle unrelated dependency upgrades, voice-model replacement, or an
assistant/framework rewrite into these fixes. Re-run focused tests,
`make lint`, and `git diff --check` after implementation, then repeat the
hardware checks affected by each change.

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
- [x] Audition Drama 3 delivery styles and select a breathier British voice.
- [x] Set up local Drama 3 as the default with Kokoro fallback.
- [ ] Measure warm Drama 3 synthesis and first-audio latency across turns.

**Exit:** local pipeline baseline measured; Drama 3 default and Kokoro fallback
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

- [ ] Benchmark Drama 3 warm synthesis and memory use alongside Ollama.
- [ ] Improve first-audio latency for the selected British Drama 3 voice.
- [ ] Retain and verify Kokoro as the local fallback.
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
