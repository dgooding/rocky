# Rocky — agent handoff

> **Start here if you are picking up this project.** This file is the current
> state, the goal, and the phased plan. The historical build handoff is
> [`docs/HANDOFF-2026-10-21.md`](docs/HANDOFF-2026-10-21.md); it is preserved for
> context only. Measured numbers in [`docs/LATENCY.md`](docs/LATENCY.md) are the
> source of truth.

Last updated: 2026-10-23
Repository: <https://github.com/dgooding/rocky>
Branch: `main`

---

## 1. Mission

Make Rocky a convincing **real-time** local desktop assistant with animated
eyes inspired by Casey Grothaus's
[desk robot](https://github.com/cgro00/desk-robot). The owner chose a natural,
conversational assistant personality and local British-English speech instead
of roleplaying the fictional character or using its cloned voice.
Earlier voice-engine plans in this handoff are historical; hosted speech or
voice-clone work requires a new explicit owner decision.

- local British-English TTS (Drama 3 by default; Kokoro fallback)
- local brain (Ollama)
- two senses in this app: **hearing** (hands-free voice recognition) and
  **sight** (webcam)
- animated eyes and emotions
- local-first and privacy-preserving
- speech-end → first audio **under 800 ms**, with barge-in

**Scope decision (2026-10-22, owner):** build on this app only. Outside apps
were surveyed ([`docs/OPEN_SOURCE_OPTIONS.md`](docs/OPEN_SOURCE_OPTIONS.md)) and
are not being adopted. Large files are never committed; `scripts/fetch_assets.sh`
downloads them.

---

## 2. Current state

### Working

- Hearing: hands-free listening (20 ms frames, adaptive energy endpointing),
  "hey Rocky" wake, awake 60 s after each exchange, "Rocky, sleep"; mic paused
  while he thinks or speaks; push-to-talk still available
- faster-whisper transcription (~0.4 s after you stop talking)
- Ollama brain streaming (`qwen3-coder:latest`, `num_ctx=8192`)
- Sentence/clause splitting and TTS prefetch
- Drama 3 local British female voice reference with 1.15x pitch-preserving
  tempo and no inserted breathing effects; Kokoro and macOS `say` are local
  fallbacks
- pygame UI, subtitles, typed input, 7 emotion presets, doze when ignored
- Sight: "what do you see?" / "what am I holding?" / "look left" / F3 →
  `qwen2.5vl:3b`; opt-in watch mode ("track me", F5) with local face detection
  so his eyes follow you
- macOS `.app` bundle with camera/microphone usage strings
- Self-diagnosis: `--diagnose` or F6 checks local setup and services; F7/F8
  perform user-triggered, unsaved microphone/camera checks; spoken diagnosis
  and bounded local brain/voice recovery are also available (F9)
- `--selftest` for eyes, STT, brain, vision, UI, and the hearing/sight logic
- `scripts/fetch_assets.sh` downloads voice files and models for a fresh clone
- Public repo with docs, screenshots, setup, restore scripts, issue templates

### Not yet verified on a Mac

The hearing and sight changes were tested with synthetic audio, fake camera
frames, and a fake brain (22 checks), not with a real microphone, webcam, or
Ollama. Run the checks in `AGENTS.md` first.

**Verification update (2026-10-23):** `./setup.sh` completed and
`rocky_desktop_app.py --selftest` passed with local Ollama. Output included
`hearing endpointer`, `configurable endpoint pause`, `hearing ignores a click`,
`sight look-intent`, `hearing commands (wake/sleep/track)`, `response
cancellation`, `PCM playback chunks`, `sight face detector`, and a synthetic
vision result ("The main object is a red square."). No STT probe WAV was
present. A coordinated 8 s microphone capture was transcribed locally by
faster-whisper as "Hey Rocky, testing the microphone. Frienda. Hello friend."
The requested phrase was recognized, with extra trailing words; this confirms
mic capture and local STT but not hands-free wake/response behavior. A brief
low-level tone and then a moderate-level tone completed through the new
`sounddevice.OutputStream` path on the MacBook Pro Speakers without an
audio-device error; the user confirmed the moderate tone was clearly audible.
**User app test (2026-10-23):** Rocky launched from the current checkout and
the user exercised a live voice interaction, then closed the app. Replies were
reported as too verbose; the user tried to interrupt by speaking over
playback. This is not supported: Rocky pauses microphone listening while he
speaks, and F1 is the current manual interrupt. The default system prompt was
initially tightened to request one or two short sentences. Follow-up smoke test passed:
the app self-test and local Ollama replies (9 and 21 words for two sample
queries). In a subsequent primary-screen test, the log captured "Hey, what's
up?", "What's up? What's up?", "What time is it?", and "Can you give yourself
that access?"; the screenshot showed Rocky awake with a response displayed.
This confirms the F1/push-to-talk transcription and response path worked in
that attempt. The user has not reported whether F1 stopped ongoing speech
promptly, so stop latency remains unmeasured. After the concise prompt update,
the user said Rocky still shortened answers and sounded flat/monotone; test
logs show requests for detailed India and Iceland/geothermal explanations.
The earlier 45-token output cap was limiting detail, so generation now uses a
48-token cap for ordinary questions and 220 for explicit detail/continuation
requests. Local smoke tests returned 15 words for "What time is it?" and 95
words for "Tell me everything you know about India." Kokoro synthesized
long-form samples; voice expressiveness remains a separate, unresolved issue.
One Kokoro request logged `'NoneType' object has no attribute 'peek'`; the
same sample texts synthesized successfully in a later direct check, so
intermittent synthesis reliability needs monitoring. Webcam permissions/vision,
the full wake/sleep/watch sequence, and the speaker self-echo check remain
unverified.

**Fish Audio Drama 3 update (2026-10-23):** the official Fish Audio runtime
still requires an NVIDIA GPU and does not support Apple MPS, but an unofficial
Apple-Silicon conversion is available through `mlx-audio`. Downloaded
`mlx-community/fish-audio-drama-3-4bit` (22 GiB) at revision
`1ac1b2108b63c2ef5bade463a121569363e293ce` and tested it on the M1 Max in an
isolated Python 3.11 environment at `~/.cache/rocky/mlx-audio-venv`.

Local test results: model load 5.51 s; with a 256-frame output cap, the first
streamed audio arrived in 0.82 s and 7.34 s of speech took 5.82 s to generate
(1.26x real-time), with 25.19 GB peak MLX memory. A separate uncapped first
sample took 3.73 s to first audio and ran at 0.84x real-time. Repeated
no-reference generations sometimes ran on for 31-48 seconds and omitted the
end of the requested line in local Whisper transcription; the bounded sample
transcribed as requested. Drama 3 therefore needs more auditioning, and a
voice reference the owner has permission to use is important for a stable
speaker and accent. The sample was played locally after the Kokoro comparison;
the owner has not yet provided voice-quality feedback. Temporary WAVs are
`/tmp/rocky-kokoro-audition.wav` and `/tmp/rocky-drama3-bounded.wav`.

**Five-style audition (2026-10-23):** generated and replayed five local samples
on the M1 Max, with no voice reference: calm, bright, thoughtful, reassuring,
and playful. The first four used the same greeting for a delivery comparison;
the fifth used the shorter line “That sounds like a fun idea.” All five passed
a local faster-whisper intelligibility check. The four same-text samples took
6.03–6.74 s to generate 7.99–9.47 s of audio (1.28–1.40x real-time), with
0.33–0.87 s to first audio and about 25.2 GB peak MLX memory. Samples are
`/tmp/rocky-drama3-01-calm.wav` through `/tmp/rocky-drama3-05-playful.wav`.
Ollama's Qwen3 and vision models were unloaded during generation and restored
afterward.

**Faster voice audition (2026-10-23):** created pitch-preserving 1.15x tempo
copies of the calm, bright, and playful samples. Their durations are 6.96 s,
7.88 s, and 1.90 s, respectively. All three passed a local faster-whisper
transcription check and were played. Original samples remain unchanged; faster
copies are `/tmp/rocky-drama3-01-calm-faster.wav`,
`/tmp/rocky-drama3-02-bright-faster.wav`, and
`/tmp/rocky-drama3-05-playful-faster.wav`.

**British breathy voice audition (2026-10-23):** conditioned Drama 3 on a
locally generated Kokoro `bf_emma` British female voice reference, with soft
breath cues, keeping the calm delivery from sample 1. Generated a 1.15x
pitch-preserving copy to match the previously liked pace. The 10.35 s sample
passed local transcription and was played. Files:
`/tmp/rocky-drama3-01-calm-british-breathy.wav` and
`/tmp/rocky-drama3-01-calm-british-breathy-faster.wav`. This audition used a
generic synthesized reference voice; it did not use a real person's recording.
The owner strongly preferred this sample over the prior auditions ("1 billion
percent better"). Treat a breathier, feminine British voice based on this
local Kokoro reference as the preferred direction for further TTS evaluation.

**Default voice switch (2026-10-23):** the owner approved the breathier
British Drama 3 voice as Rocky's default. Added an isolated persistent MLX
worker, a local setup script, and Kokoro/macOS fallbacks. The app uses the
same generic Kokoro `bf_emma` reference as the favored audition, with
1.15x pitch-preserving tempo adjustment. Initially, literal breath cues were
also added to replies; those were removed after in-app feedback. The model stays outside the
repository in `~/.cache/huggingface`; the worker environment and generated
reference stay in `~/.cache/rocky`. The app's pinned requirements are unchanged.
An initial no-breath-cue smoke test produced a 5.78 s 44.1 kHz WAV and
transcribed fully; the first model load took 17.08 s with Ollama unloaded.
Follow-up testing found the generated reference was only 24 kHz, making the
breath-cued output too quiet. `scripts/setup_drama3.sh` now resamples the
reference to 44.1 kHz. After rerunning setup, `ffprobe` confirmed 44.1 kHz and
the default `synthesize()` path produced a 10.34 s WAV at -27.0 dB mean and
-8.1 dB peak. Local Whisper recognized the main reply but omitted its trailing
"No rush."; the sample played locally. Actual live use inside the Rocky window
remains to be tested. The latest sample is
`/tmp/rocky-default-drama3-british-breathy.wav`.
Subsequent worker calls reuse the loaded model. Setup instructions are in
`scripts/setup_drama3.sh`.

**Voice feedback (2026-10-23):** after trying Rocky in the app, the owner
clarified that "breathy" means a naturally breathy vocal tone, not literal
breathing sounds at random times. The app no longer inserts inhale or breath
cues; it retains the British reference voice and 1.15x pace. Restart Rocky to
load the change and confirm its delivery.

The owner confirms Rocky is for personal use and education, not commercial
deployment. The checkpoint is an unofficial MLX conversion under the Fish
Audio Community License. No text or audio was sent to Fish Audio. The app's
pinned dependencies remain unchanged; Kokoro `bf_emma` is the local fallback.

**Voice update (2026-10-23):** after rejecting the robotic sound of installed
macOS voices, the owner selected a local open-source British TTS. The app now
defaults to a generic British Drama 3 voice and a natural, non-character
assistant prompt.
Kokoro generated a valid 24 kHz WAV and played through the app's PCM path; the
owner said it was closer. It is not claimed to match ElevenLabs. Kokoro weights
are Apache-licensed; model card grades voice data quality subjectively and
warns short utterances can be weaker. A local smoke timing took 3.41 s for the
first phrase in a process and 0.30 s for the next phrase; this is not a
statistically meaningful benchmark.

### Missing / known weak points

- **No automatic voice barge-in** — F1 can stop playback and start push-to-talk;
  hands-free interruption still waits for echo cancellation
- **No AEC** — so hands-free listening pauses while he speaks
- **TTS is not streamed** — Drama 3 synthesizes the clause before the app plays
  its 20 ms PCM blocks
- **Drama 3 has a cold first-use delay** — first app synthesis including model
  load took ~17 s in a test with Ollama unloaded; warm multi-turn latency needs
  a separate benchmark
- Legacy XTTS measurements remain in `docs/LATENCY.md`; XTTS is not the app's
  active voice path
- **`inference_stream` is broken** with `transformers==4.44.0` / `torch==2.5.1`
- **Endpointing is energy-based** — the quiet pause is configurable (200–2000
  ms, 700 ms default); Silero VAD + Smart Turn remains the natural next upgrade
- **CI workflow not pushed** — token lacked `workflow` scope; exact YAML is in
  [`docs/CI.md`](docs/CI.md)

### Measured baseline

| Stage | Measured |
|---|---:|
| Kokoro first phrase in process | 3.41 s (single smoke check) |
| Kokoro next phrase in same process | 0.30 s (single smoke check) |
| Drama 3 first app synthesis | 17.08 s including worker/model load (Ollama unloaded) |
| Drama 3 synthesis peak memory | 26.50 GiB (reference-conditioned sample) |
| Legacy XTTS per clause | 2.4–3.8 s |
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

**Goal:** measure the local pipeline and improve its real-time behavior.

Tasks:

- [x] **Decided (2026-10-22):** build on Rocky's own app; do not adopt an
  outside app. The survey is kept in
  [`docs/OPEN_SOURCE_OPTIONS.md`](docs/OPEN_SOURCE_OPTIONS.md) for reference.
- [ ] Verify hearing and sight on the Mac (see `AGENTS.md`).
- [ ] Add timestamps: speech-end, STT-final, LLM-first-token, TTS-first-byte,
  first-audio-played, barge-in-stop.
- [ ] Write one JSONL trace per turn; compute p50/p95 over 20 turns.
- [ ] Keep `qwen3-coder` and `qwen2.5vl` resident; verify with
  `curl -s http://127.0.0.1:11434/api/ps`.
- [ ] Benchmark warm synthesis for local Drama 3 while Ollama is resident.
- [x] Compare local British voice auditions; owner selected the breathier
  reference-conditioned Drama 3 voice.

Run voice checks locally; do not route voice or other data to a cloud service
without explicit user opt-in.

**Exit:** local pipeline baseline measured; Drama 3 default and Kokoro fallback
characterized.

**Files likely touched:** `rocky_desktop_app.py`, new `rocky_metrics.py`,
`docs/LATENCY.md`.

---

### Phase 1 — Real-time audio core (2–3 days)

**Goal:** continuous audio, natural endpointing, interruption, no self-hearing.

Tasks:

- [x] Continuous 16 kHz mono capture with 20 ms frames (`Ears`, hands-free).
- [ ] Silero VAD + Smart Turn v3 or provider endpointing (200–300 ms). Today:
  adaptive energy endpointing with a configurable pause (`Endpointer`,
  `--end-silence-ms`, default 700).
- [ ] Keep one persistent PCM output stream and add a bounded ring buffer;
  current `sounddevice.OutputStream` streams 20 ms blocks per synthesized clip.
- [ ] Cancelable TTS/LLM tasks; flush the ring buffer on interrupt.
- [ ] Barge-in state machine: `LISTENING → THINKING → SPEAKING → INTERRUPTED`.
- [ ] macOS AEC via `AVAudioEngine.inputNode.setVoiceProcessingEnabled(true)`
  (Swift helper or PyObjC); headphones as the temporary fallback.
- [ ] Pre-generate 5–10 neutral assistant backchannels locally.
- [ ] Keep eyes/amplitude in sync from the same PCM chunks.

**Exit:** p95 speech-end → first audio <800 ms; barge-in stop <150 ms; no
self-hearing with speakers at normal volume.

**Files likely touched:** `rocky_desktop_app.py`, new `rocky_audio.py`,
`rocky_eyes.py`, `scripts/make_app.sh` (if a Swift helper is bundled).

---

### Phase 2 — Voice engine (2–3 days)

**Goal:** improve local Drama 3 responsiveness and retain a local fallback.

Tasks:

- [ ] Benchmark warm Drama 3 synthesis and memory use alongside Ollama.
- [ ] Keep the macOS system voice available as a local fallback.
- [ ] Tune first-clause length and TTS continuations.

**Exit:** local voice is accepted; fallback works; warm latency is measured.

**Files likely touched:** new `rocky_realtime.py`, `rocky_desktop_app.py`,
`requirements.txt`, `docs/REALTIME_PLAN.md`.

---

### Phase 3 — Vision (2–3 days)

**Goal:** continuous awareness without melting the machine.

Tasks:

- [x] Background camera capture; keep the latest frame (`Watcher`, opt-in).
- [x] Cheap local detector: OpenCV Haar face cascade at 4 fps; eyes follow the
  face; arrive/leave events. MediaPipe/YOLO remain options for hands/objects.
- [ ] Scene-change gating (frame diff or perceptual hash).
- [x] On-demand VLM from speech ("what am I holding?") via `qwen2.5vl:3b`.
- [x] Visible camera indicator ("watching"), explicit look mode, privacy toggle (F5).
- [x] Keep `logs/last_look.jpg` for debugging.

**Exit:** "what am I holding?" <1.5 s; "did the user leave?" <1 s; no VLM at
30 FPS.

**Files likely touched:** new `rocky_vision.py`, `rocky_desktop_app.py`,
`rocky_eyes.py`.

---

### Phase 4 — Real-world hardening (3–5 days)

**Goal:** survive a real room, a real network, and a long session.

Tasks:

- [x] Wake phrase ("hey Rocky", from the transcript) plus push-to-talk.
  `openWakeWord` would avoid transcribing room talk while he is asleep.
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

1. **Verify hearing and sight on the Mac** (`AGENTS.md`): `--selftest`, then a
   real "hey Rocky" conversation, a look, and watch mode.
2. Then **Phase 0**: add latency marks and a JSONL trace, measure 20 turns,
   run the OpenAI Realtime vs Cartesia/ElevenLabs bake-off, and commit the
   measurements and engine decision to this file.

Do not start by rewriting the UI or swapping the brain. The bottleneck is the
audio path.

---

## 7. Decision points

| Decision | Options | Default recommendation |
|---|---|---|
| Cloud or local-first? | cloud latency vs privacy | Local by default; cloud as opt-in |
| Primary engine | local Drama 3 through MLX | **Chosen:** local-only by default; Kokoro fallback |
| Voice | Drama 3 with generic Kokoro British reference | **Chosen:** breathier feminine British voice; no cloned character voice |
| Listening mode | always-on vs wake word vs push-to-talk | **Chosen:** "hey Rocky" + push-to-talk; mic paused while he speaks until AEC exists |
| Vision | local VLM vs realtime session | **Chosen:** local face detector (opt-in) + on-demand VLM |
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
