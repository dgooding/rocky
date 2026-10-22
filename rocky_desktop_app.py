#!/usr/bin/env python3
"""
Rocky - a desk companion you can talk to.

Speak (or type) -> local speech-to-text -> local LLM -> Rocky's cloned voice,
with eyes that morph through emotion presets and bounce to the audio.

Everything runs on this machine; no cloud, no keys.

    python rocky_desktop_app.py                  # mic + Ollama brain
    python rocky_desktop_app.py --no-brain       # parrot: he repeats you back
    python rocky_desktop_app.py --selftest       # verify stt/ollama/eyes headless

Controls
    F1 (hold) / F2 (toggle)   talk
    type + Enter              same, by keyboard
    1-7                       force an emotion (when the input line is empty)
    Esc                       quit

Latency: the first sound of a reply takes STT + LLM + one sentence of XTTS
(~4-6s here). Sentences are generated ahead of playback, so a multi-sentence
reply does not stutter between sentences.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import numpy as np
import pygame
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import rocky_say as rocky
    import rocky_eyes
except ImportError:
    sys.exit("Run this inside your rocky-tts folder, next to rocky_say.py")

# --- look ---------------------------------------------------------------
W, H = 520, 300
BG = (8, 9, 14)
EYE = (247, 249, 252)
DIM = (104, 112, 126)
INK = (225, 230, 238)
WARN = (240, 150, 150)
REC = (255, 90, 90)
FPS = 60
FONT_NAME = "menlo,monospace"
HINT = "F1 hold / F2 toggle talk   -   F3 look   -   Esc quits"

LISTENING, THINKING, SPEAKING, IDLE = "LISTENING", "THINKING", "SPEAKING", "IDLE"
LABELS = {LISTENING: "listening...", THINKING: "thinking...", SPEAKING: "speaking"}

SYSTEM_PROMPT = (
    "You are Rocky, the Eridian engineer from Project Hail Mary: an alien who "
    "talks in short, blunt, warm sentences. You are endlessly curious and you "
    "love your human friend. Answer in ONE short sentence of at most 12 words, "
    "plain English, no lists, no markdown. Never mention being an AI or a model."
)

VISION_PROMPT = "In one short sentence, describe the main thing you see."

state = IDLE
subtitle = ""        # what is being said, or what was heard
note = ""            # transient line: errors, hints
amplitude = 0.0
eyes_emotion = "neutral"
jobs: queue.Queue = queue.Queue()
mic_recording = False


# --- audio --------------------------------------------------------------
def rms_envelope(wav_bytes: bytes, frame_ms: int = 30):
    data, rate = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    step = max(1, int(rate * frame_ms / 1000))
    env = [float(np.sqrt(np.mean(mono[i:i + step] ** 2)))
           for i in range(0, len(mono), step)]
    peak = max(env) if env else 0.0
    if peak <= 0:
        return [], rate, 0.0
    return [min(1.0, (v / peak) ** 0.6) for v in env], rate, len(mono) / rate


def play_with_envelope(wav_bytes: bytes) -> None:
    """Play a clip, publishing `amplitude` while it runs."""
    global amplitude, note
    env, rate, duration = rms_envelope(wav_bytes)
    if not env:
        note = "generated audio was empty"
        return
    clip = os.path.join(rocky.LOGS_DIR, "desk_last.wav")
    with open(clip, "wb") as f:
        f.write(wav_bytes)
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=rate, size=-16, channels=1, buffer=512)
        elif pygame.mixer.get_init()[0] != rate:
            pygame.mixer.quit()
            pygame.mixer.init(frequency=rate, size=-16, channels=1, buffer=512)
        chan = pygame.mixer.Sound(clip).play()
    except pygame.error as e:
        note = f"audio device error: {e}"
        print(f"[audio] {note}", file=sys.stderr)
        return

    frame = duration / len(env)
    t0 = time.monotonic()
    while chan.get_busy() and time.monotonic() - t0 < duration + 1.5:
        i = int((time.monotonic() - t0) / frame)
        amplitude = env[i] if 0 <= i < len(env) else 0.0
        time.sleep(0.016)
    amplitude = 0.0


# --- microphone ---------------------------------------------------------
class Mic:
    """16 kHz mono capture into memory between start() and stop()."""

    RATE = 16000

    def __init__(self) -> None:
        self.frames: list = []
        self.stream = None
        self.error = ""

    def start(self) -> bool:
        import sounddevice as sd
        self.frames, self.error = [], ""
        try:
            self.stream = sd.InputStream(samplerate=self.RATE, channels=1,
                                         dtype="float32", blocksize=1024,
                                         callback=self._cb)
            self.stream.start()
            return True
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            print(f"[mic] {e}", file=sys.stderr)
            return False

    def _cb(self, indata, frames, time_info, status):
        self.frames.append(indata.copy())

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
        if not self.frames:
            return None
        audio = np.concatenate(self.frames, axis=0).flatten()
        self.frames = []
        return audio


# --- camera -------------------------------------------------------------
class Camera:
    """Opens the webcam only when asked. No idle streaming, nothing uploaded.

    Frames are grabbed, JPEG-compressed at 640x480, and the device is closed
    again - so the camera light only comes on for the moment of a look.
    """

    def __init__(self, index: int = 0) -> None:
        self.index = index

    def snapshot(self, warmup: int = 5) -> bytes:
        import cv2
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            raise RuntimeError("camera unavailable - check System Settings > "
                               "Privacy & Security > Camera for your terminal")
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            frame = None
            for _ in range(warmup):          # first frames are dark while it wakes
                ok, got = cap.read()
                if ok:
                    frame = got
            if frame is None:
                raise RuntimeError("camera returned no frames")
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                raise RuntimeError("could not encode the frame")
            return buf.tobytes()
        finally:
            cap.release()


# --- speech to text -----------------------------------------------------
class Transcriber:
    def __init__(self, size: str = "base.en") -> None:
        self.size, self.model = size, None

    def _load(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            print(f"[stt] loading faster-whisper {self.size}...", file=sys.stderr)
            self.model = WhisperModel(self.size, device="cpu", compute_type="int8")
        return self.model

    def warm(self) -> None:
        """Load the model up front so the first thing you say is not slow."""
        try:
            self._load()
        except Exception as e:  # noqa: BLE001
            print(f"[stt] warm failed: {e}", file=sys.stderr)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) < 1600:
            return ""
        if float(np.abs(audio).max()) < 0.008:
            return ""
        segments, _ = self._load().transcribe(audio, language="en", beam_size=1,
                                              vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()


# --- brain --------------------------------------------------------------
class Brain:
    """A chat model behind a stream: local Ollama, or any OpenAI-compatible API.

    Note: on this machine the local models answer in ~0.1s warm, so a hosted
    model buys reply quality, not speech latency.
    """

    def __init__(self, model: str = "qwen3-coder:latest", host: str = "http://localhost:11434",
                 enabled: bool = True, api: str = "ollama", api_key: str = "",
                 vision_model: str = "qwen2.5vl:3b", context: int = 8192) -> None:
        self.model, self.host, self.enabled = model, host.rstrip("/"), enabled
        self.api, self.api_key = api, api_key
        self.vision_model = vision_model
        # qwen3-coder defaults to a 262k context (45 GB resident). Rocky only
        # ever sends a persona + one line, so 8k keeps it at ~19 GB.
        self.context = context
        self.checked = None

    def available(self) -> bool:
        if not self.enabled:
            return False
        if self.api in ("openai", "anthropic"):
            local = "localhost" in self.host or "127.0.0.1" in self.host
            self.checked = bool(self.api_key) or local
            return self.checked
        if self.checked is None:
            try:
                with urllib.request.urlopen(f"{self.host}/api/tags", timeout=2) as r:
                    models = [m["name"] for m in json.loads(r.read()).get("models", [])]
                self.checked = bool(models)
                if self.checked and self.model not in models:
                    print(f"[brain] {self.model} not pulled; have: {', '.join(models[:4])}",
                          file=sys.stderr)
            except Exception:  # noqa: BLE001
                self.checked = False
        return self.checked

    def _request(self, text: str):
        headers = {"Content-Type": "application/json"}
        if self.api == "openai":
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            body = json.dumps({
                "model": self.model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": text}],
                "stream": True,
                "max_tokens": 60,
                "temperature": 0.8,
            }).encode()
            return urllib.request.Request(f"{self.host}/chat/completions", data=body,
                                          headers=headers)
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": text}],
            "stream": True,
            "keep_alive": "30m",
            "options": {"num_predict": 45, "temperature": 0.8, "top_p": 0.9,
                        "num_ctx": self.context},
        }).encode()
        return urllib.request.Request(f"{self.host}/api/chat", data=body, headers=headers)

    def _vision_request(self, prompt: str, b64: str, stream: bool = True):
        headers = {"Content-Type": "application/json"}
        if self.api == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": self.vision_model,
                "max_tokens": 80,
                "system": VISION_PROMPT,
                "stream": True,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": "image/jpeg",
                                                 "data": b64}},
                    {"type": "text", "text": prompt}]}],
            }
            return urllib.request.Request(f"{self.host}/messages",
                                          data=json.dumps(body).encode(), headers=headers)
        if self.api == "openai":
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            body = {
                "model": self.vision_model,
                "stream": True,
                "max_tokens": 60,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": f"{VISION_PROMPT} {prompt}"},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
            }
            return urllib.request.Request(f"{self.host}/chat/completions",
                                          data=json.dumps(body).encode(), headers=headers)
        body = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": f"{VISION_PROMPT} {prompt}",
                          "images": [b64]}],
            "stream": stream,
            "options": {"num_predict": 60, "temperature": 0.1},
        }
        return urllib.request.Request(f"{self.host}/api/chat",
                                      data=json.dumps(body).encode(), headers=headers)

    def _deltas(self, resp):
        """Normalise Ollama / OpenAI / Anthropic streams into text deltas."""
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line:
                continue
            if self.api in ("openai", "anthropic"):
                if not line.startswith("data:"):
                    continue
                line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if self.api == "anthropic":
                    delta = (obj.get("delta", {}).get("text", "")
                             if obj.get("type") == "content_block_delta" else "")
                else:
                    try:
                        delta = obj["choices"][0].get("delta", {}).get("content") or ""
                    except (KeyError, IndexError):
                        delta = ""
            else:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("done"):
                    break
                delta = obj.get("message", {}).get("content", "")
            if delta:
                yield delta

    def stream(self, text: str):
        """Yield content deltas as they arrive."""
        if not self.available():
            return
        try:
            with urllib.request.urlopen(self._request(text), timeout=120) as r:
                yield from self._deltas(r)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[brain] {e}", file=sys.stderr)

    def vision_stream(self, prompt: str = "Describe the scene.", jpeg: bytes = b""):
        """Stream a description of one camera frame."""
        if not self.available() or not jpeg:
            return
        b64 = base64.b64encode(jpeg).decode()
        try:
            if self.api == "ollama":
                # Local vision models drop their first character when streamed,
                # and one short sentence gains nothing from it.
                with urllib.request.urlopen(self._vision_request(prompt, b64, stream=False),
                                            timeout=180) as r:
                    text = json.loads(r.read()).get("message", {}).get("content", "")
                if text.strip():
                    yield text.strip()
                return
            with urllib.request.urlopen(self._vision_request(prompt, b64), timeout=180) as r:
                yield from self._deltas(r)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("error", "")
            except Exception:  # noqa: BLE001
                pass
            print(f"[vision] HTTP {e.code}: {detail or e.reason}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[vision] {e}", file=sys.stderr)

    def vision(self, prompt: str, jpeg: bytes) -> str:
        return "".join(self.vision_stream(prompt, jpeg)).strip()

    def reply(self, text: str) -> str:
        return "".join(self.stream(text)).strip()

    def warm(self) -> None:
        """Load the model into memory so the first turn is not slower."""
        try:
            for _ in self.stream("hi"):
                break
        except Exception:  # noqa: BLE001
            pass


def split_sentences(text: str, limit: int = 150):
    """Sentence-ish chunks, each short enough to synthesize in one breath."""
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    out = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind(" ", 0, limit)
            cut = cut if cut > 40 else limit
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or [text]


# --- pipeline -----------------------------------------------------------
def warm_voice() -> None:
    """Make sure the XTTS server is resident before the first reply."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{rocky.SERVER_PORT}/health", timeout=2):
            return
    except Exception:  # noqa: BLE001
        pass
    print("[voice] starting XTTS server (one-time ~30s load)...", file=sys.stderr)
    rocky.server_start()


