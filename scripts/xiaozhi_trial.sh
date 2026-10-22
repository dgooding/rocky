#!/usr/bin/env bash
# Reuse-first trial: py-xiaozhi (desktop client) + xiaozhi-esp32-server
# (self-hosted backend), wired to Rocky's local Ollama models and Rocky's XTTS
# voice server. Nothing is installed inside this repository; everything goes
# into $ROCKY_TRIAL_DIR (default: ~/rocky-xiaozhi-trial).
#
# Usage: ./scripts/xiaozhi_trial.sh setup|server|client|doctor
# See docs/XIAOZHI_TRIAL.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="$ROOT/scripts/xiaozhi"
TRIAL="${ROCKY_TRIAL_DIR:-$HOME/rocky-xiaozhi-trial}"
SERVER_REPO="$TRIAL/xiaozhi-esp32-server"
SERVER_DIR="$SERVER_REPO/main/xiaozhi-server"
SERVER_VENV="$TRIAL/server-venv"
CLIENT_DIR="$TRIAL/py-xiaozhi"
CLIENT_DATA="$TRIAL/xiaozhi-data"
REPORT="$TRIAL/report.txt"

SENSEVOICE_URL="https://modelscope.cn/models/iic/SenseVoiceSmall/resolve/master/model.pt"
OLLAMA_URL="http://127.0.0.1:11434"
VOICE_URL="http://127.0.0.1:59720"
OTA_URL="http://127.0.0.1:8003/xiaozhi/ota/"
BASE_MODEL="qwen3-coder:latest"
BRAIN_ALIAS="rocky-brain"
VISION_MODEL="qwen2.5vl:3b"

usage() {
  cat <<EOF
Usage: ./scripts/xiaozhi_trial.sh <command>

  setup    install both projects, the speech model, and the rocky-brain alias
  server   start Rocky's voice server (if needed) and the xiaozhi server
  client   start the py-xiaozhi desktop app (add "--mode cli" for terminal)
  doctor   check every service, time the brain and voice, write report.txt

Install directory: $TRIAL  (override with ROCKY_TRIAL_DIR)
EOF
}

say()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 not found. $2"; }
up()   { curl -fsS --max-time 3 "$1" >/dev/null 2>&1; }

# Homebrew's libopus is not on the default dlopen path on Apple Silicon.
use_brew_libs() {
  if command -v brew >/dev/null 2>&1; then
    export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
  fi
}

fetch() {
  local url="$1" dir="$2"
  if [[ -d "$dir/.git" ]]; then
    git -C "$dir" pull --ff-only
  else
    git clone --depth 1 "$url" "$dir"
  fi
}

has_model() { ollama list 2>/dev/null | awk -v m="$1" 'NR>1 && $1==m {f=1} END {exit !f}'; }

cmd_setup() {
  [[ "$(uname -s)" == "Darwin" ]] || warn "This kit targets macOS; continuing anyway."
  need git  "Install with: xcode-select --install"
  need curl ""
  need brew "Install Homebrew from https://brew.sh"
  need uv   "Install with: brew install uv"
  need ollama "Install from https://ollama.com and start it."
  up "$OLLAMA_URL/api/tags" || die "Ollama is not running at $OLLAMA_URL. Start it, then re-run setup."

  for pkg in opus ffmpeg portaudio; do
    brew list --versions "$pkg" >/dev/null 2>&1 || { say "brew install $pkg"; brew install "$pkg"; }
  done

  mkdir -p "$TRIAL"
  say "Fetching xiaozhi-esp32-server (MIT) into $SERVER_REPO"
  fetch https://github.com/xinnan-tech/xiaozhi-esp32-server.git "$SERVER_REPO"
  say "Fetching py-xiaozhi (MIT) into $CLIENT_DIR"
  fetch https://github.com/huangjunsen0406/py-xiaozhi.git "$CLIENT_DIR"

  say "Installing server dependencies (Python 3.10)"
  [[ -x "$SERVER_VENV/bin/python" ]] || uv venv --python 3.10 "$SERVER_VENV"
  uv pip install --python "$SERVER_VENV/bin/python" -r "$SERVER_DIR/requirements.txt"

  local model="$SERVER_DIR/models/SenseVoiceSmall/model.pt"
  if [[ ! -s "$model" ]]; then
    say "Downloading SenseVoiceSmall speech model (~900 MB)"
    curl -fL --retry 3 -o "$model.part" "$SENSEVOICE_URL"
    mv "$model.part" "$model"
  fi

  mkdir -p "$SERVER_DIR/data"
  cp "$KIT/server.config.yaml" "$SERVER_DIR/data/.config.yaml"
  say "Server config: $SERVER_DIR/data/.config.yaml (rewritten on every setup)"

  say "Installing py-xiaozhi with GUI extras"
  (cd "$CLIENT_DIR" && uv sync --extra gui)

  mkdir -p "$CLIENT_DATA/config"
  if [[ ! -f "$CLIENT_DATA/config/config.json" ]]; then
    cp "$KIT/client.config.json" "$CLIENT_DATA/config/config.json"
  fi
  say "Client config: $CLIENT_DATA/config/config.json"

  has_model "$BASE_MODEL"   || { say "ollama pull $BASE_MODEL";   ollama pull "$BASE_MODEL"; }
  has_model "$VISION_MODEL" || { say "ollama pull $VISION_MODEL"; ollama pull "$VISION_MODEL"; }
  # The server calls Ollama's /v1 API, which cannot set num_ctx per request;
  # qwen3-coder's 262k default context would use ~45 GB. Pin 8k in an alias.
  if ! has_model "$BRAIN_ALIAS:latest"; then
    say "Creating $BRAIN_ALIAS ($BASE_MODEL with num_ctx 8192)"
    local mf
    mf="$(mktemp)"
    printf 'FROM %s\nPARAMETER num_ctx 8192\n' "$BASE_MODEL" > "$mf"
    ollama create "$BRAIN_ALIAS" -f "$mf"
    rm -f "$mf"
  fi

  echo
  say "Setup complete."
  echo "    Terminal 1:  ./scripts/xiaozhi_trial.sh server"
  echo "    Terminal 2:  ./scripts/xiaozhi_trial.sh client"
}

