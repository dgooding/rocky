# Latency measurements

All numbers are wall-clock measurements on the development machine:

- Apple M1 Max, 64 GB unified memory
- macOS 27.0.1
- Python 3.11.17
- `TTS==0.22.0`, `transformers==4.44.0`, `torch==2.5.1`
- Ollama with `qwen3-coder:latest` at `num_ctx=8192`

They are not vendor benchmarks. Re-run them on your machine before making
decisions.

## Summary

| Stage | Measured | Notes |
|---|---:|---|
| XTTS server cold load | ~22 s | Weights already downloaded |
| XTTS `"Hi."` | 3.77 s | 2.37 s of audio |
| XTTS `"Hello friend."` | 2.77 s | 1.72 s of audio |
| XTTS 36-char sentence | 2.44 s | 1.48 s of audio |
| XTTS 47-char sentence | 3.46 s | 2.13 s of audio |
| `qwen3-coder` first token | 0.07–0.15 s | Warm, local Ollama |
| `qwen3-coder` full reply | ~0.22 s | 45-token cap |
| faster-whisper `base.en` | ~0.4 s | After key release |
| `qwen2.5vl:3b` vision | ~0.4 s warm / ~6 s after swap | Ollama |
| End-to-end first sound | ~3–5 s | Dominated by XTTS |

The brain is not the bottleneck. XTTS is.

## Reproduce the TTS numbers

Start the voice server:

```sh
COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start
```

Then time a few phrases through the server:

```sh
./venv/bin/python - <<'PY'
import io, time
import soundfile as sf
import rocky_say as r

for text in ["Hi.", "Hello friend.",
             "Hello friend, I am happy to see you.",
             "Checking the oxygen recyclers again, as always."]:
    t0 = time.time()
    wav = r.generate_via_server(text)
    dt = time.time() - t0
    data, rate = sf.read(io.BytesIO(wav))
    print(f"{len(text):2d} chars | {dt:.2f}s synth | {len(data)/rate:.2f}s audio | {text}")
PY
```

Observed output:

```text
 3 chars | 3.77s synth | 2.37s audio | Hi.
13 chars | 2.77s synth | 1.72s audio | Hello friend.
36 chars | 2.44s synth | 1.48s audio | Hello friend, I am happy to see you.
47 chars | 3.46s synth | 2.13s audio | Checking the oxygen recyclers again, as always.
```

Short phrases are not proportionally faster: fixed overhead dominates. This is
why shrinking the first clause alone will not get you to sub-second audio.

## The streaming API is currently broken

`TTS 0.22.0` exposes `Xtts.inference_stream()`:

```python
model.inference_stream(
    text, "en", gpt_cond, spk_emb,
    stream_chunk_size=20, speed=1.25
)
```

With the pinned `transformers==4.44.0` / `torch==2.5.1` stack it raises:

```text
TypeError: isin() received an invalid combination of arguments - got
(test_elements=int, elements=Tensor, ), but expected one of:
 * (Tensor elements, Tensor test_elements, ...)
 * (Number element, Tensor test_elements, ...)
```

The failure is in `transformers/generation/utils.py` calling
`torch.isin(elements=..., test_elements=pad_token_id)` with a scalar. The
non-streaming `inference()` path used by the server works.

Implication: do not plan on `inference_stream` as a drop-in latency fix unless
you pin/patch the transformers/torch combination and re-benchmark. The
real-time plan recommends replacing XTTS with a streaming TTS engine instead.

## Reproduce the brain numbers

```sh
./venv/bin/python - <<'PY'
import time
from rocky_desktop_app import Brain

b = Brain()
print("available:", b.available())
t0 = time.time()
b.warm()
print("warm: %.2fs" % (time.time() - t0))

for q in ["Hello Rocky, what are you doing?",
          "I brought you a coffee."]:
    t0 = time.time()
    first = None
    out = []
    for delta in b.stream(q):
        if first is None:
            first = time.time() - t0
        out.append(delta)
    print("%-34s first=%.2fs total=%.2fs | %s"
          % (q, first, time.time() - t0, "".join(out)))
PY
```

Observed:

```text
model: qwen3-coder:latest context: 8192 available: True
warm: 0.16s
Hello Rocky, what are you doing?   first=0.11s total=0.22s | Checking the oxygen recyclers for any issues.
I brought you a coffee.            first=0.07s total=0.23s | Thanks, I was hoping you'd get the decaf.
```

## Why end-to-end is 3–5 s

The app waits for key release, then:

1. transcribes the whole utterance (~0.4 s),
2. gets the first LLM token (~0.1 s),
3. waits for the first complete sentence,
4. sends the first clause to XTTS (~2.4–3.8 s),
5. loads and plays the WAV.

Steps 3–4 dominate. The prefetch queue overlaps later clauses with playback, but
it cannot make the first clause arrive sooner.

## Target budget for the redesign

| Stage | Target |
|---|---:|
| Speech-end / endpointing | 200–300 ms |
| Streaming STT final | 100–250 ms |
| LLM first token | 100–300 ms |
| TTS first audio | 75–150 ms + network |
| Playback buffer | 20–50 ms |
| **First sound** | **500–800 ms cascade / 300–700 ms speech-to-speech** |

A pre-generated backchannel in Rocky's voice can mask the remaining gap and make
the interaction feel faster than the measured time-to-first-word.

See [`REALTIME_PLAN.md`](REALTIME_PLAN.md) for the implementation plan and
[`RESEARCH.md`](RESEARCH.md) for the verified vendor claims.
