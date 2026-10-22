#!/usr/bin/env python3
"""
rocky_say — Text-to-speech using Rocky's cloned voice (Project Hail Mary)

Transforms input text into Rocky's speech patterns, then synthesizes audio
using XTTS v2 / YourTTS voice cloning. Rocky is the Eridian alien from
Andy Weir's Project Hail Mary, voiced by James Ortiz in the 2026 film.

USAGE
-----
    python rocky_say.py "Hello, how are you doing today?"
    python rocky_say.py -s 1.0 "Slower, normal TTS speed"
    python rocky_say.py -m xtts "Try XTTS instead of YourTTS"
    python rocky_say.py -o output.wav "Save to file"
    python rocky_say.py --raw "Skip text transform, speak exactly this"
    python rocky_say.py --transform-only "Just show Rocky-speak, no audio"
    python rocky_say.py --server start|stop|status
    echo "some text" | python rocky_say.py

VOICE MODELS
------------
    yourtts (default, recommended)
        YourTTS zero-shot voice cloning. Best quality, ~2s generation.

    xtts
        XTTS v2 zero-shot voice cloning. Good quality, ~3s with server,
        ~22s cold start.

    rvc
        XTTS v2 + RVC v2 voice conversion (trained model, 300 epochs).

CREDITS
-------
    Original script & voice assets by Pedram Amini
    Blog: https://pedsidian.pedramamini.com/Claude/Blog/2026-03-28-rocky-voice-clone
    Gist: https://gist.github.com/pedramamini/fa5f6ef99dae79add220188419230642

LICENSE
-------
    Rocky's voice design is IP of the film's production company.
    XTTS v2 is under Coqui's non-commercial CPML license.
    This tool is for personal, non-commercial use only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

# === CONFIGURATION ===
# Project-local paths (everything lives in this repo folder)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
# Rocky's voice reference. XTTS conditions best on a short, clean sample, so a
# trimmed 15s clip is preferred when present. ROCKY_REFERENCE overrides both.
FULL_REFERENCE  = os.path.join(ASSETS_DIR, "rocky_training_audio_scrubbed.wav")
SHORT_REFERENCE = os.path.join(ASSETS_DIR, "rocky_ref_15s.wav")
REFERENCE = (
    os.environ.get("ROCKY_REFERENCE")
    or (SHORT_REFERENCE if os.path.exists(SHORT_REFERENCE) else FULL_REFERENCE)
)
RVC_MODEL   = os.path.join(ASSETS_DIR, "rocky_voice.pth")
VENV_DIR    = os.path.join(SCRIPT_DIR, "venv")
LOGS_DIR    = os.path.join(SCRIPT_DIR, "logs")
SERVER_PORT = 59720
SERVER_PID  = os.path.join(LOGS_DIR, "rocky_server.pid")

os.makedirs(LOGS_DIR, exist_ok=True)

# Detect OS
IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"

def _venv_python():
    """Return the Python executable inside the local venv."""
    if IS_WINDOWS:
        p = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        p = os.path.join(VENV_DIR, "bin", "python3")
    return p if os.path.exists(p) else sys.executable


# === TEXT TRANSFORM: English → Rocky-speak ===

ARTICLES = {'a', 'an', 'the'}
AUXILIARIES = {'is', 'are', 'was', 'were', 'will', 'would', 'should', 'could',
               'do', 'does', 'did', 'has', 'have', 'had', 'am', 'been', 'being'}
CONTRACTIONS = {
    "i'm": "I",
    "i've": "I",
    "i'll": "I",
    "i'd": "I",
    "you're": "you",
    "you've": "you",
    "you'll": "you",
    "we're": "we",
    "we've": "we",
    "we'll": "we",
    "they're": "they",
    "they've": "they",
    "they'll": "they",
    "he's": "he",
    "she's": "she",
    "it's": "it",
    "that's": "that",
    "there's": "there",
    "what's": "what",
    "don't": "no",
    "doesn't": "no",
    "didn't": "no",
    "can't": "no can",
    "cannot": "no can",
    "won't": "no will",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "no have",
    "hasn't": "no have",
    "hadn't": "no have",
}

EMPHASIS_MAP = {
    'amazing': 'amaze amaze amaze',
    'wonderful': 'amaze amaze amaze',
    'incredible': 'amaze amaze amaze',
    'fantastic': 'amaze amaze amaze',
    'excellent': 'good good good',
    'great': 'good good good',
    'terrible': 'bad bad bad',
    'awful': 'bad bad bad',
    'horrible': 'bad bad bad',
    'happy': 'happy happy happy',
    'excited': 'happy happy happy',
    'sad': 'sad sad sad',
    'upset': 'sad sad sad',
    'angry': 'angry angry angry',
    'furious': 'angry angry angry',
    'confused': 'confuse confuse confuse',
    'scared': 'scared scared scared',
    'afraid': 'scared scared scared',
    'dangerous': 'danger danger danger',
    'important': 'important',
    'interesting': 'interesting',
    'understand': 'understand',
    'absolutely': 'yes yes yes',
    'definitely': 'yes yes yes',
    'certainly': 'yes yes yes',
    'impossible': 'no can. No no no',
    'unfortunately': 'sad.',
}

PHRASE_MAP = [
    (r"i don'?t understand", "no understand"),
    (r"i do not understand", "no understand"),
    (r"i don'?t know", "I not know"),
    (r"what do you mean", "what mean"),
    (r"what does that mean", "what mean"),
    (r"what does .+ mean", "what mean"),
    (r"i need a word for", "need word."),
    (r"i'?m going to", "I"),
    (r"going to ", ""),
    (r"want to ", "want "),
    (r"need to ", "need "),
    (r"have to ", "must "),
    (r"try to ", "try "),
    (r"able to ", "can "),
    (r"in order to ", "to "),
    (r"because of ", "because "),
    (r"a lot of ", "many "),
    (r"lots of ", "many "),
    (r"kind of ", ""),
    (r"sort of ", ""),
    (r"right now", "now"),
    (r"at this point", "now"),
    (r"at the moment", "now"),
    (r"as well", "also"),
    (r"in addition", "also"),
    (r"however", "but"),
    (r"therefore", "so"),
    (r"nevertheless", "but"),
    (r"furthermore", "also"),
    (r"approximately", "about"),
    (r"regarding", "about"),
    (r"concerning", "about"),
    (r"it seems like", "maybe"),
    (r"it appears that", "maybe"),
    (r"i think that", "I think"),
    (r"i believe that", "I think"),
    (r"you know what", ""),
    (r"to be honest", ""),
    (r"basically", ""),
    (r"actually", ""),
    (r"literally", ""),
    (r"really", "very"),
    (r"extremely", "very very"),
    (r"incredibly", "very very"),
    (r"goodbye", "see you later. But I no see you later"),
]


def rocky_transform(text):
    """Transform English text into Rocky's speech patterns."""
    if not text or not text.strip():
        return text

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result = []

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue

        is_question = s.endswith('?')

        for pattern, replacement in PHRASE_MAP:
            s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)

        words = s.split()
        new_words = []
        for w in words:
            lower = w.lower().rstrip('.,!?;:')
            punct = w[len(lower):] if len(w) > len(lower) else ''

            if lower in CONTRACTIONS:
                new_words.append(CONTRACTIONS[lower] + punct)
            elif lower in EMPHASIS_MAP:
                new_words.append(EMPHASIS_MAP[lower] + punct)
            elif lower in ARTICLES:
                continue
            elif lower in AUXILIARIES and len(new_words) > 0:
                continue
            else:
                new_words.append(w)

        s = ' '.join(new_words)
        s = re.sub(r'\s+', ' ', s).strip()

        if is_question and 'question' not in s.lower():
            s = s.rstrip('?').strip() + ', question?'
        elif is_question:
            s = s.rstrip('?').strip() + '?'

        if s:
            s = s[0].upper() + s[1:]

        result.append(s)

    output = ' '.join(result)
    output = re.sub(r'\s+', ' ', output)
    output = re.sub(r'\s+([.,!?])', r'\1', output)
    output = re.sub(r'\.\.+', '.', output)

    return output.strip()


