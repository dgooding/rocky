# Rocky — agent instructions

Rocky is a local-first macOS desk companion: voice in, local Ollama brain,
Rocky's cloned XTTS voice out, animated eyes, and a webcam look. Start with
[`HANDOFF.md`](HANDOFF.md) for state, constraints, and phases.

## Current task: run the py-xiaozhi trial on this Mac

Before any new real-time voice code is written, test whether existing
open-source apps can serve as Rocky's foundation. The trial is fully scripted;
full steps, the human test script, and known gaps are in
[`docs/XIAOZHI_TRIAL.md`](docs/XIAOZHI_TRIAL.md). Background:
[`docs/OPEN_SOURCE_OPTIONS.md`](docs/OPEN_SOURCE_OPTIONS.md).

Do this in order:

1. **Check prerequisites** and tell the user exactly what is missing:
   - `brew`, `uv` (`brew install uv`), and `ollama` are installed, and Ollama is
     running (`curl -s http://127.0.0.1:11434/api/tags`).
   - Rocky's own environment exists: `./venv/bin/python` and voice files in
     `assets/*.wav`. These are **never on GitHub**. If missing, the user must
     run `./setup.sh` (needs `python3.11` and `ffmpeg`) and
     `./scripts/restore_assets.sh /path/to/their/backup`. Ask the user for the
     backup path; never download or invent voice assets. Without them the trial
     still runs, but Rocky is silent.
2. **Run** `./scripts/xiaozhi_trial.sh setup`. It is long (≈1 GB of downloads
   plus Ollama models) and installs into `~/rocky-xiaozhi-trial`, not this repo.
3. **Start the server** with `./scripts/xiaozhi_trial.sh server` as a
   long-running background process (it does not exit). Wait until its log
   prints the WebSocket/OTA addresses.
4. **Start the app** with `./scripts/xiaozhi_trial.sh client` in a separate
   background process. It opens a desktop window the user interacts with.
5. **Run** `./scripts/xiaozhi_trial.sh doctor` and show the user the result.
6. **Walk the user through the 8-step test table** in
   `docs/XIAOZHI_TRIAL.md`. You cannot speak or listen; the user does the
   physical tests and tells you what happened.
7. **Record results** in a new file `docs/XIAOZHI_TRIAL_RESULTS.md`: the date,
   the `doctor` report, the user's answer for each of the 8 steps, errors
   (with the last ~30 log lines), and a recommendation: **reuse**, **adapt**,
   or **reject** (fall back to the Pipecat plan in `docs/REALTIME_PLAN.md`).
   Then tick the matching Phase 0 item in `HANDOFF.md` and `docs/ROADMAP.md`,
   and commit.

### Known trouble spots

- **`libopus` not found** (server or client): the script exports
  `DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib"`; confirm
  `brew list opus` succeeds.
- **No microphone/camera input, no error**: macOS assigns permission to the
  app that launched the process (Terminal, iTerm, or VS Code). Have the user
  allow it in System Settings → Privacy & Security → Microphone/Camera, then
  restart the client. Running the client from Terminal.app is the simplest
  check.
- **Client crashes at startup** around audio/AEC: set `"ENABLED": false` under
  `AEC_OPTIONS` in `~/rocky-xiaozhi-trial/xiaozhi-data/config/config.json`.
- **Tool/function-call errors** in the server log: set `Intent: nointent` in
  `~/rocky-xiaozhi-trial/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml`
  and restart the server.
- **Silent replies**: check `curl -s http://127.0.0.1:59720/health`; Rocky's
  voice server log is `logs/rocky_server.log`.
- **Memory pressure**: the server must use the `rocky-brain` Ollama alias
  (8k context), never plain `qwen3-coder`, whose default 262k context uses
  about 45 GB.

Fix trial problems in `scripts/xiaozhi_trial.sh` or `scripts/xiaozhi/`, not in
the cloned projects under `~/rocky-xiaozhi-trial`, so fixes reach GitHub.
`setup` rewrites the server config from `scripts/xiaozhi/server.config.yaml` on
every run.

## Rules that always apply

- **Never commit voice assets** (`assets/*.wav`, `assets/*.pth`, `*.mp3`) or
  secrets. The project is CC BY-NC 4.0; Rocky's voice is film IP for personal,
  non-commercial use only.
- **Keep the local path working without API keys.** Do not route audio, text,
  or camera frames to a cloud service unless the user explicitly opts in.
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
| Start / stop Rocky's voice server | `make server-start` / `make server-stop` |
| Run the desktop app | `./venv/bin/python rocky_desktop_app.py` |
| Self-test (eyes, STT, brain, vision, UI) | `make selftest` |
| Syntax check | `make lint` |
