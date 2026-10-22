# Rocky — agent handoff

> **Start here if you are picking up this project.** This file is the current
> state, the goal, and the phased plan. The historical build handoff is
> [`docs/HANDOFF-2026-10-21.md`](docs/HANDOFF-2026-10-21.md); it is preserved for
> context only. Measured numbers in [`docs/LATENCY.md`](docs/LATENCY.md) are the
> source of truth.

Last updated: 2026-10-22
Repository: <https://github.com/dgooding/rocky>
Branch: `main`

---

## 1. Mission

Make Rocky a convincing **real-time** desk companion:

- local voice clone (Rocky)
- local brain (Ollama)
- local vision (camera)
- animated eyes and emotions
- local-first and privacy-preserving
- speech-end → first audio **under 800 ms**, with barge-in

The current app is a working turn-based prototype. The next job is the real-time
redesign, not another model swap.

---

## 2. Current state

### Working

- Mic push-to-talk → faster-whisper transcription (~0.4 s after release)
- Ollama brain streaming (`qwen3-coder:latest`, `num_ctx=8192`)
- Sentence/clause splitting and TTS prefetch
- XTTS v2 voice clone via persistent server on `127.0.0.1:59720`
- pygame UI, subtitles, typed input, 7 emotion presets
- Webcam snapshot → `qwen2.5vl:3b` vision
- macOS `.app` bundle with camera/microphone usage strings
- `--selftest` for eyes, STT, brain, vision, and UI
- Public repo with docs, screenshots, setup, restore scripts, issue templates

### Missing / known weak points

- **No barge-in** — listening and speaking are mutually exclusive
- **No AEC** — cannot safely keep the mic open during playback
- **No streaming playback** — `pygame.mixer` plays a complete WAV
- **No continuous vision** — camera opens only for one snapshot
- **XTTS is too slow** — measured **2.4–3.8 s per clause**
- **`inference_stream` is broken** with `transformers==4.44.0` / `torch==2.5.1`
- **No wake word** — F1 hold / F2 toggle only
- **CI workflow not pushed** — token lacked `workflow` scope; exact YAML is in
  [`docs/CI.md`](docs/CI.md)

### Measured baseline

| Stage | Measured |
|---|---:|
| XTTS per clause | 2.4–3.8 s |
| End-to-end first sound | ~3–5 s |
| Brain first token (warm) | 0.07–0.15 s |
| faster-whisper | ~0.4 s |
| Vision warm | ~0.4 s; ~6 s after model swap |

The brain is not the bottleneck. The voice path is.

---

## 3. Hard constraints

1. **License:** CC BY-NC 4.0. Non-commercial only.
2. **Voice IP:** Rocky's voice is the *Project Hail Mary* film production's IP.
   Personal, non-commercial use only.
3. **Do not commit voice assets:** `assets/*.wav`, `assets/*.pth`, `*.mp3`.
   Use [`scripts/restore_assets.sh`](scripts/restore_assets.sh) with a private
   backup.
4. **Keep the local path working** without API keys. Cloud is an enhancement.
5. **macOS camera/mic only work through `Rocky.app`.** The launcher must not use
   `exec`.
6. **Keep `numpy==1.26.4` and `opencv-python-headless==4.11.0.86`.** Newer
   OpenCV can upgrade numpy to 2.x and break XTTS.
7. **No telemetry, no hidden camera capture, no secrets in the repo.**

---

## 4. Where things are

| Path | What |
|---|---|
| [`README.md`](README.md) | Short overview and quick start |
| [`PROJECT.md`](PROJECT.md) | Full handbook: architecture, config, performance, FAQ |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Current process/thread model and seams |
| [`docs/REALTIME_PLAN.md`](docs/REALTIME_PLAN.md) | Target design and engine options |
| [`docs/LATENCY.md`](docs/LATENCY.md) | Measured numbers and reproduction |
| [`docs/RESEARCH.md`](docs/RESEARCH.md) | Verified vendor claims and caveats |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phased checklist |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Camera, audio, Ollama, bundle fixes |
| [`rocky_desktop_app.py`](rocky_desktop_app.py) | App: mic, STT, brain, vision, TTS, UI |
| [`rocky_eyes.py`](rocky_eyes.py) | Emotion presets and renderer |
| [`rocky_say.py`](rocky_say.py) | Voice script + persistent XTTS server |
| [`scripts/make_app.sh`](scripts/make_app.sh) | Build the `.app` bundle |
| [`scripts/restore_assets.sh`](scripts/restore_assets.sh) | Restore private assets |

Read order for a new agent:

1. this file
2. `docs/LATENCY.md`
3. `docs/REALTIME_PLAN.md`
4. `docs/ARCHITECTURE.md`
5. `docs/ROADMAP.md`
6. `docs/RESEARCH.md`

