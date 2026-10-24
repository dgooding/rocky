#!/usr/bin/env bash
# Set up Rocky's isolated local Drama 3 voice runtime and British reference.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$HOME/.cache/rocky"
VENV="$CACHE/mlx-audio-venv"
REVISION="1ac1b2108b63c2ef5bade463a121569363e293ce"
MODEL="mlx-community/fish-audio-drama-3-4bit"
REFERENCE="$CACHE/drama3-british-female-reference.wav"
REFERENCE_SOURCE="$CACHE/drama3-british-female-reference-24k.wav"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v python3.11 >/dev/null 2>&1 || die "Install Python 3.11 first (brew install python@3.11)."
command -v ffmpeg >/dev/null 2>&1 || die "Install ffmpeg first (brew install ffmpeg)."
[[ -x "$ROOT/venv/bin/python" ]] || die "Run ./setup.sh first to install Rocky's Kokoro reference voice."

mkdir -p "$CACHE"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3.11 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install "mlx-audio==0.6.1"

printf 'Downloading %s (about 22 GiB; cached after the first run)...\n' "$MODEL"
"$VENV/bin/hf" download "$MODEL" --revision "$REVISION"

REFERENCE_RATE=""
if [[ -s "$REFERENCE" ]]; then
  REFERENCE_RATE="$(
    ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate \
      -of default=noprint_wrappers=1:nokey=1 "$REFERENCE"
  )"
fi

if [[ ! -s "$REFERENCE" || "$REFERENCE_RATE" != "44100" ]]; then
  printf 'Creating a generic British female reference with local Kokoro...\n'
  ROOT="$ROOT" REFERENCE_SOURCE="$REFERENCE_SOURCE" "$ROOT/venv/bin/python" - <<'PY'
import os
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

text = "Hello there. I'm glad you're here. Take your time, and tell me what's on your mind."
chunks = [audio for _, _, audio in KPipeline(lang_code="b")(
    text, voice="bf_emma", speed=1.0
)]
if not chunks:
    raise RuntimeError("Kokoro produced no voice-reference audio")
reference = Path(os.environ["REFERENCE_SOURCE"])
reference.parent.mkdir(parents=True, exist_ok=True)
sf.write(reference, np.concatenate(chunks), 24000, format="WAV", subtype="PCM_16")
print(f"Created {reference}")
PY
  ffmpeg -hide_banner -loglevel error -y -i "$REFERENCE_SOURCE" \
    -ar 44100 -ac 1 -c:a pcm_s16le "$REFERENCE"
  rm -f "$REFERENCE_SOURCE"
fi

echo
echo "Drama 3 local voice setup is ready."
echo "Default engine: ./venv/bin/python rocky_desktop_app.py"
echo "Fallback voice: ./venv/bin/python rocky_desktop_app.py --tts-engine kokoro"