# === SERVER MANAGEMENT ===

def server_start():
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=2)
        print("Server already running.", file=sys.stderr)
        return
    except Exception:
        pass

    print("Starting Rocky TTS server (model load takes ~17s)...", file=sys.stderr)

    ref_escaped = REFERENCE.replace("\\", "/")
    server_script = f'''
import os, sys, tempfile, time, json
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from http.server import HTTPServer, BaseHTTPRequestHandler
REFERENCE = r"{REFERENCE}"
print("Loading XTTS v2...", flush=True)
t0 = time.time()
from TTS.api import TTS
import numpy as np, soundfile as sf
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
# Condition on the reference once, then reuse the latents for every request.
gpt_cond, spk_emb = tts.synthesizer.tts_model.get_conditioning_latents(audio_path=[REFERENCE])
SPEED = float(os.environ.get("ROCKY_SPEED", "1.25"))
print(f"Ready in {{time.time()-t0:.0f}}s on port {SERVER_PORT}", flush=True)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length",0))).decode()
        try: text = json.loads(body).get("text","")
        except: text = body
        if not text.strip():
            self.send_response(400); self.end_headers(); return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f: tmp = f.name
        try:
            out = tts.synthesizer.tts_model.inference(
                text, "en", gpt_cond, spk_emb, speed=SPEED)
            arr = out["wav"]
            arr = arr.detach().cpu().numpy() if hasattr(arr, "detach") else np.asarray(arr)
            sf.write(tmp, arr, 24000)
        except Exception:
            tts.tts_to_file(text=text, speaker_wav=REFERENCE, language="en", file_path=tmp)
        with open(tmp,"rb") as f: wav = f.read()
        os.unlink(tmp)
        self.send_response(200)
        self.send_header("Content-Type","audio/wav")
        self.end_headers()
        self.wfile.write(wav)
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(b\'{{"status":"ok","voice":"rocky"}}\')
        else: self.send_response(404); self.end_headers()

HTTPServer(("127.0.0.1",{SERVER_PORT}), H).serve_forever()
'''
    python = _venv_python()
    log_path = os.path.join(LOGS_DIR, "rocky_server.log")

    kwargs = {}
    if IS_WINDOWS:
        # Windows: use DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
        import ctypes
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        [python, "-c", server_script],
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    with open(SERVER_PID, "w") as f:
        f.write(str(proc.pid))

    import urllib.request, time
    for _ in range(60):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=2)
            print("Server ready.", file=sys.stderr)
            return
        except Exception:
            pass
    print(f"Server failed to start. Check {log_path}", file=sys.stderr)


