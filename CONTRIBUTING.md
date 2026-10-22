# Contributing

Thanks for taking a look. This is a personal, local-first desk companion, but
issues and focused pull requests are welcome.

## Before you start

- Read [`PROJECT.md`](PROJECT.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- Check [`docs/ROADMAP.md`](docs/ROADMAP.md) for current priorities.
- For a large change, open an issue first so we can agree on the approach.

## Asset policy

Do **not** commit voice assets, model weights, or large generated audio:

```text
assets/*.wav
assets/*.pth
assets/*.mp3
logs/
venv/
Rocky.app/
archives/
```

The voice assets are restricted by the upstream license and the film IP. See
[`NOTICE.md`](NOTICE.md).

## Development setup

```sh
./setup.sh
./scripts/restore_assets.sh /path/to/your/rocky-assets
ollama pull qwen3-coder
ollama pull qwen2.5vl:3b
COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start
```

## Checks

```sh
python3.11 -m compileall -q rocky_desktop_app.py rocky_eyes.py rocky_say.py app.py
./venv/bin/python rocky_eyes.py --selftest shots/eyes
./venv/bin/python rocky_desktop_app.py --selftest
```

If you change latency-sensitive code, include before/after measurements from
[`docs/LATENCY.md`](docs/LATENCY.md)'s method. Report p50 and p95, not a single
run.

## Style

- Python 3.11, standard library plus the pinned dependencies.
- Keep the local path working without API keys.
- Do not add a cloud dependency as the only path.
- Prefer small, composable functions over a framework rewrite.
- Keep comments about *why*, not *what*.
- Do not add telemetry.

## Pull requests

- One logical change per PR.
- Explain the user-visible effect and how you tested it.
- Include screenshots for eye/UI changes.
- Note any new model, asset, or license implications.
- Do not include secrets, API keys, or transcripts from real conversations.

## License

By contributing, you agree that your contribution is licensed under the same
CC BY-NC 4.0 terms as the project, and that you have the right to submit it.
