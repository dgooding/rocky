# Open-source app survey

Checked 2026-10-22 against project READMEs, repository file listings, and
licenses. This is a reuse-first shortlist, not an endorsement: features and
latency stated by project authors are claims until tested on Rocky's hardware.

## Recommendation

Do not start by building another voice-agent stack. First run a short proof of
fit on:

1. **[py-xiaozhi](https://github.com/huangjunsen0406/py-xiaozhi)** as the
   editable, cross-platform desktop-app candidate.
2. **[Xiaozhi Desktop](https://xiaozhi.junsen.online)** as a ready-to-run
   interaction/UX comparison. Its public
   [release repository](https://github.com/huangjunsen0406/xiaozhi-desktop-release)
   exposes a download site, not the desktop client's source code; do not treat
   it as reusable source unless a source repository and license are confirmed.
3. **[Open WebUI](https://github.com/open-webui/open-webui)** as a local-Ollama
   voice/video interface benchmark, not a Rocky desktop-app replacement.

If none passes the acceptance checks below, adapt a mature voice framework such
as [Pipecat](https://github.com/pipecat-ai/pipecat) rather than reimplementing
audio capture, turn detection, streaming, and cancellation from scratch. The
current real-time architecture is a fallback proposal, not a decision to build
everything in-house.

## Candidates

| Project | Ready-made capabilities in its public docs | Fit and limitations for Rocky | Recommendation |
|---|---|---|---|
| [py-xiaozhi](https://github.com/huangjunsen0406/py-xiaozhi) | MIT-licensed Python app/framework; PySide6/QML GUI and CLI; async audio pipeline, WebSocket/MQTT, vision, plugins, offline Sherpa-ONNX wake word; README lists macOS, Windows, and Linux. | Closest editable desktop foundation found. Its README also calls for a stable internet connection for AI/online features and does not establish a fully local Ollama brain or Rocky-voice path. The stated sub-20 ms processing is a project claim, not an independent end-to-end measurement. | **Test first as a source-based app.** Verify local-only operation, runtime/provider extension points, camera privacy, and audio interruption before choosing it. |
| [Xiaozhi Desktop](https://xiaozhi.junsen.online) | The related py-xiaozhi README describes an Electron desktop client with AEC, Live2D, floating windows, and Windows/macOS installers. | Appears closest to a ready-to-run voice/avatar experience. The public release repo found contains static download-site files rather than client source; its code license and backend/local-model fit were not established. | **Run as a black-box UX comparison only.** Do not copy or redistribute the client until source and license are verified. |
| [Open WebUI](https://github.com/open-webui/open-webui) | Self-hosted interface for Ollama and OpenAI-compatible APIs; PWA; voice/video calls with multiple STT and TTS backends. | Strong local-model and provider coverage, but it is a general AI UI rather than an animated desktop companion. Its current [license](https://github.com/open-webui/open-webui/blob/main/LICENSE) imposes branding-preservation conditions, so it is not a straightforward white-label Rocky UI. | **Use as a benchmark or personal tool**, not as the assumed rebrandable foundation. Review the exact license before any reuse. |
| [LiraVtuber](https://github.com/Rukafuu/LiraVtuber) | MIT-licensed, desktop-first Python assistant with voice, memory, GUI, Live2D/VTube Studio, multiple LLM/TTS providers, and tests. The repository was updated 2026-10-20. | Strong visual/character overlap, but the README targets Windows desktop. The documented voice/provider paths include hosted services and XTTS via Colab; a local Ollama path and macOS support were not established. It also includes broad PC automation, media, Discord, and WhatsApp features beyond Rocky's goal. | **Reference for UI/character patterns**, not a drop-in macOS/local-first replacement without a compatibility and scope review. |
| [Hyori / live2d-Live-Assistant](https://github.com/JSNrepo/live2d-Live-Assistant) | MIT-licensed Live2D voice companion; README describes Gemini Live streaming, barge-in, audio-reactive avatar, and an offline MiniCPM5 fallback. | Feature overlap is high, but the README also describes a large autonomous tool/agent system and cloud-first Gemini flow. The small project footprint and broad capabilities warrant a focused dependency, permission, and local-fallback review before adoption. | **Architecture reference only** for the voice/avatar experience; do not import the unrelated agent/remote-control surface. |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Open-source Python framework for streaming voice and multimodal agents; quickstart, CLI, service adapters, examples, and separate Pipecat UI components. | Not a complete desktop companion; adopting it still requires app/UI integration. It is already named in the existing plan and is more appropriate than inventing a new audio orchestration framework if a full app does not fit. | **Fallback integration framework**, not the first app to replace Rocky with. |
| [OpenVoiceOS](https://github.com/OpenVoiceOS/ovos-core) | Apache-2.0 voice-assistant platform with install tooling, skills, and persona/LLM plugins. | A voice-centric smart-speaker platform rather than a ready-made desktop character app. Its install and plugin model may be useful if Rocky shifts toward a general assistant platform. | **Not the closest fit** for the current on-screen companion. |

### Screened out as a foundation

- [OpenClaw Desktop Assistant MVP](https://github.com/andyhuo520/openclaw-assistant-mvp)
  is an Electron prototype, but its README says its data is simulated, Live2D is
  still planned, and the real OpenClaw API is not connected. No license file was
  found in the queried repository path.
- [Leon](https://github.com/leon-ai/leon) is MIT-licensed and privacy-aware, but
  its current `develop` branch README labels the 2.0 Developer Preview and
  describes an agent/tools/memory assistant; it is no longer primarily a
  classic voice-assistant implementation.
- [Mycroft Core](https://github.com/MycroftAI/mycroft-core) is archived and is
  not a sensible new foundation.

## Proof-of-fit checklist

Run the same small scenarios on Rocky and each runnable candidate; record
observations rather than relying on README latency claims:

1. **Platform:** builds/runs on the target Mac and obtains microphone/camera
   permission without a terminal-only workaround.
2. **Local-first:** completes a voice turn with the network disconnected using
   the existing local Ollama models; identify every feature that still sends
   audio, text, or images to a service.
3. **Voice and interaction:** accepts the available Rocky assets only where
   technically and legally permitted; measure speech-end to first audio and
   barge-in stop; check whether TTS can be stopped promptly.
4. **Echo/privacy:** demonstrate AEC or document a safe headphones-only
   fallback; verify the camera indicator and explicit/continuous capture mode.
5. **Integration:** determine whether the app can preserve Rocky's concise
   persona, seven eye emotions, typed input, one-shot look, and current local
   fallback without replacing working pieces unnecessarily.
6. **Maintainability and license:** inspect source availability, release
   cadence, tests, dependency/platform requirements, license obligations, and
   third-party model/asset terms.

**Decision gate:** reuse the app if it meets the required behavior and
constraints; adapt only the missing seams if it is close; otherwise reuse its
permissively licensed components or use Pipecat for the real-time audio path.
Do not migrate the whole app merely to obtain streaming audio.

## Licensing and privacy constraints

Rocky's own repository is CC BY-NC 4.0, and the Rocky character/voice assets
have separate rights constraints documented in `NOTICE.md` and `assets/README.md`.
A candidate app's MIT or Apache license does not grant rights to those assets or
to the Project Hail Mary character. Keep voice assets out of the repository and
confirm each provider's consent, data-retention, and usage terms before sending
audio to cloud services. For code reuse, preserve required notices and review
the complete upstream and dependency licenses.

## Sources

- [py-xiaozhi README](https://github.com/huangjunsen0406/py-xiaozhi/blob/main/README.md)
  and [MIT license](https://github.com/huangjunsen0406/py-xiaozhi/blob/main/LICENSE)
- [Xiaozhi Desktop site](https://xiaozhi.junsen.online) and
  [public release-site repository](https://github.com/huangjunsen0406/xiaozhi-desktop-release)
- [Open WebUI README](https://github.com/open-webui/open-webui/blob/main/README.md)
  and [license](https://github.com/open-webui/open-webui/blob/main/LICENSE)
- [LiraVtuber README](https://github.com/Rukafuu/LiraVtuber/blob/main/README.md)
  and [MIT license](https://github.com/Rukafuu/LiraVtuber/blob/main/LICENSE)
- [Hyori README](https://github.com/JSNrepo/live2d-Live-Assistant/blob/main/README.md)
  and [MIT license](https://github.com/JSNrepo/live2d-Live-Assistant/blob/main/LICENSE)
- [Pipecat README](https://github.com/pipecat-ai/pipecat/blob/main/README.md)
- [OpenVoiceOS core README](https://github.com/OpenVoiceOS/ovos-core/blob/dev/README.md)
- [Leon README](https://github.com/leon-ai/leon/blob/develop/README.md)
- [OpenClaw Desktop Assistant MVP README](https://github.com/andyhuo520/openclaw-assistant-mvp/blob/main/README.md)
- [Mycroft Core repository](https://github.com/MycroftAI/mycroft-core)