def server_stop():
    if os.path.exists(SERVER_PID):
        pid = open(SERVER_PID).read().strip()
        try:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            else:
                os.kill(int(pid), 9)
        except Exception:
            pass
        os.unlink(SERVER_PID)
        print("Server stopped.", file=sys.stderr)
    else:
        print("No server running.", file=sys.stderr)


def server_status():
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=2)
        print(f"Server running on port {SERVER_PORT}")
        print(resp.read().decode())
    except Exception:
        print("Server not running. Start with: python rocky_say.py --server start")


# === TTS GENERATION ===

def generate_via_server(text):
    """Try the persistent XTTS server (fast path ~3s)."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=1)
    except Exception:
        return None

    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{SERVER_PORT}",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.read()
    except Exception:
        return None


def generate_standalone(text):
    """Standalone XTTS v2 generation (slow path ~22s cold start)."""
    python = _venv_python()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name

    escaped_text = text.replace('"', '\\"').replace("\\", "\\\\")
    ref_escaped = REFERENCE.replace("\\", "\\\\")
    script = f'''
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
tts.tts_to_file(text="""{escaped_text}""", speaker_wav=r"{REFERENCE}", language="en", file_path=r"{tmp}")
'''
    subprocess.run([python, "-c", script], capture_output=True)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        with open(tmp, "rb") as f:
            wav = f.read()
        os.unlink(tmp)
        return wav
    return None


def generate_yourtts(text):
    """Generate with YourTTS zero-shot voice cloning (recommended)."""
    python = _venv_python()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name

    escaped_text = text.replace('"', '\\"').replace("\\", "\\\\")
    script = f'''
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/your_tts")
tts.tts_to_file(text="""{escaped_text}""", speaker_wav=r"{REFERENCE}", language="en", file_path=r"{tmp}")
'''
    subprocess.run([python, "-c", script], capture_output=True)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        with open(tmp, "rb") as f:
            wav = f.read()
        os.unlink(tmp)
        return wav
    return None


def generate_rvc(text):
    """XTTS v2 + RVC v2 voice conversion."""
    if not os.path.exists(RVC_MODEL):
        print(f"Error: RVC model not found at {RVC_MODEL}", file=sys.stderr)
        return None

    # Step 1: Generate base XTTS audio
    wav = generate_via_server(text) or generate_standalone(text)
    if not wav:
        print("Error: XTTS generation failed (needed as RVC input)", file=sys.stderr)
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav)
        xtts_tmp = f.name

    python = _venv_python()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        rvc_tmp = f.name

    rvc_script = f'''
import sys, os
os.environ["weight_root"] = r"{ASSETS_DIR}"
os.environ["index_root"] = r"{ASSETS_DIR}"
os.environ["rmvpe_root"] = r"{ASSETS_DIR}"
from infer.modules.vc.modules import VC
from configs.config import Config
config = Config()
vc = VC(config)
vc.get_vc("rocky_voice.pth")
info, opt = vc.vc_single(0, r"{xtts_tmp}", 0, None, "rmvpe", "", "", 0.75, 3, 0, 0.25, 0.33)
import soundfile as sf
audio = opt[1]
if audio.ndim == 1:
    audio = audio.reshape(-1, 1)
sf.write(r"{rvc_tmp}", audio, opt[0])
'''
    result = subprocess.run([python, "-c", rvc_script], capture_output=True)
    os.unlink(xtts_tmp)

    if os.path.exists(rvc_tmp) and os.path.getsize(rvc_tmp) > 0:
        with open(rvc_tmp, "rb") as f:
            wav = f.read()
        os.unlink(rvc_tmp)
        return wav

    stderr = result.stderr.decode() if result.stderr else ""
    print("Error: RVC conversion failed", file=sys.stderr)
    for line in stderr.split('\n'):
        if any(k in line for k in ('Error', 'error', 'Traceback')):
            print(f"  {line}", file=sys.stderr)
    return None


def apply_speed(wav_data, speed):
    """Apply speed adjustment via ffmpeg atempo filter."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_data)
        in_path = f.name
    out_path = in_path + ".speed.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", in_path, "-filter:a", f"atempo={speed}", out_path],
        capture_output=True,
    )
    os.unlink(in_path)
    if os.path.exists(out_path):
        with open(out_path, "rb") as f:
            result = f.read()
        os.unlink(out_path)
        return result
    return wav_data