ensure_voice() {
  if up "$VOICE_URL/health"; then
    say "Rocky voice server is running."
    return
  fi
  if [[ -x "$ROOT/venv/bin/python" ]] && ls "$ROOT"/assets/*.wav >/dev/null 2>&1; then
    say "Starting Rocky voice server (first load ~20 s)"
    (cd "$ROOT" && COQUI_TOS_AGREED=1 ./venv/bin/python rocky_say.py --server start)
  else
    warn "Rocky voice server is not running and cannot start automatically."
    warn "It needs ./setup.sh and the voice assets (see assets/README.md). Replies will be silent."
  fi
}

cmd_server() {
  [[ -d "$SERVER_DIR" ]] || die "Not installed. Run: ./scripts/xiaozhi_trial.sh setup"
  ensure_voice
  use_brew_libs
  cd "$SERVER_DIR"
  say "xiaozhi server: ws://127.0.0.1:8000/xiaozhi/v1/  OTA: $OTA_URL  (Ctrl+C to stop)"
  exec "$SERVER_VENV/bin/python" app.py
}

cmd_client() {
  [[ -d "$CLIENT_DIR" ]] || die "Not installed. Run: ./scripts/xiaozhi_trial.sh setup"
  up "$OTA_URL" || warn "xiaozhi server not reachable at $OTA_URL. Start it with: ./scripts/xiaozhi_trial.sh server"
  use_brew_libs
  export XIAOZHI_DATA_DIR="$CLIENT_DATA"
  cd "$CLIENT_DIR"
  exec uv run python main.py "$@"
}

probe() {
  if up "$2"; then echo "ok    $1  ($2)"; else echo "DOWN  $1  ($2)"; fi
}

cmd_doctor() {
  mkdir -p "$TRIAL"
  {
    echo "Rocky xiaozhi trial report  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host: $(uname -srm)"
    if command -v sw_vers >/dev/null 2>&1; then
      echo "macOS: $(sw_vers -productVersion)"
    fi
    echo "chip: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)"
    echo "trial dir: $TRIAL"
    echo
    for d in "$ROOT" "$SERVER_REPO" "$CLIENT_DIR"; do
      if [[ -d "$d/.git" ]]; then
        echo "commit $(basename "$d"): $(git -C "$d" rev-parse --short HEAD)"
      else
        echo "commit $(basename "$d"): not installed"
      fi
    done
    echo
    for c in brew uv ollama ffmpeg; do
      printf '%-7s %s\n' "$c" "$(command -v "$c" || echo missing)"
    done
    echo
    probe "Ollama        " "$OLLAMA_URL/api/tags"
    probe "Rocky voice   " "$VOICE_URL/health"
    probe "xiaozhi server" "$OTA_URL"
    echo
    for m in "$BRAIN_ALIAS:latest" "$VISION_MODEL"; do
      if has_model "$m"; then echo "model ok      $m"; else echo "model MISSING $m"; fi
    done
    local sv="$SERVER_DIR/models/SenseVoiceSmall/model.pt"
    if [[ -s "$sv" ]]; then
      echo "SenseVoiceSmall: $(du -h "$sv" | cut -f1)"
    else
      echo "SenseVoiceSmall: MISSING"
    fi
    echo
    if up "$OLLAMA_URL/api/tags" && has_model "$BRAIN_ALIAS:latest"; then
      # First call may include a model load; the second is the warm number.
      for run in cold warm; do
        local t
        t="$(curl -fs -o /dev/null -w '%{time_starttransfer}' \
          -d "{\"model\":\"$BRAIN_ALIAS\",\"prompt\":\"Say hello.\",\"stream\":true,\"options\":{\"num_predict\":8}}" \
          "$OLLAMA_URL/api/generate")" || t=fail
        echo "brain first byte ($run): ${t}s"
      done
    fi
    if up "$VOICE_URL/health"; then
      local t
      t="$(curl -fs -o /dev/null -w '%{time_total}' -H 'Content-Type: application/json' \
        -d '{"text":"Hello friend."}' "$VOICE_URL/")" || t=fail
      echo "Rocky voice, 'Hello friend.': ${t}s"
    fi
  } 2>&1 | tee "$REPORT"
  echo
  say "Saved $REPORT"
}

case "${1:-}" in
  setup)  cmd_setup ;;
  server) cmd_server ;;
  client) shift; cmd_client "$@" ;;
  doctor) cmd_doctor ;;
  -h|--help|"") usage ;;
  *) usage; exit 1 ;;
esac