def synthesize(text: str):
    spoken = rocky.rocky_transform(text)
    wav = rocky.generate_via_server(spoken)
    if wav is None:
        warm_voice()
        wav = rocky.generate_via_server(spoken)
    return spoken, wav


def clause_split(sentence: str, first: bool = False, first_limit: int = 38,
                 limit: int = 90):
    """Split at commas so audio can start before the whole sentence exists.

    The opening chunk is held to a shorter limit, because that is the one the
    user is waiting on; later chunks can breathe for better prosody.
    """
    parts = re.split(r"(?<=,)\s+", sentence.strip())
    chunks, cur = [], ""
    for part in parts:
        trial = f"{cur} {part}".strip()
        cap = first_limit if (first and not chunks) else limit
        if cur and len(trial) > cap:
            chunks.append(cur)
            cur = part
        else:
            cur = trial
    if cur:
        chunks.append(cur)
    return chunks


def sentence_stream(brain: Brain, text: str):
    """Turn streamed LLM deltas into sentences, yielding each as it completes."""
    buf = ""
    for delta in brain.stream(text):
        buf += delta
        while True:
            m = re.search(r"[.!?](\s|$)", buf)
            if not m:
                break
            end = m.end()
            sentence, buf = buf[:end].strip(), buf[end:]
            if sentence:
                yield sentence
    if buf.strip():
        yield buf.strip()


