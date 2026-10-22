# Xiaozhi trial: can an existing app be Rocky's foundation?

This is the hands-on proof-of-fit from
[`OPEN_SOURCE_OPTIONS.md`](OPEN_SOURCE_OPTIONS.md). It runs two existing
MIT-licensed projects on your Mac, wired entirely to local services:

```text
py-xiaozhi (desktop app: mic, speaker, AEC, GUI, camera)
      │  WebSocket (Opus audio)
      ▼
xiaozhi-esp32-server (self-hosted on 127.0.0.1)
      ├─ Silero VAD + SenseVoice speech-to-text   (local)
      ├─ Ollama rocky-brain = qwen3-coder, 8k ctx (local)
      ├─ Ollama qwen2.5vl:3b vision               (local)
      └─ Rocky's XTTS voice server :59720         (local, existing)
```

**Why the server is needed:** out of the box, py-xiaozhi is only a client and
sends your audio to the hosted xiaozhi service at `api.tenclass.net`. The trial
points it at a self-hosted
[xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)
instead. That server's `custom` text-to-speech provider sends
`POST {"text": ...}` and expects audio back, which is exactly what Rocky's
existing voice server accepts, so no new voice code is needed.

**What this trial answers:** whether the app plumbing (continuous listening,
pause detection, interruption, echo cancellation, GUI, camera) is good enough to
build on. It does **not** make Rocky's voice faster: XTTS still takes about
2.4–3.8 s per clause, so first-audio time will be slow. Judge the experience
around the voice, not the voice latency.

## Before you start

- A Mac with [Homebrew](https://brew.sh) and
  [Ollama](https://ollama.com) installed, and Ollama running.
- `uv` (`brew install uv`).
- About 15 GB free disk (models and Python environments).
- For Rocky's voice: this repo set up with `./setup.sh` and the voice assets
  restored (`./scripts/restore_assets.sh ...`). Without them the trial still
  runs, but replies are silent.
- Headphones, for the first round.

Everything is installed in `~/rocky-xiaozhi-trial`, outside this repo. Delete
that folder to remove it. (Ollama models and Homebrew packages stay installed.)

## Run it

From the repo root:

```sh
git pull
chmod +x scripts/xiaozhi_trial.sh

./scripts/xiaozhi_trial.sh setup      # one time; downloads ~1 GB plus models
./scripts/xiaozhi_trial.sh server     # terminal 1 — leave running
./scripts/xiaozhi_trial.sh client     # terminal 2 — opens the app
./scripts/xiaozhi_trial.sh doctor     # any time — writes ~/rocky-xiaozhi-trial/report.txt
```

`setup` installs `opus`, `ffmpeg`, and `portaudio` with Homebrew if they are
missing, pulls `qwen3-coder` and `qwen2.5vl:3b` if needed, and creates an
Ollama alias `rocky-brain` with an 8k context. The server talks to Ollama's
OpenAI-compatible API, which cannot set the context size per request, and
`qwen3-coder`'s default 262k context would use about 45 GB of memory.

The app's shortcuts include **Ctrl+J** (hold to talk), **Ctrl+K** (hands-free
mode), and **Ctrl+Q** (interrupt). If the GUI fails, try
`./scripts/xiaozhi_trial.sh client --mode cli`.

## Test script

Do these in order and note what happens. Rough timings by feel are fine.

| # | Do this | Record |
|---|---|---|
| 1 | Run `doctor` with everything started | Paste `report.txt` |
| 2 | Hold Ctrl+J, say "Hello Rocky, how are you?" | Did it hear you correctly? Did Rocky's voice answer? Seconds until he spoke? |
| 3 | Switch to hands-free (Ctrl+K), ask three questions in a row without pressing keys | Did it notice when you stopped talking? Any cut-offs mid-sentence? |
| 4 | While Rocky is talking, start talking over him (with headphones) | Did he stop? How quickly? Did he hear what you said? |
| 5 | Repeat step 4 **without** headphones (speakers) | Did he hear himself and reply to his own voice? |
| 6 | Ask "What do you see?" or "Look at what I'm holding" | Did the camera turn on? Was the answer right? Any errors in terminal 1? |
| 7 | Turn Wi-Fi off, then repeat step 2 | Did everything still work? |
| 8 | Look at the app overall | Would you be happy building on this window/UI, or only on its internals? |

## What to send back

1. `~/rocky-xiaozhi-trial/report.txt`
2. Your notes from the table above.
3. Any errors from terminal 1 (server) or terminal 2 (app). Copy the last
   30 lines or so.

## Known gaps going in

- **Rocky's grammar transform isn't applied.** The desktop app runs
  `rocky_transform()` before speaking; the voice server alone does not. Rocky
  will speak the brain's plain English.
- **No Rocky eyes.** The trial shows py-xiaozhi's own UI. If the plumbing
  passes, the eyes can be ported or the app's UI replaced.
- **Echo cancellation is turned on in the client config** (`AEC_OPTIONS`), but
  it is untested on macOS. If the client errors at startup, set
  `"ENABLED": false` in `~/rocky-xiaozhi-trial/xiaozhi-data/config/config.json`.
- **Camera/tool calls use `Intent: function_call`.** If plain conversation
  fails with tool errors in terminal 1, change `Intent` to `nointent` in
  `~/rocky-xiaozhi-trial/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml`
  and restart the server (this disables voice-triggered camera).
- **Some built-in features are cloud-backed** (for example music search). The
  trial doesn't use them; Wi-Fi-off in step 7 will show anything else that is.
- The trial uses the latest `main` of both projects; `doctor` records the exact
  commits tested.

## Configuration files

- [`scripts/xiaozhi/server.config.yaml`](../scripts/xiaozhi/server.config.yaml):
  local-only server override (Rocky persona, providers, ports). Copied into the
  server on every `setup`.
- [`scripts/xiaozhi/client.config.json`](../scripts/xiaozhi/client.config.json):
  client settings (local server address, wake word off, local camera vision,
  AEC on). Copied only on the first `setup`, because the app adds its own
  device ID to it.