---

## 5. Phases

### Phase 0 — Instrument and decide (0.5–1 day)

**Goal:** stop guessing; choose the primary real-time engine.

Tasks:

- [ ] **First:** complete the reuse-first app bake-off in
  [`docs/OPEN_SOURCE_OPTIONS.md`](docs/OPEN_SOURCE_OPTIONS.md). Evaluate
  py-xiaozhi as the editable app, Xiaozhi Desktop as a UX-only comparison, and
  Open WebUI as the local-Ollama voice benchmark. Do not build a new audio core
  until this fit check is complete. The py-xiaozhi trial is scripted:
  `./scripts/xiaozhi_trial.sh setup|server|client|doctor`; see
  [`docs/XIAOZHI_TRIAL.md`](docs/XIAOZHI_TRIAL.md).
- [ ] Verify target Mac support, offline/local Ollama behavior, AEC/barge-in,
  current Rocky voice/eyes integration, camera privacy, and source/license
  terms for any candidate.
- [ ] Add timestamps: speech-end, STT-final, LLM-first-token, TTS-first-byte,
  first-audio-played, barge-in-stop.
- [ ] Write one JSONL trace per turn; compute p50/p95 over 20 turns.
- [ ] Keep `qwen3-coder` and `qwen2.5vl` resident; verify with
  `curl -s http://127.0.0.1:11434/api/ps`.
- [ ] Re-run the XTTS baseline using `docs/LATENCY.md`.
- [ ] Confirm voice-clone consent and a monthly cloud budget cap.
- [ ] Run a one-day A/B:
  - OpenAI Realtime (`gpt-realtime`, custom voice, semantic VAD)
  - Pipecat cascade: Deepgram Nova-3 or Cartesia Ink 2 → local `qwen3-coder`
    → Cartesia Sonic 3.6 or ElevenLabs Flash v2.5

Run the provider A/B only after the app reuse gate says that no ready-made
candidate meets the required platform/privacy/UX constraints.

**Exit:** measured baseline; primary engine chosen; fallback chosen.

**Files likely touched:** `rocky_desktop_app.py`, new `rocky_metrics.py`,
`docs/LATENCY.md`.

---

### Phase 1 — Real-time audio core (2–3 days)

**Goal:** continuous audio, natural endpointing, interruption, no self-hearing.

Tasks:

- [ ] Continuous 16 kHz mono capture with 20 ms frames.
- [ ] Silero VAD + Smart Turn v3 or provider endpointing (200–300 ms).
- [ ] Replace `pygame.mixer` with `sounddevice.RawOutputStream` or PyAudio and a
  PCM ring buffer.
- [ ] Cancelable TTS/LLM tasks; flush the ring buffer on interrupt.
- [ ] Barge-in state machine: `LISTENING → THINKING → SPEAKING → INTERRUPTED`.
- [ ] macOS AEC via `AVAudioEngine.inputNode.setVoiceProcessingEnabled(true)`
  (Swift helper or PyObjC); headphones as the temporary fallback.
- [ ] Pre-generate 5–10 backchannels in Rocky's voice ("Mm", "Yes", "Okay").
- [ ] Keep eyes/amplitude in sync from the same PCM chunks.

**Exit:** p95 speech-end → first audio <800 ms; barge-in stop <150 ms; no
self-hearing with speakers at normal volume.

**Files likely touched:** `rocky_desktop_app.py`, new `rocky_audio.py`,
`rocky_eyes.py`, `scripts/make_app.sh` (if a Swift helper is bundled).

---

### Phase 2 — Voice engine (2–3 days)

**Goal:** make the chosen engine the primary voice, with a fallback.

Tasks:

- [ ] Define a `RealtimeSession` interface: audio in/out, cancel, events.
- [ ] Implement the primary engine (OpenAI Realtime or Pipecat cascade).
- [ ] Implement the fallback engine.
- [ ] Tune first-clause length and TTS continuations.
- [ ] Blind similarity test against the XTTS reference (10–20 phrases).
- [ ] Measure cost per 100 turns.
- [ ] Add a voice-consent note to the UI/docs.

**Exit:** primary voice accepted; fallback works; cost understood.

**Files likely touched:** new `rocky_realtime.py`, `rocky_desktop_app.py`,
`requirements.txt`, `docs/REALTIME_PLAN.md`.

---

### Phase 3 — Vision (2–3 days)

**Goal:** continuous awareness without melting the machine.

Tasks:

- [ ] Background camera capture at 640×480/30 FPS; keep the latest frame.
- [ ] MediaPipe Face/Hands/Pose or YOLOv8n/YOLO11n at 5–10 FPS.
- [ ] Scene-change gating (frame diff or perceptual hash).
- [ ] On-demand VLM: local Moondream/SmolVLM2/qwen2.5vl, or the realtime
  session's image input.
