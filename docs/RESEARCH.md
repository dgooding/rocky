# Research notes

These are the verified facts behind [`REALTIME_PLAN.md`](REALTIME_PLAN.md).
Vendor latency claims are marked as claims; local measurements are marked as
measured. Re-check pricing and model names before committing to a provider.

## Verification standard

A first-pass set of local research summaries contained errors (for example,
"Piper does zero-shot voice cloning" and "Cartesia is preset-only"). Those
claims are false. The facts below were checked against primary documentation or
measured locally. If a number is not in this document, do not treat it as
verified.

## Voice output

| Engine | First-audio claim | Voice cloning | Streaming | Notes |
|---|---|---|---|---|
| Cartesia Sonic 3.6 | ~90 ms first byte (vendor) | Instant, 10 s clip | WebSocket, continuations | Strong cascade candidate |
| ElevenLabs Flash v2.5 | ~75 ms excluding app/network (vendor) | Instant, short sample | Yes | Mature Python SDK |
| OpenAI Realtime | Native audio; latency network-dependent | Custom voice from sample + consent | Yes | One session, native interruption |
| XTTS v2 | **2.4–3.8 s per clause (measured)** | Zero-shot, 15 s | `inference_stream` broken here | Current engine; too slow |
| Piper | Fast local | **No zero-shot clone** | Yes | Fine-tune for offline |
| Kokoro | Fast local | **No clone** | Yes | Pair with RVC if needed |

### Cartesia

From the official docs:

- Sonic 3.6 "streams the first byte of audio in about 90ms".
- Instant voice clone works from a 10 s recording; up to 60 s improves accent
  retention on newer models.
- WebSocket continuations let you push an LLM transcript in parts and receive
  audio chunks in real time.
- Sonic 3 (older) was listed at ~190 ms median latency.

Source: <https://docs.cartesia.ai/get-started/overview> and
<https://docs.cartesia.ai/build-with-cartesia/capability-guides/clone-voices>.

### ElevenLabs

From the official docs:

- Flash v2.5 is the fastest model, "~75ms" excluding application and network
  latency.
- Instant Voice Cloning is few-shot adaptation: no training, uses the sample as
  a conditioning signal. Under two minutes can produce a usable clone; more
  varied samples improve consistency.
- It generalizes less well across styles than a fine-tune.

Sources: <https://elevenlabs.io/docs/overview/models> and
<https://elevenlabs.io/docs/eleven-api/concepts/voice-cloning>.

### OpenAI Realtime

From the official API docs:

- `gpt-realtime` family; audio input/output, `semantic_vad` turn detection.
- Custom voices can be created from an audio sample plus a consent recording;
  the Realtime session accepts `{"voice": {"id": "..."}}`.
- `input_image` content is supported in Realtime user messages (PNG/JPEG data
  URI).
- Interruption is native; `response.cancel` stops the current response.

Sources: <https://developers.openai.com/api/docs/guides/realtime-conversations>,
<https://developers.openai.com/api/docs/guides/custom-voices>, and
<https://developers.openai.com/api/reference/resources/realtime/server-events>.

### XTTS v2

Measured locally with the pinned stack:

- Server cold load: ~22 s.
- `"Hi."`: 3.77 s synthesis, 2.37 s audio.
- `"Hello friend."`: 2.77 s synthesis, 1.72 s audio.
- 36-character sentence: 2.44 s synthesis, 1.48 s audio.
- 47-character sentence: 3.46 s synthesis, 2.13 s audio.

`inference_stream` raises a `torch.isin` `TypeError` with
`transformers==4.44.0` / `torch==2.5.1`. See [`LATENCY.md`](LATENCY.md) for the
traceback and reproduction.

## Speech-to-text and turn detection

| Tool | What is verified | Notes |
|---|---|---|
| Deepgram Nova-3 | Streaming WebSocket; `endpointing` ms; `speech_final`; `UtteranceEnd` | 300–500 ms recommended for conversational pauses |
| Cartesia Ink 2 | Streaming STT with native turn detection | Pairs with Sonic |
| WhisperKit | On-device CoreML Whisper; streaming supported | Good local fallback |
| Silero VAD | Local VAD; Pipecat says 150–200 ms faster than network VAD | Use for speech start/stop |
| Pipecat Smart Turn v3 | Local turn-completion model bundled with Pipecat | Use with Silero `stop_secs=0.2` |

