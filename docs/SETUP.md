# Setup

Tested on macOS 27.0.1, Apple Silicon (M1 Max, 64 GB), Python 3.11.17.

## 1. Prerequisites

```sh
brew install python@3.11 ffmpeg
```

- Python **3.11** — TTS caps at `<3.12`.
- `ffmpeg` — used by the upstream voice script for audio conversion.
- [Ollama](https://ollama.com/) — local brain and vision.
- Xcode Command Line Tools (for `codesign` and the app bundle):
  `xcode-select --install`.

## 2. Clone and install

```sh
git clone https://github.com/dgooding/rocky.git
cd rocky
./setup.sh
```

`setup.sh` creates `./venv`, upgrades pip, and installs
[`requirements.txt`](../requirements.txt). It does not download voice assets.

The desktop app's default Drama 3 voice has a separate isolated setup because
its MLX dependencies and model are large and must not replace the app's pinned
NumPy/Torch stack:

```sh
./scripts/setup_drama3.sh
```

This downloads about 22 GiB into the Hugging Face cache and creates a generic
British female Kokoro reference in `~/.cache/rocky`. It needs network access
only for setup; app inference is local. Drama 3 peaks around 26 GiB memory
while generating. The app offers Kokoro as a fallback with
`--tts-engine kokoro`.

Manual equivalent:

```sh
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

### Why the pins matter

- `numpy==1.26.4` — `gruut` (a TTS dependency) requires numpy `<2`.
- `opencv-python-headless==4.11.0.86` — current OpenCV wheels can silently
  upgrade numpy to 2.x and break XTTS on the next restart.
- `TTS==0.22.0`, `transformers==4.44.0`, `torch==2.5.1`,
  `torchaudio==2.5.1` — the combination used by the working server path.

Do not run `pip install -U` on the whole environment unless you are prepared to
re-pin numpy/OpenCV.

## 3. Voice assets

Place these in `assets/`:

```text
assets/rocky_ref_15s.wav              # preferred 15 s reference
assets/rocky_training_audio_scrubbed.wav
assets/rocky_voice.pth                # RVC model, optional for XTTS path
```

The repository does not include them. Download them from the upstream author's
published links (see `docs/GUIDE.md`) with:

```sh
./scripts/fetch_assets.sh
```

It asks you to confirm personal, non-commercial use, downloads
`rocky_training_audio_scrubbed.wav` and `rocky_voice.pth`, checks each file's
type, makes `rocky_ref_15s.wav` from the first 15 s of speech (with `ffmpeg`),
and never overwrites files you already have. Unless you pass `--assets-only`,
it also pulls the Ollama models below and caches the faster-whisper and XTTS
models, so the first launch does not stall. Add `--yes` to skip the prompt.

If you have your own backup (including the original hand-trimmed 15 s clip),
copy it instead:

```sh
./scripts/restore_assets.sh /path/to/your/rocky-assets
```

That script accepts a directory or a `.tar.gz` archive, verifies the files are
present and non-empty, and does not download anything.

### License warning

The voice assets are for personal, non-commercial use only. Rocky's voice design
belongs to the *Project Hail Mary* film production. Do not redistribute the
assets or use them commercially. See [`NOTICE.md`](../NOTICE.md).

## 4. Ollama models

`./scripts/fetch_assets.sh` pulls these if they are missing. To do it by hand:

```sh
ollama pull qwen3-coder       # brain, ~18 GB
ollama pull qwen2.5vl:3b      # vision, ~3.2 GB
```

Optional fast fallback:

```sh
ollama pull llama3.2:3b
```

Check what is loaded:

```sh
curl -s http://127.0.0.1:11434/api/ps | python3 -m json.tool
```

`qwen3-coder` defaults to a 262k context and can reserve ~45 GB. The app pins
`num_ctx=8192` (~19 GB). If another client loads it at 262k, Rocky's first turn
may trigger a 5 s reload; the app warms the brain at startup, so this usually
happens before you speak.

## 5. Start the voice server

```sh
COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start
```

- First load: ~20 s.
- Health check: `curl -s http://127.0.0.1:59720/health`
- Log: `logs/rocky_server.log`
- Stop: `./venv/bin/python rocky_say.py --server stop`

The server is single-threaded. Do not run another client against it while the
app is speaking; requests queue.

## 6. Build the macOS app bundle

```sh
./scripts/make_app.sh
codesign --force --sign - --identifier com.aiserver.rocky ./Rocky.app
open -n ./Rocky.app
```

Why a bundle:

- macOS attributes camera and microphone permission to the `.app` identity.
- A bare `python` process has no stable bundle identity and is silently denied
  camera access.
- The launcher must not use `exec`; replacing the bundle process loses the
  identity.

If macOS prompts, allow camera and microphone once. If you re-sign and the
prompt returns, allow it again. The bundle ID stays `com.aiserver.rocky`.

### Install to /Applications

```sh
cp -R ./Rocky.app /Applications/
open -n /Applications/Rocky.app
```

The generated launcher points at the repository path at build time. If you move
the repo, rebuild the bundle with `./scripts/make_app.sh`.

## 7. Run without the bundle

```sh
./venv/bin/python rocky_desktop_app.py
```

Camera access will likely be denied; use `--no-camera` if you only need voice.

## 8. Hosted brain (optional)

```sh
export BRAIN_API_KEY=...
./venv/bin/python rocky_desktop_app.py \
  --brain-api openai \
  --brain-url https://api.deepseek.com/v1 \
  --brain-model deepseek-chat
```

Anthropic:

```sh
./venv/bin/python rocky_desktop_app.py \
  --brain-api anthropic \
  --brain-url https://api.anthropic.com/v1 \
  --brain-model claude-sonnet-4-5
```

For hosted vision, set `--vision-model` to a vision-capable model from the same
provider.

## 9. Verify

```sh
# Eye presets
./venv/bin/python rocky_eyes.py --selftest shots/eyes

# STT + brain + synthetic vision + UI states
./venv/bin/python rocky_desktop_app.py --selftest

# Camera permission through the bundle
open -n ./Rocky.app --args --snap /tmp/cam.jpg
ls -lh /tmp/cam.jpg

# Voice server
curl -s http://127.0.0.1:59720/health
```

Expected self-test output includes:

```text
[selftest] ollama reachable: True
[selftest] stt (...): 'Hello, friend, are you okay, question? ...'
[selftest] vision (...): 'The main object is a red square.'
[selftest] shots -> .../shots/app_*.png
```

## 10. Next steps

The current app is turn-based. See [`REALTIME_PLAN.md`](REALTIME_PLAN.md) for
the streaming audio, barge-in, AEC, and continuous-vision redesign.
