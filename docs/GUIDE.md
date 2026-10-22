#!/usr/bin/env python3
"""
rocky_say — Text-to-speech using Rocky's cloned voice (Project Hail Mary)

Transforms input text into Rocky's speech patterns ("text GAN"), then
synthesizes audio using XTTS v2 voice cloning. Rocky is the Eridian alien
from Andy Weir's Project Hail Mary, voiced by James Ortiz in the 2026 film.

His speech patterns are distinctive: dropped articles, simplified grammar,
word tripling for emphasis ("good good good", "bad bad bad"), and the
signature "question" suffix on all interrogatives.

This tool does two things:
  1. Transforms your text into Rocky-speak (rule-based, no API needed)
  2. Synthesizes speech in Rocky's cloned voice via XTTS v2

Blog: https://pedsidian.pedramamini.com/Claude/Blog/2026-03-28-rocky-voice-clone
Gist: https://gist.github.com/pedramamini/fa5f6ef99dae79add220188419230642

USAGE
-----
    rocky_say "Hello, how are you doing today?"
    rocky_say -s 1.0 "Slower, normal TTS speed"
    rocky_say -m rvc "Try the RVC model instead"
    echo "some text" | rocky_say
    rocky_say -f file.txt -s 1.2
    rocky_say -o output.wav "Save to file"
    rocky_say --raw "Skip text transform, speak exactly this"
    rocky_say --transform-only "Just show Rocky-speak, no audio"
    rocky_say --server start|stop|status

VOICE MODELS
------------
    yourtts (default, recommended)
        YourTTS zero-shot voice cloning. Best quality in A/B/C/D testing
        across longer passages. Fast generation (~2s). Uses the full 2:10
        of scrubbed training audio as reference.

    xtts
        XTTS v2 zero-shot voice cloning. Good quality, slower (~3s with
        persistent server, ~22s cold start).

    rvc
        XTTS v2 generation followed by RVC v2 voice conversion using a
        dedicated trained model (300 epochs, 55MB). Adds Rocky voice
        characteristics on top of XTTS output. Requires RVC repo +
        Python 3.10 venv (not portable).

    openvoice
        OpenVoice v2 tone color transfer. MeloTTS generates base speech,
        then Rocky's tone color is applied. Slowest (~40-80s on CPU).
        Requires OpenVoice venv.

SETUP (one-time, ~5 minutes)
----------------------------
    # 1. Install system dependencies
    brew install ffmpeg python@3.11

    # 2. Create virtual environment
    python3.11 -m venv ~/.rocky_say/venv
    source ~/.rocky_say/venv/bin/activate
    pip install TTS 'transformers==4.44.0' 'torch==2.5.1' 'torchaudio==2.5.1'
    deactivate

    # 3. Download Rocky's voice (22MB training audio)
    mkdir -p ~/.rocky_say
    curl -L -o ~/.rocky_say/rocky_training_audio_scrubbed.wav \\
        https://pedramamini.com/dropbox/rocky_training_audio_scrubbed.wav

    # 4. Install the script
    chmod +x rocky_say
    sudo ln -sf $(pwd)/rocky_say /usr/local/bin/rocky_say

    # 5. (Optional) Start persistent server for fast generation (~3s vs ~22s)
    rocky_say --server start

TEXT TRANSFORM EXAMPLES
-----------------------
    "I don't understand"           → "No understand"
    "What do you mean?"            → "What mean, question?"
    "That's really amazing!"       → "That very amaze amaze amaze!"
    "This approach is terrible"    → "This approach bad bad bad"
    "Goodbye my friend"            → "See you later. But I no see you later my friend"

HOW IT WAS BUILT
----------------
    1. Extracted 11 dialogue scenes from the Project Hail Mary film (MKV)
    2. Isolated vocals from music/effects using Meta's demucs
    3. Transcribed with OpenAI Whisper
    4. Speaker diarization via pyannote to separate Rocky from Grace
    5. Manual review pass to tag 84 clean Rocky segments
    6. Two rounds of audio scrubbing to remove non-Rocky artifacts
    7. Text style corpus extracted from Andy Weir's novel (269 lines)
    8. Rule-based text transform derived from corpus analysis
    9. Voice cloned via Coqui TTS XTTS v2 (zero-shot, no fine-tuning)

DOWNLOADS
---------
    Voice:  https://pedramamini.com/dropbox/rocky_training_audio_scrubbed.wav
    RVC v2: https://pedramamini.com/dropbox/rocky_voice.pth (trained model, 55MB)

LICENSE
-------
    Rocky's voice design is the IP of the film's production company.
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
ROCKY_DIR = os.path.expanduser("~/.rocky_say")
VENV_DIR = os.path.join(ROCKY_DIR, "venv")
REFERENCE = os.path.join(ROCKY_DIR, "rocky_training_audio_scrubbed.wav")
RVC_MODEL = os.path.join(ROCKY_DIR, "rocky_voice.pth")
RVC_DIR = os.path.expanduser("~/Downloads/hail_mary_audio/rvc")
RVC_VENV = os.path.expanduser("~/Downloads/hail_mary_audio/.venv-rvc")
SERVER_PORT = 59720
SERVER_PID = "/tmp/rocky_server.pid"

# Also check legacy location
if not os.path.exists(REFERENCE):
    alt = os.path.expanduser("~/Downloads/hail_mary_audio/output/rocky_training_audio_scrubbed.wav")
    if os.path.exists(alt):
        REFERENCE = alt


# === TEXT TRANSFORM: English → Rocky-speak ===

# Articles and auxiliaries to strip
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

# Emphasis words that get Rocky's triple repetition
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

# Common phrase replacements
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

    # Work sentence by sentence
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result = []

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue

        # Detect if it's a question
        is_question = s.endswith('?')

        # Apply phrase-level replacements first
        for pattern, replacement in PHRASE_MAP:
            s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)

        # Expand contractions
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
                continue  # drop articles
            elif lower in AUXILIARIES and len(new_words) > 0:
                # Drop auxiliaries mid-sentence but keep at start
                continue
            else:
                new_words.append(w)

        s = ' '.join(new_words)

        # Clean up double spaces
        s = re.sub(r'\s+', ' ', s).strip()

        # Replace ? with ", question?" (Rocky's style) — skip if already has it
        if is_question and 'question' not in s.lower():
            s = s.rstrip('?').strip() + ', question?'
        elif is_question:
            # Already has "question" — just ensure it ends with ?
            s = s.rstrip('?').strip() + '?'

        # Capitalize first word
        if s:
            s = s[0].upper() + s[1:]

        result.append(s)

    output = ' '.join(result)

    # Final cleanup
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
    except:
        pass

    print("Starting Rocky TTS server (model load takes ~17s)...", file=sys.stderr)

    # Write server script inline
    server_script = f'''
import os, sys, tempfile, time, json
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from http.server import HTTPServer, BaseHTTPRequestHandler
REFERENCE = "{REFERENCE}"
print("Loading XTTS v2...", flush=True)
t0 = time.time()
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
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
            self.wfile.write(b'{{"status":"ok","voice":"rocky"}}')
        else: self.send_response(404); self.end_headers()

HTTPServer(("127.0.0.1",{SERVER_PORT}), H).serve_forever()
'''
    # Find python3.11 in venv or system
    python = os.path.join(VENV_DIR, "bin", "python3")
    if not os.path.exists(python):
        python = "python3.11"

    proc = subprocess.Popen(
        [python, "-c", server_script],
        stdout=open("/tmp/rocky_server.log", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with open(SERVER_PID, "w") as f:
        f.write(str(proc.pid))

    import urllib.request
    for _ in range(60):
        import time; time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=2)
            print("Server ready.", file=sys.stderr)
            return
        except:
            pass
    print("Server failed to start. Check /tmp/rocky_server.log", file=sys.stderr)


def server_stop():
    if os.path.exists(SERVER_PID):
        pid = open(SERVER_PID).read().strip()
        try:
            os.kill(int(pid), 9)
        except:
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
    except:
        print("Server not running. Start with: rocky_say --server start")


# === TTS GENERATION ===

def generate_via_server(text):
    """Try the persistent server (fast path ~3s)."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=1)
    except:
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
    except:
        return None


