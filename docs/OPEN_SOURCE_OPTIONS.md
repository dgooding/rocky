# Open-source app survey

Checked 2026-10-22 against project READMEs, source files, and licenses. This is
a reuse-first shortlist, not an endorsement: features and latency stated by
project authors are claims until tested on Rocky's hardware.

**Selection rule:** English-first projects only (UI, docs, defaults, and
maintainer communication), runnable on macOS, with a fully local path.

## Decision (2026-10-22)

**Not adopting an outside app.** The owner chose to build on Rocky's own app
(`rocky_desktop_app.py`), modelled on Casey Grothaus's
[desk robot](https://github.com/cgro00/desk-robot) (MIT), whose eye presets it
already uses. That robot's brain (faster-whisper, Silero VAD, Smart Turn,
OpenCV face tracking) is the reference for Rocky's hearing and sight. This
survey is kept as a research record; no trial kits remain in the repo.

## Recommendation at the time of the survey

Before the decision above, the suggested order of evaluation was:

1. **[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)**:
   the closest ready-made app.
2. **[Hugging Face speech-to-speech](https://github.com/huggingface/speech-to-speech)**:
   a ready-made local voice pipeline without an app shell.
3. **[Pipecat](https://github.com/pipecat-ai/pipecat)**: the framework to build
   on rather than reimplementing audio capture, turn detection, streaming, and
   cancellation from scratch (see [`REALTIME_PLAN.md`](REALTIME_PLAN.md)).

[Open WebUI](https://github.com/open-webui/open-webui) is a useful benchmark
for local voice chat, but not a Rocky app replacement.

## Candidates

| Project | Ready-made capabilities in its public docs | Fit and limitations for Rocky | Recommendation |
|---|---|---|---|
| [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | MIT-licensed Python server with a web UI and optional Electron desktop/pet app; about 14k stars. README: fully offline mode; macOS, Linux, and Windows; hands-free voice; interruption without headphones; camera and screen input; Ollama and many local or cloud speech-to-text and voice engines. UI falls back to English; the default config template is English. | Closest match to Rocky's goal (companion with a face, voice, camera, local brain). Its `x_tts` engine sends `POST {"text", "speaker_wav", "language"}` and saves the returned WAV, which Rocky's XTTS server already accepts. Images go to the same model that answers, so camera use needs a vision model. It calls Ollama's `/v1` API, which cannot set `num_ctx`, so `qwen3-coder` needs an 8k-context alias. Bundled Live2D sample avatars are separately licensed. v1 is in maintenance while a v2 rewrite is planned. | **Was the first candidate**; not adopted. |
| [Hugging Face speech-to-speech](https://github.com/huggingface/speech-to-speech) | Apache-2.0 local voice pipeline (Silero VAD → speech-to-text → LLM → TTS), every stage swappable; serves the OpenAI Realtime protocol; CI smoke-tests Apple Silicon macOS; picks MLX models on Apple Silicon. | Strong, well-maintained pipeline, but no app or face. Its README says to use headphones or block the mic during playback, so no echo cancellation. Using Rocky's brain or voice would need configuration or code beyond the defaults. | **Second choice**, as the pipeline behind Rocky's own UI if Open-LLM-VTuber's shell does not fit. |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Open-source Python framework for streaming voice and multimodal agents; local audio transport, Silero VAD, Smart Turn, interruption handling, many service adapters. | Not a complete app; adopting it means writing the integration. Already the basis of the existing real-time plan. | **Fallback framework.** |
| [Open WebUI](https://github.com/open-webui/open-webui) | Self-hosted interface for Ollama and OpenAI-compatible APIs; PWA; voice/video calls with multiple speech-to-text and voice backends. | General AI chat UI rather than a desktop companion. Its [license](https://github.com/open-webui/open-webui/blob/main/LICENSE) imposes branding-preservation conditions, so it is not a white-label Rocky UI. | **Benchmark or personal tool only.** |
| [LiraVtuber](https://github.com/Rukafuu/LiraVtuber) | MIT-licensed desktop assistant with voice, memory, GUI, Live2D/VTube Studio, multiple LLM and voice providers. | README targets Windows; documented voice paths include hosted services and XTTS via Colab; no established local Ollama or macOS path. Large scope (PC automation, Discord, WhatsApp) beyond Rocky's goal. | **Reference only.** |
| [Hyori / live2d-Live-Assistant](https://github.com/JSNrepo/live2d-Live-Assistant) | MIT-licensed Live2D voice companion; Gemini Live streaming with barge-in; offline fallback. | Cloud-first (Gemini) and bundles a large autonomous agent and remote-control surface. Small project. | **Reference only** for the voice/avatar experience. |
| [OpenVoiceOS](https://github.com/OpenVoiceOS/ovos-core) | Apache-2.0 voice-assistant platform with installer, skills, and LLM persona plugins. | Smart-speaker platform, not an on-screen companion. | **Not the closest fit.** |

### Screened out

- **py-xiaozhi, xiaozhi-esp32-server, and Xiaozhi Desktop.** Technically
  capable, but Chinese-first: UI text, setup guides, default providers, and
  community are primarily Chinese, and the client's default backend is a hosted
  service. They fail the selection rule. A trial kit was briefly added on
  2026-10-22 and then removed.
- **[RealtimeVoiceChat](https://github.com/KoljaB/RealtimeVoiceChat).** English
  and well regarded, but its author states it is no longer actively maintained,
  it recommends a CUDA NVIDIA GPU, and the provided installer is Windows-only.
- **[OpenClaw Desktop Assistant MVP](https://github.com/andyhuo520/openclaw-assistant-mvp).**
  Prototype with simulated data; Live2D planned, not built; no license file
  found.
- **[Leon](https://github.com/leon-ai/leon).** MIT-licensed, but the current
  2.0 developer preview is an agent/tools assistant rather than a voice
  companion.
- **[Mycroft Core](https://github.com/MycroftAI/mycroft-core).** Archived.

## Proof-of-fit checklist

Run the same small scenarios on Rocky and each runnable candidate; record
observations rather than relying on README latency claims:

1. **Platform:** runs on the target Mac and gets microphone/camera permission
   without workarounds.
2. **Local-first:** completes a voice turn with the network disconnected using
   the local Ollama models; identify every feature that still sends audio,
   text, or images to a service.
3. **Voice and interaction:** uses Rocky's voice; measure speech-end to first
   audio and how quickly speech stops when interrupted.
4. **Echo/privacy:** echo cancellation works on speakers, or a safe
   headphones-only fallback is documented; camera use is explicit and visible.
5. **Integration:** can keep Rocky's concise persona, eye emotions, typed
   input, one-shot look, and local fallback without replacing working pieces
   unnecessarily.
6. **Maintainability and license:** source availability, release cadence,
   tests, platform requirements, license obligations, and third-party
   model/asset terms.

**Decision gate:** reuse the app if it meets the required behavior and
constraints; adapt only the missing pieces if it is close; otherwise reuse its
permissively licensed components or use Pipecat for the real-time audio path.

## Licensing and privacy constraints

Rocky's own repository is CC BY-NC 4.0, and the Rocky character/voice assets
have separate rights constraints documented in `NOTICE.md` and
`assets/README.md`. A candidate app's MIT or Apache license does not grant
rights to those assets or to the Project Hail Mary character. Keep voice assets
out of the repository and confirm each provider's consent, data-retention, and
usage terms before sending audio to cloud services. For code reuse, preserve
required notices and review the complete upstream and dependency licenses.

## Sources

- Open-LLM-VTuber
  [README](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/README.md),
  [MIT license](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/LICENSE),
  [config template](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/config_templates/conf.default.yaml),
  [`x_tts` engine](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/src/open_llm_vtuber/tts/x_tts.py),
  [`pyproject.toml`](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/pyproject.toml),
  [English quick start](https://github.com/Open-LLM-VTuber/open-llm-vtuber.github.io/blob/main/i18n/en/docusaurus-plugin-content-docs/current/quick-start.md),
  and [web UI language fallback](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web/blob/main/src/renderer/src/i18n.ts)
- [Hugging Face speech-to-speech README](https://github.com/huggingface/speech-to-speech/blob/main/README.md)
- [Pipecat README](https://github.com/pipecat-ai/pipecat/blob/main/README.md)
- [Open WebUI README](https://github.com/open-webui/open-webui/blob/main/README.md)
  and [license](https://github.com/open-webui/open-webui/blob/main/LICENSE)
- [RealtimeVoiceChat README](https://github.com/KoljaB/RealtimeVoiceChat/blob/main/README.md)
- [LiraVtuber README](https://github.com/Rukafuu/LiraVtuber/blob/main/README.md)
  and [MIT license](https://github.com/Rukafuu/LiraVtuber/blob/main/LICENSE)
- [Hyori README](https://github.com/JSNrepo/live2d-Live-Assistant/blob/main/README.md)
  and [MIT license](https://github.com/JSNrepo/live2d-Live-Assistant/blob/main/LICENSE)
- [OpenVoiceOS core README](https://github.com/OpenVoiceOS/ovos-core/blob/dev/README.md)
- [Leon README](https://github.com/leon-ai/leon/blob/develop/README.md)
- [OpenClaw Desktop Assistant MVP README](https://github.com/andyhuo520/openclaw-assistant-mvp/blob/main/README.md)
- [Mycroft Core repository](https://github.com/MycroftAI/mycroft-core)
