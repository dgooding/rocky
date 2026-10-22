# Troubleshooting

## Camera

### The camera light never turns on

macOS attributes camera access to the app bundle. A bare `python` process has no
stable bundle identity and is silently denied.

- Launch `Rocky.app`, not `./venv/bin/python rocky_desktop_app.py`.
- Check **System Settings → Privacy & Security → Camera**.
- Rebuild and re-sign the bundle if you moved the repo:
  `./scripts/make_app.sh && codesign --force --sign - --identifier com.aiserver.rocky ./Rocky.app`.
- If the prompt returns after re-signing, allow it once.

### The camera opens but frames are black

`Camera.snapshot()` discards five warm-up frames. Some cameras need more. Try a
different `--camera-index`, close other apps using the camera, or increase the
warm-up count in `Camera.snapshot()`.

### The camera works from the app but not from the terminal

This is expected. Use the app bundle for camera work, or grant your terminal
camera access and accept that the identity is less stable.

## Audio

### No sound

- Check the system output device.
- The app uses `pygame.mixer`; a device change after startup may require a
  restart.
- Look for `[audio]` lines in `~/Library/Logs/Rocky.log` (bundle) or
  `$TMPDIR/rocky-desk.log`.

### The voice server is slow or requests queue

The XTTS server is single-threaded. Two callers queue behind each other; a 1.2 s
synthesis can look like 12 s. Do not run a second client against
`127.0.0.1:59720` while the app is speaking.

Check the server log:

```sh
tail -50 logs/rocky_server.log
curl -s http://127.0.0.1:59720/health
```

Restart it:

```sh
./venv/bin/python rocky_say.py --server stop
COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start
```

### `inference_stream` raises `TypeError: isin()`

Known issue with `transformers==4.44.0` / `torch==2.5.1` in this environment. The
server uses the non-streaming `inference()` path, which works. See
[`LATENCY.md`](LATENCY.md). Do not switch the app to `inference_stream` without
pinning or patching the stack.

### Rocky hears himself / feedback

The current app does not open the mic during playback, so this should not happen
yet. If you add barge-in, add AEC first (see the plan). Headphones are the
quickest workaround.

## Python environment

### `numpy` upgraded to 2.x and XTTS broke

`gruut` requires numpy `<2`. Reinstall the pins:

```sh
./venv/bin/pip install "numpy==1.26.4" "opencv-python-headless==4.11.0.86"
```

Do not install a current OpenCV wheel into this venv; it may upgrade numpy.

### `python3.11` not found

```sh
brew install python@3.11
python3.11 --version
```

TTS 0.22.0 does not support Python 3.12+.

### `ffmpeg` missing

```sh
brew install ffmpeg
```

## Ollama

### Brain not available

```sh
ollama list
ollama pull qwen3-coder
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool
```

If you use a hosted brain, check `--brain-url` and `--brain-key`, or set
`BRAIN_API_KEY`.

### Model swap takes ~6 seconds

Ollama may unload `qwen2.5vl` when `qwen3-coder` is loaded (or vice versa). Check:

```sh
curl -s http://127.0.0.1:11434/api/ps | python3 -m json.tool
```

Keep models resident with `keep_alive`, avoid switching, or use a single
multimodal session in the real-time redesign.

### qwen2.5vl hallucinates objects

Use temperature 0.1 and a neutral prompt. At 0.6 it has been observed to invent
objects ("you are holding a guitar"). The app already uses a low temperature for
vision.

### Vision model drops the first character when streamed

Local vision requests are intentionally non-streamed. Do not "fix" this by
enabling streaming for `moondream` or similar models.

## App bundle

### `exec` in the launcher breaks the camera

The launcher must stay alive as the parent process. `exec python ...` replaces
the bundle process and loses the bundle identity. `scripts/make_app.sh` already
does the right thing.

### The app opens but the repo path is wrong

The generated launcher embeds the absolute path at build time. If you move the
repository, rebuild:

```sh
./scripts/make_app.sh
```

### Re-signing and permissions

```sh
codesign --force --sign - --identifier com.aiserver.rocky ./Rocky.app
open -n ./Rocky.app
```

If macOS asks again, allow camera/microphone once. The identifier stays
`com.aiserver.rocky`.

## Assets

### `assets/rocky_ref_15s.wav` missing

The repository does not include voice assets. Download them, or restore your
own backup:

```sh
./scripts/fetch_assets.sh
./scripts/restore_assets.sh /path/to/your/rocky-assets
```

### The voice sounds wrong or robotic

- Use `assets/rocky_ref_15s.wav` (preferred over the 2:10 clip).
- Check `ROCKY_SPEED` (default 1.25). Lower it for more natural pacing, at the
  cost of longer audio.
- The reference clip quality dominates the clone. Use clean, consistent speech.

## Git / repository

### Voice assets accidentally staged

They should be ignored by `.gitignore`. Check:

```sh
git status --short
git check-ignore -v assets/rocky_voice.pth
```

If they are already tracked:

```sh
git rm --cached assets/rocky_voice.pth assets/rocky_training_audio_scrubbed.wav assets/rocky_ref_15s.wav
```

Do not rewrite public history without coordinating with collaborators.

### Repository is large

The app code and shots are small. If the repo grows, check for `venv/`,
`logs/`, `archives/`, `*.wav`, `*.pth`, and `Rocky.app/` accidentally committed.

## Logs

| Context | Path |
|---|---|
| App bundle | `~/Library/Logs/Rocky.log` |
| Bare Python | `$TMPDIR/rocky-desk.log` |
| XTTS server | `logs/rocky_server.log` |
| Last camera frame | `logs/last_look.jpg` |
| Last spoken WAV | `logs/desk_last.wav` |

## Still stuck?

Capture:

```sh
uname -a
sw_vers
./venv/bin/python --version
./venv/bin/pip show numpy opencv-python-headless TTS transformers torch
ollama list
curl -s http://127.0.0.1:59720/health
tail -100 ~/Library/Logs/Rocky.log
```

Open an issue with those details and the smallest reproduction you can make.