- [ ] Visible camera indicator, explicit look mode, privacy toggle.
- [ ] Keep `logs/last_look.jpg` for debugging.

**Exit:** "what am I holding?" <1.5 s; "did the user leave?" <1 s; no VLM at
30 FPS.

**Files likely touched:** new `rocky_vision.py`, `rocky_desktop_app.py`,
`rocky_eyes.py`.

---

### Phase 4 — Real-world hardening (3–5 days)

**Goal:** survive a real room, a real network, and a long session.

Tasks:

- [ ] Wake word (`openWakeWord`) or a clear push-to-talk mode.
- [ ] Short conversation memory.
- [ ] Offline/local fallback when cloud is unavailable.
- [ ] Cost caps, per-turn limits, kill switch.
- [ ] 30-minute soak; device hot-plug; sleep/wake.
- [ ] Log rotation; local-only crash reporting.
- [ ] Packaging/signing; rebuild instructions.
- [ ] 50-turn scripted conversation in a noisy room.

**Exit:** 50 turns without stuck state or duplicate replies; stable memory;
fallback works.

---

## 6. Recommended first action

Do **Phase 0** before writing the real-time core:

1. Add latency marks and a JSONL trace.
2. Measure 20 turns on the current app.
3. Run the OpenAI Realtime vs Cartesia/ElevenLabs bake-off.
4. Commit the measurements and the engine decision to this file.

Do not start by rewriting the UI or swapping the brain. The bottleneck is the
audio path.

---

## 7. Decision points

| Decision | Options | Default recommendation |
|---|---|---|
| Cloud or local-first? | cloud latency vs privacy | Local by default; cloud as opt-in |
| Primary engine | OpenAI Realtime vs Pipecat cascade | Run both for one day; pick on p95 + voice quality |
| Voice | OpenAI custom voice vs Cartesia/ElevenLabs clone | Cascade if Rocky's voice matters most |
| Listening mode | always-on vs wake word vs push-to-talk | Wake word + push-to-talk; always-on only with AEC |
| Vision | local VLM vs realtime session | Cheap local detector + on-demand VLM |
| Budget | per-minute cloud audio | Set a hard monthly cap before Phase 2 |

---

## 8. Verification

```sh
# Environment
./venv/bin/python --version
./venv/bin/pip show numpy opencv-python-headless TTS transformers torch
ollama list

# Compile
python3.11 -m compileall -q rocky_desktop_app.py rocky_eyes.py rocky_say.py app.py

# Eyes
./venv/bin/python rocky_eyes.py --selftest shots/eyes

# App pipeline (synthetic vision, no camera)
./venv/bin/python rocky_desktop_app.py --selftest

# Voice server
curl -s http://127.0.0.1:59720/health

# Camera through the bundle
./scripts/make_app.sh
open -n ./Rocky.app --args --snap /tmp/cam.jpg
ls -lh /tmp/cam.jpg

# No restricted assets tracked
git ls-files assets
# expected: assets/README.md
```

Acceptance for the redesign:

- p95 speech-end → first audio <800 ms (cascade) / <700 ms (S2S)
- barge-in stop <150 ms
- no self-hearing at normal speaker volume
- 50 turns without a stuck state or duplicate reply
- camera answer <1.5 s
- 30-minute soak with stable memory
- offline fallback still responds
- no camera frame leaves the machine unless cloud vision is explicitly enabled

---

## 9. Known blockers and gotchas

- **CI workflow:** the publishing token lacked `workflow` scope. The YAML is in
  [`docs/CI.md`](docs/CI.md). Add it via the web UI or refresh with
  `gh auth refresh -h github.com -s workflow`.
- **`inference_stream`:** raises `TypeError: isin()` with the pinned stack. Do
  not switch to it without re-pinning/patching and re-benchmarking.
- **Camera permission:** only the `.app` bundle works. The launcher must not use
  `exec`.
- **numpy:** must stay `<2`; current OpenCV wheels can silently upgrade it.
- **XTTS server:** single-threaded; concurrent callers queue.
- **Ollama model swaps:** ~6 s. Keep models warm or use one multimodal session.
- **Vision streaming:** local vision requests are intentionally non-streamed
  (small models drop the first character).
- **Voice assets:** never commit or redistribute them.

---

## 10. Definition of done

Rocky is "done" for this phase when:

- A new user can clone the repo, restore assets, run `./setup.sh`, pull models,
  start the voice server, and launch the app from the README.
- The app starts speaking in under 800 ms p95 after the user stops talking.
- The user can interrupt mid-sentence and Rocky stops immediately.
- The camera is useful without a 6 s model swap and without a VLM on every
  frame.
- The local path works without any API key.
- All docs and measurements match the code.
- No restricted voice assets are in the repository.
