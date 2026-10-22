# Changelog

## 2026-10-22 (later)

- **Hearing:** hands-free listening (`Ears` + `Endpointer`): continuous 20 ms
  mic frames, adaptive noise floor, 700 ms end-of-turn. Like the
  [desk robot](https://github.com/cgro00/desk-robot) Rocky is modelled on,
  "hey Rocky" wakes him (his name alone does not), he stays awake for 60 s
  after each exchange, and "Rocky, sleep" / "goodnight" puts him back to sleep.
  The mic is ignored while he thinks or speaks. F4 / `--push-to-talk`.
- **Sight:** "what do you see?", "what am I holding?", and "look left" take a
  camera look and pass the question to the vision model. Opt-in watch mode
  ("track me", F5, `--watch`) runs local OpenCV face detection so his eyes
  follow you; he perks up when you arrive and dozes when ignored.
- The window always shows which senses are on.
- `scripts/fetch_assets.sh` (and `make fetch`) downloads everything large that
  is not in git: Rocky's voice files from the upstream author's published
  links, the Ollama models, and the faster-whisper and XTTS caches.
- `--selftest` checks the hearing and sight logic without a mic or camera.
- Removed the outside-app trial kit; Rocky's own app is the foundation.

## 2026-10-22

- Published the desktop app, eyes, camera path, and voice server as a standalone
  repository.
- Added the full project handbook, architecture, setup, latency, research,
  roadmap, troubleshooting, and security docs.
- Switched the default brain to `qwen3-coder:latest` with `num_ctx=8192`
  (~19 GB instead of ~45 GB).
- Documented that XTTS is the real-time bottleneck and that
  `inference_stream` is broken with the pinned transformers/torch stack.
- Added a research-backed real-time redesign plan with OpenAI Realtime and
  Pipecat/Cartesia/ElevenLabs options.
- Excluded the restricted voice assets from the public repository and added a
  private restore script.

## 2026-10-21

- Desktop app: mic, faster-whisper, Ollama brain, XTTS voice, camera vision,
  animated eyes, typed input, seven emotions.
- macOS `.app` launcher with camera/microphone usage strings.
- Persistent XTTS server with cached conditioning latents.
- Eye preset selftest and app selftest.
- Local vision via `qwen2.5vl:3b`.
