# Continuous integration

The repository includes issue templates and a lightweight CI check. The workflow
file is kept here because publishing with a GitHub OAuth token that lacks the
`workflow` scope is rejected by GitHub, even when the rest of the push is
allowed.

To enable CI, either:

1. Add `.github/workflows/ci.yml` through the GitHub web UI, or
2. Refresh the CLI token with the workflow scope:
   `gh auth refresh -h github.com -s workflow`, then push the file.

Workflow:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Byte-compile the app
        run: python -m compileall -q rocky_desktop_app.py rocky_eyes.py rocky_say.py app.py

      - name: Ensure restricted voice assets are not tracked
        run: |
          if git ls-files | grep -E '^assets/.*\.(wav|pth|mp3|safetensors|ckpt)$'; then
            echo "Restricted voice assets must not be committed." >&2
            exit 1
          fi

      - name: Ensure core docs exist
        run: |
          test -f README.md
          test -f PROJECT.md
          test -f LICENSE
          test -f NOTICE.md
          test -f docs/REALTIME_PLAN.md
```

Local equivalent:

```sh
python3.11 -m compileall -q rocky_desktop_app.py rocky_eyes.py rocky_say.py app.py
git ls-files | grep -E '^assets/.*\.(wav|pth|mp3|safetensors|ckpt)$' && exit 1 || true
```
