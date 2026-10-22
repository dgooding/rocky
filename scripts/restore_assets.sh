#!/usr/bin/env bash
# Restore the private Rocky voice assets from a directory or a .tar.gz backup.
# This script never downloads anything.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/assets"
FORCE=0
SOURCE=""

usage() {
  cat <<'EOF'
Usage: ./scripts/restore_assets.sh [--force] <directory-or-archive>

Copies these files into ./assets/:
  rocky_ref_15s.wav
  rocky_training_audio_scrubbed.wav
  rocky_voice.pth

If no path is given, the script looks for:
  ../archives/rocky-tts-2026-10-21.tar.gz
  ./archives/rocky-tts-2026-10-21.tar.gz

The voice assets are restricted to personal, non-commercial use. Do not
redistribute them. See NOTICE.md.
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --force) FORCE=1 ;;
    *) SOURCE="$arg" ;;
  esac
done

if [[ -z "$SOURCE" ]]; then
  for candidate in \
    "$ROOT/../archives/rocky-tts-2026-10-21.tar.gz" \
    "$ROOT/archives/rocky-tts-2026-10-21.tar.gz"
  do
    if [[ -f "$candidate" ]]; then
      SOURCE="$candidate"
      break
    fi
  done
fi

if [[ -z "$SOURCE" ]]; then
  usage
  echo
  echo "ERROR: no source given and no default archive found." >&2
  exit 1
fi

if [[ ! -e "$SOURCE" ]]; then
  echo "ERROR: source not found: $SOURCE" >&2
  exit 1
fi

mkdir -p "$DEST"
TMP=""
cleanup() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }
trap cleanup EXIT

copy_one() {
  local name="$1" src="$2" dst="$DEST/$1"
  if [[ -s "$dst" && "$FORCE" -ne 1 ]]; then
    echo "  keep   $name (already present; use --force to replace)"
    return
  fi
  cp -f "$src" "$dst"
  echo "  copy   $name"
}

if [[ -d "$SOURCE" ]]; then
  for name in rocky_ref_15s.wav rocky_training_audio_scrubbed.wav rocky_voice.pth; do
    if [[ -f "$SOURCE/$name" ]]; then
      copy_one "$name" "$SOURCE/$name"
    else
      echo "  warn   $name not found in $SOURCE" >&2
    fi
  done
elif [[ -f "$SOURCE" && "$SOURCE" == *.tar.gz ]]; then
  TMP="$(mktemp -d "${TMPDIR:-/tmp}/rocky-assets.XXXXXX")"
  tar -xzf "$SOURCE" -C "$TMP"
  for name in rocky_ref_15s.wav rocky_training_audio_scrubbed.wav rocky_voice.pth; do
    found="$(find "$TMP" -type f -name "$name" -print -quit)"
    if [[ -n "$found" ]]; then
      copy_one "$name" "$found"
    else
      echo "  warn   $name not found in $SOURCE" >&2
    fi
  done
else
  echo "ERROR: expected a directory or a .tar.gz: $SOURCE" >&2
  exit 1
fi

echo
missing=0
for name in rocky_ref_15s.wav rocky_training_audio_scrubbed.wav rocky_voice.pth; do
  if [[ -s "$DEST/$name" ]]; then
    printf '  ok     %-36s %s\n' "$name" "$(du -h "$DEST/$name" | cut -f1)"
  else
    printf '  MISSING %-35s\n' "$name"
    missing=1
  fi
done

echo
echo "Voice assets are for personal, non-commercial use only."
echo "Rocky's voice is the IP of the Project Hail Mary film production."
echo "Do not redistribute these files. See NOTICE.md and LICENSE."
exit "$missing"