def generate_standalone(text):
    """Standalone XTTS generation (slow path ~22s)."""
    python = os.path.join(VENV_DIR, "bin", "python3")
    if not os.path.exists(python):
        python = "python3.11"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name

    escaped_text = text.replace('"', '\\"')
    script = f'''
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
tts.tts_to_file(text="""{escaped_text}""", speaker_wav="{REFERENCE}", language="en", file_path="{tmp}")
'''
    result = subprocess.run([python, "-c", script], capture_output=True)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        with open(tmp, "rb") as f:
            wav = f.read()
        os.unlink(tmp)
        return wav
    return None


def generate_yourtts(text):
    """Generate with YourTTS zero-shot voice cloning (best quality in A/B testing)."""
    python = os.path.join(VENV_DIR, "bin", "python3")
    if not os.path.exists(python):
        python = "python3.11"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name

    escaped_text = text.replace('"', '\\"')
    script = f'''
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/your_tts")
tts.tts_to_file(text="""{escaped_text}""", speaker_wav="{REFERENCE}", language="en", file_path="{tmp}")
'''
    result = subprocess.run([python, "-c", script], capture_output=True)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        with open(tmp, "rb") as f:
            wav = f.read()
        os.unlink(tmp)
        return wav
    return None


def generate_openvoice(text):
    """Generate with OpenVoice v2 tone color transfer."""
    openvoice_venv = os.path.expanduser("~/Downloads/hail_mary_audio/.venv-openvoice")
    ov_python = os.path.join(openvoice_venv, "bin", "python3")
    if not os.path.exists(ov_python):
        print(f"Error: OpenVoice venv not found at {openvoice_venv}", file=sys.stderr)
        return None

    # OpenVoice SE extractor needs shorter reference (max ~30s)
    ref_30s = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-i", REFERENCE, "-t", "30",
                    "-acodec", "pcm_s16le", ref_30s], capture_output=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_tmp = f.name

    ckpt_dir = os.path.expanduser("~/.cache/openvoice/models--myshell-ai--OpenVoiceV2/snapshots")
    # Find the snapshot directory
    if os.path.exists(ckpt_dir):
        snapshots = [d for d in os.listdir(ckpt_dir) if os.path.isdir(os.path.join(ckpt_dir, d))]
        if snapshots:
            ckpt_dir = os.path.join(ckpt_dir, snapshots[0])

    escaped_text = text.replace('"', '\\"')
    script = f'''
import os, torch
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
from openvoice.api import ToneColorConverter
from openvoice import se_extractor
from melo.api import TTS as MeloTTS

melo = MeloTTS(language="EN", device="cpu")
spk_id = list(melo.hps.data.spk2id.values())[0]
melo.tts_to_file("""{escaped_text}""", spk_id, "/tmp/ov_base_tmp.wav", speed=1.0)

converter = ToneColorConverter("{ckpt_dir}/converter/config.json", device="cpu")
converter.load_ckpt("{ckpt_dir}/converter/checkpoint.pth")

target_se, _ = se_extractor.get_se("{ref_30s}", converter, vad=False)
source_se, _ = se_extractor.get_se("/tmp/ov_base_tmp.wav", converter, vad=False)

converter.convert(audio_src_path="/tmp/ov_base_tmp.wav", src_se=source_se, tgt_se=target_se, output_path="{output_tmp}")
os.unlink("/tmp/ov_base_tmp.wav")
'''
    result = subprocess.run([ov_python, "-c", script], capture_output=True)
    os.unlink(ref_30s)

    if os.path.exists(output_tmp) and os.path.getsize(output_tmp) > 0:
        with open(output_tmp, "rb") as f:
            wav = f.read()
        os.unlink(output_tmp)
        return wav
    return None


