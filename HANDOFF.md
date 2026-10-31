# Rocky — agent handoff

> **Start here if you are picking up this project.** This file is the current
> state, the goal, and the phased plan. The historical build handoff is
> [`docs/HANDOFF-2026-10-21.md`](docs/HANDOFF-2026-10-21.md); it is preserved for
> context only. Measured numbers in [`docs/LATENCY.md`](docs/LATENCY.md) are the
> source of truth.

Last updated: 2026-10-30
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

- local British-English TTS (Kokoro `bf_emma` by default)
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
- Kokoro local British voice (`bf_emma`), cached after first use; macOS `say`
  is an alternate local voice
- Modular brain architecture (`rocky_brain.py`): standalone `Brain`, prompts,
  sliding-window conversation history (bounded to 20 turns), detail-request
  token limits, and clause/sentence streaming
- Extensible Tool Registry (`tools.py`): real live web search via DuckDuckGo
  Lite (no API keys or external dependencies), system URL opening via native
  macOS `open`, and automatic tool call execution
- Dual tool-calling support: streams and intercepts `<tool_call>` tags while
  normalizing native Ollama / OpenAI `tool_calls` payload schemas into the
  conversation loop (capped at 3 tool turns to avoid runaway loops)
- 1600×900 JARVIS-style HUD (`rocky_hud.py`): arc-reactor core, transcript,
  system, senses and latency panels, live mic level, command bar, typed input.
  The eyes no longer appear in the window; `rocky_eyes.py` is kept because
  `make selftest` still uses `mood_for()` and `PRESETS`
- Sight: "what do you see?" / "what am I holding?" / "look left" / F3 →
  `qwen2.5vl:3b`; opt-in watch mode ("track me", F5) with local face detection
  so his eyes follow you
- macOS `.app` bundle with camera/microphone usage strings
- `--selftest` for eyes, STT, brain, vision, UI, and the hearing/sight logic
- `scripts/fetch_assets.sh` downloads voice files and models for a fresh clone
- Public repo with docs, screenshots, setup, restore scripts, issue templates

### Verification log

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

**Fish Audio Drama 3 research (2026-10-23):** the model is explicitly designed
for directed, expressive, long-form speech and supports natural-language
performance directions. However, the official installation requirements say
Drama 3 needs at least 48 GB NVIDIA GPU memory and supports neither CPU nor
Apple MPS; the H200 streaming figures are not representative of this M1 Max.
The official Fish Audio web/API path is hosted, so do not send Rocky's replies
to it unless the owner explicitly opts into that cloud service. Keep Kokoro
local as the active default; the Fish Audio website can be auditioned manually
with non-sensitive sample text if the owner wants to compare quality.

**Voice update (2026-10-23):** after rejecting the robotic sound of installed
macOS voices, the owner selected a local open-source British TTS. The app now
defaults to Kokoro `bf_emma` and a natural, non-character assistant prompt.
Kokoro generated a valid 24 kHz WAV and played through the app's PCM path; the
owner said it was closer. It is not claimed to match ElevenLabs. Kokoro weights
are Apache-licensed; model card grades voice data quality subjectively and
warns short utterances can be weaker. A local smoke timing took 3.41 s for the
first phrase in a process and 0.30 s for the next phrase; this is not a
statistically meaningful benchmark.

**Verification update (2026-10-27):** the working copy was stuck in a failed
`git rebase` with a committed 73 MB archive and unmerged `.gitignore`; it was
reset to `origin/main` and those files removed (backup bundle and the stale
branch are in `~/Documents/Rocky-backups/`, tag `archive/submodule-flatten-2026-10-23`).
On a fresh `venv` from `requirements.txt`, `--selftest` passed every check
(hearing endpointer, configurable endpoint pause, ignores a click, look-intent,
wake/sleep/track, response length, cancellation, PCM chunks, face detector) and
the synthetic vision probe answered in 6.1 s (cold model). Kokoro `bf_emma`
synthesized "What time is it?" in 0.25 s and a ten-word sentence in 0.40 s once
warm; the first call in a fresh venv took 11.2 s because Kokoro installs
`en_core_web_sm` and downloads its weights once. Real microphone, webcam, and
wake-word behaviour are still unverified by a person.

