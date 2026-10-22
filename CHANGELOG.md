# Changelog

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