def generate_rvc(text):
    """Generate via XTTS first, then apply RVC voice conversion for higher quality."""
    if not os.path.exists(RVC_MODEL):
        print(f"Error: RVC model not found at {RVC_MODEL}", file=sys.stderr)
        print("Download from: https://pedramamini.com/dropbox/rocky_voice.pth", file=sys.stderr)
        return None

    if not os.path.exists(RVC_DIR):
        print(f"Error: RVC repo not found at {RVC_DIR}", file=sys.stderr)
        return None

    # Step 1: Generate base audio with XTTS
    xtts_wav = generate_via_server(text)
    if not xtts_wav:
        xtts_wav = generate_standalone(text)
    if not xtts_wav:
        print("Error: XTTS generation failed (needed as input for RVC)", file=sys.stderr)
        return None

    # Save XTTS output to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(xtts_wav)
        xtts_tmp = f.name

    # Step 2: Apply RVC voice conversion
    rvc_python = os.path.join(RVC_VENV, "bin", "python3")
    if not os.path.exists(rvc_python):
        print(f"Error: RVC venv not found at {RVC_VENV}", file=sys.stderr)
        os.unlink(xtts_tmp)
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        rvc_tmp = f.name

    rvc_script = f'''
import sys, os
os.environ["weight_root"] = "{ROCKY_DIR}"
os.environ["index_root"] = "{RVC_DIR}/logs/rocky_voice"
os.environ["rmvpe_root"] = "{RVC_DIR}/assets/rmvpe"
os.chdir("{RVC_DIR}")
from infer.modules.vc.modules import VC
from configs.config import Config
config = Config()
vc = VC(config)
vc.get_vc("rocky_voice.pth")
info, opt = vc.vc_single(0, "{xtts_tmp}", 0, None, "rmvpe", "", "", 0.75, 3, 0, 0.25, 0.33)
import soundfile as sf
import numpy as np
audio = opt[1]
if audio.ndim == 1:
    audio = audio.reshape(-1, 1)
sf.write("{rvc_tmp}", audio, opt[0])
'''
    result = subprocess.run([rvc_python, "-c", rvc_script], capture_output=True)
    os.unlink(xtts_tmp)

    if os.path.exists(rvc_tmp) and os.path.getsize(rvc_tmp) > 0:
        with open(rvc_tmp, "rb") as f:
            wav = f.read()
        os.unlink(rvc_tmp)
        return wav

    stderr = result.stderr.decode() if result.stderr else ""
    print(f"Error: RVC conversion failed", file=sys.stderr)
    if stderr:
        # Show just the actual error, not all the warnings
        for line in stderr.split('\n'):
            if 'Error' in line or 'error' in line or 'Traceback' in line:
                print(f"  {line}", file=sys.stderr)
    return None


