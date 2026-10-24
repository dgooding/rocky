#!/usr/bin/env bash
# Download everything large that is not in git, so a fresh clone can run.
#
#   ./scripts/fetch_assets.sh            # voice files + Ollama models + speech models
#   ./scripts/fetch_assets.sh --yes      # skip the license prompt
#   ./scripts/fetch_assets.sh --assets-only
#
# Voice files come from the links the upstream author publishes in
# docs/GUIDE.md; this repository never hosts them. Nothing that is already
# present is downloaded or overwritten again.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$ROOT/assets"
BASE_URL="https://pedramamini.com/dropbox"
OLLAMA_MODELS=("qwen3-coder:latest" "qwen2.5vl:3b")

YES=0
ASSETS_ONLY=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    --assets-only) ASSETS_ONLY=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

cat <<'EOF'
Rocky's voice files and the XTTS v2 model are for personal, non-commercial use
only. Rocky's voice is the intellectual property of the Project Hail Mary film
production; the voice files are CC BY-NC 4.0 and XTTS v2 is under the Coqui
Public Model License (non-commercial). Do not redistribute or commit them.
See NOTICE.md.
EOF
if [[ "$YES" -ne 1 ]]; then
  read -r -p "Download them for personal use? [y/N] " answer
  [[ "$answer" == [yY]* ]] || die "Cancelled. Nothing was downloaded."
fi

command -v curl >/dev/null 2>&1 || die "curl not found."
mkdir -p "$ASSETS"

# name  expected-bytes  magic-bytes  description
fetch_asset() {
  local name="$1" size="$2" magic="$3" what="$4" dst="$ASSETS/$1"
  if [[ -s "$dst" ]]; then
    printf '  keep   %-36s (already present)\n' "$name"
    return
  fi
  say "Downloading $name ($what)"
  curl -fL --retry 3 --progress-bar -o "$dst.part" "$BASE_URL/$name"
  if [[ "$(head -c "${#magic}" "$dst.part")" != "$magic" ]]; then
    rm -f "$dst.part"
    die "$name is not the expected file type; the download link may have changed."
  fi
  local got
  got="$(wc -c < "$dst.part" | tr -d ' ')"
  [[ "$got" == "$size" ]] || warn "$name is $got bytes; expected $size. Keeping it, but check the source."
  mv "$dst.part" "$dst"
}

fetch_asset rocky_training_audio_scrubbed.wav 22908200 "RIFF" "2:10 voice clip, 23 MB"
fetch_asset rocky_voice.pth 57578452 "PK" "RVC voice model, 58 MB, optional"

# XTTS clones best from a short, clean clip. Make one if the original 15 s
# reference is not already restored from a backup.
if [[ ! -s "$ASSETS/rocky_ref_15s.wav" ]]; then
  if command -v ffmpeg >/dev/null 2>&1; then
    say "Making rocky_ref_15s.wav (first 15 s of speech)"
    ffmpeg -loglevel error -y -i "$ASSETS/rocky_training_audio_scrubbed.wav" \
      -af "silenceremove=start_periods=1:start_threshold=-40dB" -t 15 -ac 1 -ar 22050 \
      "$ASSETS/rocky_ref_15s.wav"
  else
    warn "ffmpeg not found; skipping rocky_ref_15s.wav. Rocky will use the full clip."
  fi
else
  printf '  keep   %-36s (already present)\n' "rocky_ref_15s.wav"
fi

if [[ "$ASSETS_ONLY" -ne 1 ]]; then
  if command -v ollama >/dev/null 2>&1 && curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    for model in "${OLLAMA_MODELS[@]}"; do
      if ollama list 2>/dev/null | awk -v m="$model" 'NR>1 && $1==m {f=1} END {exit !f}'; then
        printf '  keep   %-36s (already pulled)\n' "$model"
      else
        say "ollama pull $model"
        ollama pull "$model"
      fi
    done
  else
    warn "Ollama is not running; skipping: ollama pull ${OLLAMA_MODELS[*]}"
  fi

  PY="$ROOT/venv/bin/python"
  if [[ -x "$PY" ]]; then
    say "Speech-to-text model (faster-whisper base.en, ~150 MB, cached once)"
    "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8')"
    say "Voice model (XTTS v2, ~1.8 GB, cached once)"
    COQUI_TOS_AGREED=1 "$PY" -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')" >/dev/null
    say "Default local voice (Drama 3 MLX, ~22 GiB, isolated from ./venv)"
    "$ROOT/scripts/setup_drama3.sh"
  else
    warn "No ./venv yet; run ./setup.sh, then re-run this script to cache speech, voice, and Drama 3 models."
  fi
fi

echo
missing=0
for name in rocky_training_audio_scrubbed.wav rocky_ref_15s.wav rocky_voice.pth; do
  if [[ -s "$ASSETS/$name" ]]; then
    printf '  ok     %-36s %s\n' "$name" "$(du -h "$ASSETS/$name" | cut -f1)"
  elif [[ "$name" == rocky_training_audio_scrubbed.wav ]]; then
    printf '  MISSING %-35s (required)\n' "$name"
    missing=1
  else
    printf '  skip   %-36s (optional)\n' "$name"
  fi
done
echo
echo "These files are git-ignored. Never commit or redistribute them."
exit "$missing"
