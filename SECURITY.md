# Security and privacy

## Reporting

This is a personal desktop app, not a hosted service. If you find a security
issue, open a private security advisory on GitHub rather than a public issue.

## Default posture

- No telemetry, analytics, or remote logging.
- Ollama and XTTS bind to `127.0.0.1` by default.
- No cloud calls unless you configure a hosted brain or cloud voice.
- Camera access is explicit in the current build; a planned always-on mode must
  be opt-in and visibly indicated.

## Secrets

- Do not commit API keys. Use `BRAIN_API_KEY` or a local `.env` that is
  git-ignored.
- Do not paste keys into issues, logs, or screenshots.
- The app logs transcripts; treat `~/Library/Logs/Rocky.log` and `logs/` as
  private.

## Voice assets

The voice model and reference audio are not distributed with this repository.
They are restricted to personal, non-commercial use. See
[`NOTICE.md`](NOTICE.md).

## Model downloads

Ollama models and Coqui XTTS weights are downloaded by their respective tools.
Review their licenses before use. XTTS v2 / Coqui TTS is non-commercial under the
CPML.

## Camera

- The camera LED is controlled by macOS.
- Do not add hidden capture. If you add always-on vision, add a visible
  indicator and a one-key off switch.
- Keep the cheap detector local; send frames to a cloud VLM only with explicit
  consent.