def apply_speed(wav_data, speed):
    """Apply speed adjustment via ffmpeg atempo filter."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_data)
        in_path = f.name
    out_path = in_path + ".speed.wav"
    subprocess.run(
        ["/opt/homebrew/bin/ffmpeg", "-y", "-i", in_path, "-filter:a", f"atempo={speed}", out_path],
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
    """Play WAV audio."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_data)
        path = f.name
    if sys.platform == "darwin":
        subprocess.run(["/usr/bin/afplay", path])
    elif sys.platform.startswith("linux"):
        subprocess.run(["aplay", path])
    os.unlink(path)


# === MAIN ===

def main():
    parser = argparse.ArgumentParser(
        prog="rocky_say",
        description="Rocky voice TTS — Project Hail Mary",
        epilog="Tip: rocky_say --server start  (loads model once, ~3s per call after)",
    )
    parser.add_argument("text", nargs="?", help="Text to speak")
    parser.add_argument("-s", "--speed", type=float, default=1.5,
                        help="Playback speed (default: 1.5, range: 0.5-2.0)")
    parser.add_argument("-m", "--model", choices=["yourtts", "xtts", "rvc", "openvoice"], default="yourtts",
                        help="Voice model: yourtts (default), xtts, rvc, openvoice")
    parser.add_argument("-f", "--file", help="Read text from file")
    parser.add_argument("-o", "--output", help="Save WAV to file instead of playing")
    parser.add_argument("--raw", action="store_true",
                        help="Skip Rocky text transform, speak text as-is")
    parser.add_argument("--transform-only", action="store_true",
                        help="Only transform text to Rocky-speak, no TTS")
    parser.add_argument("--server", choices=["start", "stop", "status"],
                        help="Manage persistent TTS server")

    args = parser.parse_args()

    # Server management
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

    # Transform text to Rocky-speak (unless --raw)
    if not args.raw:
        original = text
        text = rocky_transform(text)
        if text != original:
            print(f"Rocky: {text}", file=sys.stderr)

    # Transform-only mode
    if args.transform_only:
        print(text)
        return

    # Check reference audio exists
    if not os.path.exists(REFERENCE):
        print(f"Error: Voice reference not found at {REFERENCE}", file=sys.stderr)
        print(f"Place rocky_training_audio_scrubbed.wav in {ROCKY_DIR}/", file=sys.stderr)
        sys.exit(1)

    # Generate audio
    if args.model == "yourtts":
        wav = generate_yourtts(text)
    elif args.model == "rvc":
        wav = generate_rvc(text)
    elif args.model == "openvoice":
        wav = generate_openvoice(text)
    else:  # xtts
        wav = generate_via_server(text)
        if not wav:
            wav = generate_standalone(text)
    if not wav:
        print("Error: TTS generation failed", file=sys.stderr)
        sys.exit(1)

    # Apply speed
    if args.speed != 1.0:
        wav = apply_speed(wav, args.speed)

    # Output
    if args.output:
        with open(args.output, "wb") as f:
            f.write(wav)
        print(args.output)
    else:
        play_audio(wav)


if __name__ == "__main__":
    main()