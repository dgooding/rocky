#!/usr/bin/env bash
# macOS setup for the Rocky desktop app.
# This script installs Python dependencies only; it does not download voice
# assets. See assets/README.md and scripts/restore_assets.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=== Rocky desktop setup ==="
echo

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "ERROR: python3.11 not found." >&2
  echo "  Install with: brew install python@3.11" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found." >&2
  echo "  Install with: brew install ffmpeg" >&2
  exit 1
fi

if [[ ! -d venv ]]; then
  echo "Creating venv (Python 3.11)..."
  python3.11 -m venv venv
fi

echo "Installing dependencies from requirements.txt..."
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt

echo
echo "=== Dependencies installed ==="
echo
echo "Next steps:"
echo "  1. Download the large files that are not in git (voice files, models):"
echo "       ./scripts/fetch_assets.sh"
echo "     (or copy your own backup: ./scripts/restore_assets.sh /path/to/your/rocky-assets)"
echo "  2. Start the voice server:"
echo "       COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start"
echo "  3. Build and launch the app, then say \"hey Rocky\":"
echo "       ./scripts/make_app.sh"
echo "       open -n ./Rocky.app"
echo
echo "Voice assets are for personal, non-commercial use only. See NOTICE.md."
