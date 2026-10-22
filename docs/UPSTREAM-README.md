> **Upstream reference.** This README comes from
> [`Kuberwastaken/rocky-tts`](https://github.com/Kuberwastaken/rocky-tts) and is
> preserved for attribution. Voice assets are **not** included in this
> repository; see [`../NOTICE.md`](../NOTICE.md) and
> [`../assets/README.md`](../assets/README.md).

# Rocky TTS

A plug-and-play text-to-speech voice clone of Rocky, the Eridian alien from Andy Weir's *Project Hail Mary*, voiced by James Ortiz in the 2026 film.

Give it normal English text. It transforms the grammar into Rocky-speak, then synthesizes it in his voice.

Designed as an optional, user-triggered pluggable voice for /Rocky mode in [Claurst CLI](https://github.com/Kuberwastaken/claurst)

```
python rocky_say.py "I don't understand what you mean."
# Rocky: No understand what mean, question?
# [plays audio in Rocky's voice]
```

## How it works

Two steps happen on every call:

1. **Text transform** -- rule-based grammar rewrite into Rocky's speech patterns (dropped articles, simplified tense, word tripling for emphasis, "question?" suffix on interrogatives)
2. **Voice synthesis** -- YourTTS or XTTS v2 zero-shot voice cloning using 2 minutes of cleaned training audio from the film

## Setup

Requires Python 3.10+ and ffmpeg.

**Windows:**
```bat
setup.bat
```

**macOS / Linux:**
```bash
chmod +x setup.sh && ./setup.sh
```

Both scripts create a venv, install dependencies, and download the voice assets automatically. First run takes a few minutes to pull the TTS models.

## Usage

```
python rocky_say.py "Hello, how are you doing today?"
python rocky_say.py --transform-only "What does that mean?"   # just show the rewrite
python rocky_say.py --raw "No understand"                     # skip transform
python rocky_say.py -m xtts "Try XTTS instead of YourTTS"
python rocky_say.py -m rvc "Highest quality, needs rocky_voice.pth"
python rocky_say.py -s 1.2 -o out.wav "Save to file"
python rocky_say.py -f file.txt                               # read from file
echo "some text" | python rocky_say.py                        # pipe input
```

### Voice models

| Model | Quality | Speed | Notes |
|---|---|---|---|
| `yourtts` | good | ~2s | default, recommended |
| `xtts` | good | ~3s server / ~22s cold | start server for speed |
| `rvc` | best | slow | XTTS + trained RVC conversion |

Start a persistent server to avoid the cold-start penalty:

```
python rocky_say.py --server start
python rocky_say.py --server status
python rocky_say.py --server stop
```

### Transform examples

| Input | Rocky |
|---|---|
| "I don't understand" | "No understand" |
| "What do you mean?" | "What mean, question?" |
| "That's amazing!" | "That amaze amaze amaze!" |
| "This is terrible" | "This bad bad bad" |
| "Goodbye" | "See you later. But I no see you later" |

## Credits

Original script, voice training pipeline, and audio assets by Pedram Amini.
Gist: https://gist.github.com/pedramamini/fa5f6ef99dae79add220188419230642

Rocky's voice was built by:
- Extracting 11 dialogue scenes from the film
- Isolating vocals with Meta's demucs
- Speaker diarization via pyannote to separate Rocky from Grace
- Manual review of 84 clean Rocky segments
- Zero-shot voice cloning via Coqui TTS XTTS v2

## License

CC BY-NC 4.0 -- personal, non-commercial use only.

Rocky's voice design is IP of the film's production company. XTTS v2 is under Coqui's non-commercial CPML license. See [LICENSE](../LICENSE).