Deepgram's docs show:

```python
with client.listen.v1.connect(
    model="nova-3",
    language="en-US",
    endpointing=300,          # 300 ms of silence triggers speech_final
    interim_results=True,
    utterance_end_ms="1000",
    vad_events=True,
) as connection:
    ...
```

Source: <https://developers.deepgram.com/docs/understand-endpointing-interim-results>
and <https://developers.deepgram.com/docs/utterance-end>.

Do not quote a single "Nova-3 latency" number unless the vendor publishes one
for your exact configuration. Endpointing and network path dominate the
perceived delay.

## Orchestration

Pipecat is a Python framework with:

- `LocalAudioTransport` using PyAudio for local mic/speakers (macOS requires
  `brew install portaudio`).
- `SileroVADAnalyzer` for local VAD.
- `LocalSmartTurnAnalyzerV3` for local turn completion.
- Interruption handling and a `Pipeline` of frame processors.
- Service adapters for Deepgram, Cartesia, ElevenLabs, OpenAI, and others.

Sources:
<https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/transports/local/audio.py>
and <https://github.com/pipecat-ai/docs/blob/main/pipecat-cloud/guides/smart-turn.mdx>.

LiveKit Agents is a reasonable alternative if you need WebRTC or remote clients.
TEN is more complex than a single desktop app needs.

## Vision

| Option | Verified capability | Notes |
|---|---|---|
| Gemini Live | Accepts JPEG/PNG video frames; max 1 FPS; native audio in/out | Python SDK `send_realtime_input(video=...)` |
| OpenAI Realtime | `input_image` in user messages | Same session as voice |
| Moondream 2 | Small local VLM | Fast; lower accuracy than qwen2.5vl |
| SmolVLM2 | Small local VLM/video | Good for low-power always-on |
| qwen2.5vl:3b | Local VLM via Ollama | Current vision model; ~6 s after model swap |
| MediaPipe / YOLO | Local face/hand/pose/object detection | Use for always-on, not a VLM |

Gemini Live docs show individual frames at a maximum of 1 FPS:

```python
await session.send_realtime_input(
    video=types.Blob(data=frame, mime_type="image/jpeg")
)
```

Source: <https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk>.

## macOS audio and AEC

- `AVAudioEngine.inputNode.setVoiceProcessingEnabled(true)` enables Apple's
  voice-processing IO (AEC, noise suppression, AGC). It must be called before
  reading the node format.
- `sounddevice`/PortAudio does not provide AEC by itself.
- `python-webrtc-audio-processing` exists but is an older wrapper; test it
  before relying on it.
- A small Swift helper is the most reliable way to get native AEC into a Python
  app.

Source: Apple AVFAudio `setVoiceProcessingEnabled(_:)` documentation, plus
working examples in open-source macOS audio projects.

## What this means

1. The brain is not the problem. Local `qwen3-coder` is ~0.1 s warm.
2. XTTS is the problem. It cannot meet the target as-is.
3. The fastest route to a real-time feel is a speech-to-speech session
   (OpenAI Realtime) or a streaming cascade with Cartesia/ElevenLabs.
4. The cascade keeps Rocky's voice but needs AEC, streaming playback, and
   cancellation to feel right.
5. The camera should be a cheap always-on detector plus an on-demand VLM, not a
   VLM on every frame.

## Caveats

- Vendor latency claims exclude application and network latency; measure p95 on
  your machine and network.
- Voice-clone quality is not captured by latency numbers. Run a blind similarity
  test with 10–20 phrases before committing.
- Pricing changes; check the provider's current page.
- The Rocky voice is film IP. Personal, non-commercial use only. Cloud cloning
  may require consent verification and may still violate the character rights.
- Public benchmarks are not a substitute for a 20-turn test in your actual room.