def play_audio(wav_data):
    """Play WAV audio (cross-platform)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_data)
        path = f.name
    try:
        if IS_WINDOWS:
            # Use Windows Media Player via PowerShell (no extra deps needed)
            subprocess.run(
                ["powershell", "-c",
                 f"(New-Object Media.SoundPlayer '{path}').PlaySync()"],
                check=True,
            )
        elif IS_MAC:
            subprocess.run(["afplay", path])
        else:
            subprocess.run(["aplay", path])
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# === MAIN ===

def main():
    parser = argparse.ArgumentParser(
        prog="rocky_say",
        description="Rocky voice TTS — Project Hail Mary",
        epilog="Tip: --server start  loads the model once for ~3s/call instead of ~22s",
    )
    parser.add_argument("text", nargs="?", help="Text to speak")
    parser.add_argument("-s", "--speed", type=float, default=1.5,
                        help="Playback speed (default: 1.5, range: 0.5-2.0)")
    parser.add_argument("-m", "--model", choices=["yourtts", "xtts", "rvc"], default="yourtts",
                        help="Voice model: yourtts (default), xtts, rvc")
    parser.add_argument("-f", "--file", help="Read text from file")
    parser.add_argument("-o", "--output", help="Save WAV to file instead of playing")
    parser.add_argument("--raw", action="store_true",
                        help="Skip Rocky text transform, speak text as-is")
    parser.add_argument("--transform-only", action="store_true",
                        help="Only show Rocky-speak transformation, no audio")
    parser.add_argument("--server", choices=["start", "stop", "status"],
                        help="Manage persistent TTS server (for faster xtts generation)")

    args = parser.parse_args()

    if args.server:
        {"start": server_start, "stop": server_stop, "status": server_status}[args.server]()
        return

    # Get input text
    text = args.text
    if args.file:
        with open(args.file) as f:
            text = f.read()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    if not text:
        parser.print_help()
        sys.exit(1)

    text = text.strip()

    if not args.raw:
        original = text
        text = rocky_transform(text)
        if text != original:
            print(f"Rocky: {text}", file=sys.stderr)

    if args.transform_only:
        print(text)
        return

    if not os.path.exists(REFERENCE):
        print(f"Error: Voice reference not found at {REFERENCE}", file=sys.stderr)
        sys.exit(1)

    # Generate audio
    if args.model == "yourtts":
        wav = generate_yourtts(text)
    elif args.model == "rvc":
        wav = generate_rvc(text)
    else:  # xtts
        wav = generate_via_server(text) or generate_standalone(text)

    if not wav:
        print("Error: TTS generation failed", file=sys.stderr)
        sys.exit(1)

    if args.speed != 1.0:
        wav = apply_speed(wav, args.speed)

    if args.output:
        with open(args.output, "wb") as f:
            f.write(wav)
        print(args.output)
    else:
        play_audio(wav)


if __name__ == "__main__":
    main()