**HUD update (2026-10-30):** the 640×400 eyes panel was replaced by a
1600×900 JARVIS-style HUD (`rocky_hud.py`, spec in `docs/HUD.md`): arc-reactor
core, transcript / system / senses / latency panels, live mic level, 1 Hz
telemetry from the standard library, `--reduce-motion`. Commits `b995324`
(HUD), `3ebc72f` (ring radii scale with the core), `77809cc` (fixes below).
`rocky_eyes.py` is untouched. Launching the bundle on the Mac exposed two
rendering bugs, both fixed in `77809cc`: the new `render()` had lost the
`pygame.display.flip()` carried by the old renderer, so the window drew pure
black; and the cached chrome surface must carry `SRCALPHA` — blending the
translucent grid onto a surface without that flag zeroes the destination alpha,
which makes macOS composite the window as see-through. `make lint` is clean and
`--selftest` passed all ten checks. The window is 1600×900 (932 with the title
bar); here it opened on display 2 at (2648, 238), so a window capture is
`screencapture -R2648,266,1600,900`.

**Live app test (2026-10-30, HUD build):** the bundle was launched from
`Rocky.app`, rendered the HUD correctly, ran both sessions without a crash, and
was closed normally. The owner reports it working end to end. What the log
actually shows in `~/Library/Logs/Rocky.log`: `[you] wake up` in the 18:52 run
and `[you] how's it going` plus `[you] Not too shabby.` in the 19:02 run. So the
bundle's microphone and faster-whisper transcription work live, and none of
those phrases woke him — correct for room talk with no wake name. No `[rocky]`
reply, vision answer, or watch-mode transition was logged, and it is not
recorded whether "Not too shabby." was the owner or his own voice reaching the
microphone. The wake → answer, look, watch-mode, F1 and speaker-echo checks are
therefore user-reported, not log-verified; the ROADMAP checkbox stays unticked
until a session with logged replies and a vision use is captured.

**Tool execution, brain modularization & folder consolidation (2026-10-30):**
Code review uncovered that `Brain` in `rocky_desktop_app.py` was instantiating an
empty `ToolRegistry()` rather than attaching `default_registry`, while
`open_browser` used a brittle AppleScript that ignored the target URL.
Furthermore, tool interception in the streaming loop used an inner `continue`
that didn't exit the active delta stream to re-query the model with tool
results, while `import re` and `import json` were firing on every incoming
token.
- Connected `default_registry` to `Brain.tools` and upgraded `open_browser` to
  use native `open <url>`.
- Replaced the stub `search_web` with live web search via DuckDuckGo Lite,
  returning top snippets without API keys or external packages.
- Added native Ollama and OpenAI tool call streaming extraction in `_deltas()`
  alongside `<tool_call>` tag parsing.
- Fixed the continuation loop and conversation history: user prompt and tool
  results are stored in `self.history` with a bounded sliding window (system
  prompt + last 18 messages).
- Extracted LLM generation, prompts, token limits, and sentence streaming into
  `rocky_brain.py`, reducing `rocky_desktop_app.py` by >300 lines.
- Passed `venv/bin/python rocky_desktop_app.py --selftest` completely.
- Repositories consolidated: earlier unpushed local commit `cf3fadf` (Drama3
  worker / voice recovery) was pushed and backed up to GitHub branch
  `voice-recovery-drama3`. The duplicate folder `~/Documents/Rocky` was backed
  up to `~/Documents/Rocky-backup-20261030` and replaced with a symlink to
  `/Users/aiserver/rocky`, preventing future codebase drift.

### Missing / known weak points


- **No automatic voice barge-in** — F1 can stop playback and start push-to-talk;
  hands-free interruption still waits for echo cancellation