def speak(sentences) -> None:
    """Synthesize ahead of playback; start talking as soon as clause 1 exists."""
    global state, subtitle, eyes_emotion
    prefetch: queue.Queue = queue.Queue(maxsize=3)
    said = ""

    def produce():
        try:
            first = True
            for sentence in sentences:
                for chunk in clause_split(sentence, first=first):
                    prefetch.put(synthesize(chunk))
                    first = False
        except Exception as e:  # noqa: BLE001
            print(f"[tts] {e}", file=sys.stderr)
        finally:
            prefetch.put(None)

    threading.Thread(target=produce, daemon=True).start()
    while True:
        item = prefetch.get()
        if item is None:
            break
        spoken, wav = item
        said = f"{said} {spoken}".strip()
        subtitle = said
        eyes_emotion = rocky_eyes.mood_for(said)
        if wav is None:
            continue
        state = SPEAKING
        play_with_envelope(wav)


def worker(transcriber: Transcriber, brain: Brain, camera) -> None:
    global state, subtitle, note, eyes_emotion
    while True:
        job = jobs.get()
        if job is None:
            return
        try:
            note = ""
            if job.get("look") is not None:
                state, eyes_emotion, subtitle = THINKING, "thinking", "looking..."
                if camera is None:
                    note, state = "camera disabled", IDLE
                    continue
                jpeg = camera.snapshot()
                try:      # keep what he saw, for when the answer makes no sense
                    with open(os.path.join(rocky.LOGS_DIR, "last_look.jpg"), "wb") as f:
                        f.write(jpeg)
                except OSError:
                    pass
                reply = brain.vision("Describe the scene.", jpeg)
                if not reply:
                    note, state = (f"no vision reply - try: ollama pull "
                                   f"{brain.vision_model}"), IDLE
                    continue
                print(f"[rocky] {reply}", file=sys.stderr)
                speak(split_sentences(reply))
                state = IDLE
                continue

            if job.get("audio") is not None:
                state, eyes_emotion = THINKING, "thinking"
                heard = transcriber.transcribe(job["audio"])
                if not heard:
                    note, state = "didn't catch that", IDLE
                    continue
                subtitle = "you: " + heard
                text = heard
            else:
                text = job["text"]

            state, eyes_emotion = THINKING, "thinking"
            if brain.available():
                print(f"[you] {text}", file=sys.stderr)
                speak(sentence_stream(brain, text))
            else:
                # echo mode: he repeats you back in his own grammar
                print(f"[rocky] {text}", file=sys.stderr)
                speak(split_sentences(text))
            state = IDLE
        except Exception as e:  # noqa: BLE001
            note, state = f"error: {e}", IDLE
            print(f"[worker] {e}", file=sys.stderr)


