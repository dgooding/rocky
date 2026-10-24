# Rocky — agent instructions

Rocky is a local-first macOS desk companion with animated eyes inspired by
Casey Grothaus's [desk robot](https://github.com/cgro00/desk-robot)
([video](https://www.youtube.com/shorts/aHSusA0xXjU)). Hearing, sight, and
assistant personality are implemented in this app.
Start with [`HANDOFF.md`](HANDOFF.md) for state, constraints, and phases. When
in doubt about the interaction style, use a natural, concise assistant voice.

**Scope (owner decision):** work only on this app (`rocky_desktop_app.py` and
its helpers). Do not add outside apps or cloud services. The assistant uses
Kokoro's local British voice and a neutral, conversational personality; do not
reintroduce the cloned Rocky voice or character mannerisms.

## Current task: set up Rocky on this Mac and verify his senses

Hearing and sight were added on 2026-10-22 and tested only with synthetic
audio, fake camera frames, and a fake brain. Verify them for real.

1. **Install and download** (tell the user exactly what is missing):
   - `brew install python@3.11 ffmpeg`, Ollama installed and running
     (`curl -s http://127.0.0.1:11434/api/tags`).
   - `./setup.sh` (creates `./venv`).
   - Kokoro `bf_emma` (British English) is the default local voice; the model
     is cached on first use. The legacy standalone `rocky_say.py` tool still
     needs private Rocky voice assets if used. `./scripts/fetch_assets.sh`
     downloads those assets and additional model caches (~23 GB); it asks for
     personal, non-commercial-use confirmation. Let the user answer (never
     pass `--yes` for them). Never invent or commit voice files.
2. **Self-test:** `./venv/bin/python rocky_desktop_app.py --selftest`. Expect
   `ok` for `hearing endpointer`, `hearing ignores a click`, `sight
   look-intent`, `hearing commands (wake/sleep/track)`, and `sight face
   detector`.
3. No voice server is needed for the default Kokoro voice. Build and open:
   `./scripts/make_app.sh && open -n ./Rocky.app`.
   The bundle is what gets microphone and camera permission on macOS.
4. **Walk the user through these checks.** You cannot speak or listen; the user
   does them and tells you what happened. The top-right of the window shows
   `say "hey Rocky"` (asleep), `awake`, and `watching`.

   | # | User does | Expected |
   |---|---|---|
   | 1 | Talks normally near the Mac without saying his name | No reply (he is asleep) |
   | 2 | "Hey Rocky" | Eyes look up; indicator shows `awake`; no speech |
   | 3 | "How are you?" (no name) | He answers in the selected local voice |
   | 4 | "What am I holding?" while holding something | Camera look; answer about the object |
   | 5 | "Rocky, look left" | Eyes turn, then he describes what he sees |
   | 6 | "Track me", then moves left and right | `watching` shows; camera light on; eyes follow |
   | 7 | "Stop tracking" | `watching` disappears; camera light off |
   | 8 | "Rocky, sleep" | "Goodnight, friend."; indicator back to `say "hey Rocky"`; eyes doze |
   | 9 | F1 hold, speak, release | Push-to-talk still answers without "hey Rocky" |
   | 10 | Speakers (no headphones), a long answer | He does not answer his own voice |

5. **Record results** in `HANDOFF.md` under "Not yet verified on a Mac": date,
   self-test output, each check's result, and any errors (last ~30 lines of
   `~/Library/Logs/Rocky.log`). Tick "Verify hearing and sight on the Mac" in
   `HANDOFF.md` and `docs/ROADMAP.md` if everything passed.
6. **Commit and push** to `origin main` (github.com/dgooding/rocky). Never
   commit `assets/*`, `logs/`, `venv/`, or model caches.

### Tuning and known trouble spots

All hearing/sight knobs are near the top of `rocky_desktop_app.py` or in
`Endpointer`/`Watcher`:

- **He never wakes:** check the window says `say "hey Rocky"` (F4 toggles
  hands-free). Look at the subtitle: if faster-whisper writes his name
  differently, extend `WAKE_PATTERN`. If speech is never detected, lower the
  floor in `Endpointer.threshold()` (`0.012`).
- **He wakes on noise or cuts you off:** raise `Endpointer.threshold()`, or
  raise `--end-silence-ms` (700 default) so pauses do not end your turn. Add any phantom words
  faster-whisper invents in room noise to `PHANTOM_PHRASES`.
- **He answers his own voice:** raise the 0.4 s tail in `play_with_envelope`
  (`quiet_until`). There is no echo cancellation yet.
- **No mic or camera input, no error:** macOS gives permission to the launching
  app. Run `Rocky.app` (not a bare `python`), and allow it in System Settings →
  Privacy & Security → Microphone/Camera.
- **Eyes follow the wrong way:** flip the sign of `seen[0]` in the gaze code in
  `run()`. The default assumes the webcam image is not mirrored.
- **Silent replies:** `curl -s http://127.0.0.1:59720/health`; voice server log
  is `logs/rocky_server.log`.
- **`fetch_assets.sh` says a file "is not the expected file type":** the
  upstream link changed; tell the user and use `restore_assets.sh` with a
  backup instead.

Natural next upgrades, matching the desk robot: Silero VAD + Smart Turn for
endpointing; `openWakeWord` so he does not transcribe room talk while asleep.

## Rules that always apply

- **Never commit large or restricted files.** Voice assets (`assets/*.wav`,
  `assets/*.pth`, `*.mp3`), models, caches, and secrets stay out of git. If a
  new large file is needed, add its download to `scripts/fetch_assets.sh`. The
  project is CC BY-NC 4.0; Rocky's voice is film IP for personal,
  non-commercial use only.
- **Keep the local path working without API keys.** Do not route audio, text,
  or camera frames to a cloud service unless the user explicitly opts in.
- **No hidden capture.** Watch mode stays opt-in and visibly indicated; the
  window must always show which senses are on.
- **Keep the pins in `requirements.txt`** (`numpy==1.26.4`,
  `opencv-python-headless==4.11.0.86`); newer OpenCV pulls numpy 2 and breaks
  XTTS.
- **The macOS app launcher must not use `exec`** (`scripts/make_app.sh`), or
  camera/mic permission breaks.
- Measured numbers live in [`docs/LATENCY.md`](docs/LATENCY.md); do not quote
  vendor latency claims as measurements.

## Commands

| Task | Command |
|---|---|
| Install Rocky's dependencies | `./setup.sh` |
| Download legacy voice files and models (not in git) | `./scripts/fetch_assets.sh` (or `make fetch`) |
| Start / stop legacy voice server | `make server-start` / `make server-stop` |
| Build and open the app | `./scripts/make_app.sh && open -n ./Rocky.app` |
| Run from source (no camera permission) | `./venv/bin/python rocky_desktop_app.py` |
| Start with watch mode / without hands-free | `--watch` / `--push-to-talk` |
| Self-test (eyes, STT, brain, vision, UI, senses) | `make selftest` |
| Syntax check | `make lint` |