- **No AEC** — so hands-free listening pauses while he speaks
- **Kokoro's first call is slow once** — a fresh venv installs `en_core_web_sm`
  and downloads the 82M weights (~11 s); later calls are 0.25–0.40 s
- **TTS is not streamed** — Kokoro synthesizes the clause before the app plays
  its 20 ms PCM blocks
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
| Kokoro per clause (warm) | 0.25–0.40 s (2 checks, 2026-10-27) |
| Kokoro first call in a fresh venv | 11.2 s (one-time model + G2P install) |
| Legacy XTTS per clause | 2.4–3.8 s |
| End-to-end first sound | not measured with Kokoro; the parts add up to ~0.8 s warm |
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
| [`docs/HUD.md`](docs/HUD.md) | HUD spec: palette, type scale, layout rects, motion |
| [`rocky_hud.py`](rocky_hud.py) | HUD renderer: chrome cache, arc reactor, panels, glow |
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

## Not yet verified on a Mac

**Date:** Fri Oct 30 2026
**Self-test output (HUD build):**
- Ollama reachable: True
- Hearing:
  - `endpointer`: ok
  - `configurable endpoint pause`: ok
  - `ignores a click`: ok
  - `commands (wake/sleep/track)`: ok
- Brain: `response length`, `cancellation`: ok
- Playback: `PCM chunks`: ok
- Sight:
  - `look-intent`: ok
  - `face detector`: ok
  - Vision output: `'The main object is a red square.'`

The owner exercised the app on 2026-10-30 and reports it working (see the live
app test entry above); the log captures transcription but no replies or vision,
so treat the spoken checks as user-reported rather than log-verified.

## 5. Phases

### Phase 0 — Instrument and decide (0.5–1 day)

**Goal:** measure the local pipeline and improve its real-time behavior.

Tasks:

- [x] **Decided (2026-10-22):** build on Rocky's own app; do not adopt an
  outside app. The survey is kept in
  [`docs/OPEN_SOURCE_OPTIONS.md`](docs/OPEN_SOURCE_OPTIONS.md) for reference.
- [x] Verify hearing and sight on the Mac (see `AGENTS.md`).
- [ ] Add timestamps: speech-end, STT-final, LLM-first-token, TTS-first-byte,
  first-audio-played, barge-in-stop.
- [ ] Write one JSONL trace per turn; compute p50/p95 over 20 turns.
- [ ] Keep `qwen3-coder` and `qwen2.5vl` resident; verify with
  `curl -s http://127.0.0.1:11434/api/ps`.
- [ ] Benchmark warm synthesis for local Kokoro.
- [ ] Compare British Kokoro presets with the user.

Run voice checks locally; do not route voice or other data to a cloud service
without explicit user opt-in.

**Exit:** local pipeline baseline measured; Kokoro default and macOS fallback
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

**Goal:** improve local Kokoro responsiveness and retain a local fallback.

Tasks:

- [ ] Optimize and benchmark Kokoro synthesis for the default British preset.
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
   real "hey Rocky" conversation, a look, and watch mode. The self-test side is
   green as of 2026-10-30; only the person-in-front-of-the-Mac checks are open.
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
| Primary engine | local Kokoro, with local macOS fallback | **Chosen:** local-only by default |
| Voice | Kokoro British preset vs installed macOS voice | **Chosen:** Kokoro `bf_emma`; no cloned character voice |
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

# Legacy voice server (only the standalone rocky_say.py tool uses it)
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

- A new user can clone the repo, run `./setup.sh`, pull the Ollama models, and
  launch the app from the README (Kokoro needs no voice server or voice assets).
- The app starts speaking in under 800 ms p95 after the user stops talking.
- The user can interrupt mid-sentence and Rocky stops immediately.
- The camera is useful without a 6 s model swap and without a VLM on every
  frame.
- The local path works without any API key.
- All docs and measurements match the code.
- No restricted voice assets are in the repository.