# --- drawing ------------------------------------------------------------
def render(screen, font, small, t, st, said, msg, typed, recording, eyes):
    screen.fill(BG)
    eyes.draw(screen, t, glow=0.5 + amplitude * 0.9)

    if st in LABELS:
        screen.blit(small.render(LABELS[st], True, DIM), (16, 16))
    if said:
        line = said if len(said) < 58 else said[:55] + "..."
        screen.blit(font.render(line, True, EYE), (16, H - 74))
    if msg:
        screen.blit(small.render(msg[:68], True, WARN), (16, H - 46))
    elif st == IDLE and not said:
        screen.blit(small.render(HINT, True, DIM), (16, H - 46))

    # recording dot
    if recording:
        pygame.draw.circle(screen, REC, (W - 24, 22), 7)

    pygame.draw.rect(screen, (14, 17, 24), pygame.Rect(0, H - 30, W, 30))
    caret = "_" if int(t * 2) % 2 else " "
    screen.blit(font.render(("> " + typed)[-64:] + caret, True, INK), (16, H - 25))
    pygame.display.flip()


def run(mic: Mic, transcriber: Transcriber, brain: Brain, camera=None) -> None:
    global state, mic_recording
    pygame.mixer.pre_init(24000, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption("Rocky")
    screen = pygame.display.set_mode((W, H))
    font = pygame.font.SysFont(FONT_NAME, 15)
    small = pygame.font.SysFont(FONT_NAME, 13)
    clock = pygame.time.Clock()
    eyes = rocky_eyes.Eyes()

    threading.Thread(target=worker, args=(transcriber, brain, camera), daemon=True).start()
    threading.Thread(target=warm_voice, daemon=True).start()
    threading.Thread(target=transcriber.warm, daemon=True).start()
    threading.Thread(target=brain.warm, daemon=True).start()

    typed, recording = "", False
    next_blink = time.monotonic() + random.uniform(1.5, 4)
    blink_until = 0.0
    next_gaze = time.monotonic() + 1.0
    gaze = (0.0, 0.0)
    running = True

    while running:
        now = time.monotonic()
        dt = clock.get_time() / 1000 or 1 / FPS

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_F1:
                    recording = mic.start()
                    mic_recording = recording
                elif e.key == pygame.K_F2:
                    if recording:
                        audio = mic.stop()
                        recording = False
                        jobs.put({"audio": audio})
                    else:
                        recording = mic.start()
                    mic_recording = recording
                elif e.key == pygame.K_F3 or (e.key == pygame.K_SPACE and not typed):
                    jobs.put({"look": True})
                elif e.key == pygame.K_RETURN and typed.strip():
                    jobs.put({"text": typed.strip()})
                    typed = ""
                elif e.key == pygame.K_BACKSPACE:
                    typed = typed[:-1]
                elif not typed and pygame.K_1 <= e.key <= pygame.K_7:
                    eyes.set_emotion(rocky_eyes.EMOTIONS[e.key - pygame.K_1])
                elif e.unicode and e.unicode.isprintable():
                    typed += e.unicode
            elif e.type == pygame.KEYUP and e.key == pygame.K_F1 and recording:
                audio = mic.stop()
                recording = False
                mic_recording = False
                jobs.put({"audio": audio})

        # emotion follows what the robot is doing
        if recording and state == IDLE:
            state = LISTENING
        if state == LISTENING:
            eyes.set_emotion("neutral")
        elif state == THINKING:
            eyes.set_emotion("thinking")
        elif state == IDLE and eyes.emotion != eyes_emotion:
            eyes.set_emotion(eyes_emotion)

        if blink_until and now > blink_until:
            blink_until = 0.0
            next_blink = now + random.uniform(1.8, 5.0)
        elif not blink_until and now > next_blink:
            blink_until = now + 0.13

        if now > next_gaze and state == IDLE:
            gaze = (random.uniform(-7, 7), random.uniform(-4, 4))
            next_gaze = now + random.uniform(1.6, 4.5)

        if state == LISTENING:
            g = (0.0, -3.0)
        elif state == THINKING:
            g = (0.0, -4.0)
        else:
            g = gaze

        eyes.update(dt, amp=amplitude, blink=bool(blink_until), t=now, gaze=g)
        render(screen, font, small, now, state, subtitle, note, typed, recording, eyes)
        clock.tick(FPS)

    jobs.put(None)
    pygame.quit()


# --- selftest -----------------------------------------------------------
def selftest(no_brain: bool) -> int:
    """Prove the parts that do not need a human in front of the mic."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    ok = True

    brain = Brain(enabled=not no_brain)
    print(f"[selftest] ollama reachable: {brain.available()}")

    probe = os.path.join(rocky.LOGS_DIR, "compare_15s.wav")
    if os.path.exists(probe):
        data, rate = sf.read(probe, dtype="float32", always_2d=True)
        audio = data.mean(axis=1)
        if rate != 16000:                      # what mic capture gives us
            idx = (np.arange(int(len(audio) * 16000 / rate)) * rate / 16000).astype(int)
            audio = audio[np.clip(idx, 0, len(audio) - 1)]
        t0 = time.monotonic()
        heard = Transcriber().transcribe(audio)
        print(f"[selftest] stt ({time.monotonic() - t0:.1f}s): {heard!r}")
        ok = ok and bool(heard)
    else:
        print(f"[selftest] no probe wav at {probe}")

    print(f"[selftest] sentences: {split_sentences('Hi! Are you okay? I am happy happy happy to meet you. ' * 2)}")
    print(f"[selftest] moods: {[(s, rocky_eyes.mood_for(s)) for s in ('I am happy', 'bad bad bad', 'wow really', 'I think so')]}")

    pygame.init()
    pygame.display.set_mode((W, H))
    screen, font = pygame.display.get_surface(), pygame.font.SysFont(FONT_NAME, 15)
    small = pygame.font.SysFont(FONT_NAME, 13)

    # Vision plumbing, tested with a synthetic frame so no camera is needed.
    if brain.available():
        probe_img = pygame.Surface((320, 240))
        probe_img.fill((28, 30, 38))
        pygame.draw.rect(probe_img, (225, 90, 60), pygame.Rect(108, 66, 104, 132), border_radius=10)
        probe_path = os.path.join(rocky.LOGS_DIR, "vision_probe.jpg")
        pygame.image.save(probe_img, probe_path)
        with open(probe_path, "rb") as f:
            jpeg = f.read()
        t0 = time.monotonic()
        seen = brain.vision("Name the main object.", jpeg)
        print(f"[selftest] vision ({time.monotonic() - t0:.1f}s): {seen!r}")

    eyes = rocky_eyes.Eyes()
    outdir = os.path.join(rocky.SCRIPT_DIR, "shots")
    os.makedirs(outdir, exist_ok=True)
    for st, emo, amp, label in ((IDLE, "neutral", 0.0, "idle"), (LISTENING, "neutral", 0.0, "listening"),
                                (THINKING, "thinking", 0.0, "thinking"), (SPEAKING, "happy", 0.7, "speaking")):
        eyes.set_emotion(emo)
        eyes.p = dict(rocky_eyes.PRESETS[emo])
        render(screen, font, small, 0.5, st, "Hello friend! I happy happy happy to meet you." if st == SPEAKING else "",
               "", "are you okay", st == LISTENING, eyes)
        pygame.image.save(screen, os.path.join(outdir, f"app_{label}.png"))
    pygame.quit()
    print(f"[selftest] shots -> {outdir}/app_*.png")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Rocky desk companion")
    ap.add_argument("--no-brain", action="store_true", help="skip the LLM; echo what you say")
    ap.add_argument("--brain-model", default="qwen3-coder:latest")
    ap.add_argument("--brain-context", type=int, default=8192,
                    help="Ollama context window; qwen3-coder defaults to 262k (45 GB), 8k is plenty")
    ap.add_argument("--brain-api", choices=["ollama", "openai", "anthropic"], default="ollama",
                    help="openai/anthropic = hosted brain; needs --brain-url and --brain-key")
    ap.add_argument("--brain-url", default="",
                    help="default http://localhost:11434; "
                         "e.g. https://api.deepseek.com/v1 or https://api.anthropic.com/v1")
    ap.add_argument("--brain-key", default=os.environ.get("BRAIN_API_KEY", ""),
                    help="API key for a hosted brain (or set BRAIN_API_KEY)")
    ap.add_argument("--vision-model", default="qwen2.5vl:3b",
                    help="vision model for F3 (ollama qwen2.5vl:3b, or a hosted model)")
    ap.add_argument("--camera-index", type=int, default=0, help="webcam index for F3")
    ap.add_argument("--no-camera", action="store_true", help="disable F3 look")
    ap.add_argument("--snap", metavar="PATH",
                    help="grab one camera frame, save it, exit (permission check)")
    ap.add_argument("--stt-model", default="base.en",
                    help="tiny.en / base.en / small.en")
    ap.add_argument("--selftest", action="store_true", help="verify stt/brain/eyes, no mic")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest(args.no_brain))

    if args.snap:
        try:
            jpeg = Camera(args.camera_index).snapshot()
            with open(args.snap, "wb") as f:
                f.write(jpeg)
            print(f"[snap] wrote {args.snap} ({len(jpeg)} bytes)")
            sys.exit(0)
        except Exception as e:  # noqa: BLE001
            print(f"[snap] {e}", file=sys.stderr)
            sys.exit(1)

    host = args.brain_url or ("http://localhost:11434" if args.brain_api == "ollama" else "")
    enabled = not args.no_brain
    if not host:
        print("[brain] a hosted brain needs --brain-url; using echo mode", file=sys.stderr)
        enabled = False
    brain = Brain(model=args.brain_model, host=host or "http://localhost:11434",
                  enabled=enabled, api=args.brain_api, api_key=args.brain_key,
                  vision_model=args.vision_model, context=args.brain_context)
    if not brain.available():
        print("[brain] no LLM available - Rocky will repeat what you say", file=sys.stderr)
    camera = None if args.no_camera else Camera(args.camera_index)
    run(Mic(), Transcriber(args.stt_model), brain, camera)


if __name__ == "__main__":
    main()
