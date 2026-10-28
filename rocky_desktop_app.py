#!/usr/bin/env python3
"""
Rocky - a desk companion you can talk to.

Speak (or type) -> local speech-to-text -> local LLM -> British Kokoro speech,
with eyes that morph through emotion presets and bounce to the audio.

Everything runs on this machine; no cloud, no keys.

    python rocky_desktop_app.py                  # mic + Ollama brain
    python rocky_desktop_app.py --watch          # also let the webcam watch for you
    python rocky_desktop_app.py --no-brain       # parrot: he repeats you back
    python rocky_desktop_app.py --selftest       # verify stt/ollama/eyes headless

Senses (modelled on the desk robot he is based on, github.com/cgro00/desk-robot)
    Hearing   hands-free by default. Say "hey Rocky" to wake him; his name alone
              does not. He stays awake for a minute after each exchange, and
              "Rocky, sleep" or "goodnight" puts him back to sleep. He stops
              listening while he thinks or speaks, so he never hears himself.
              F4 toggles; --push-to-talk starts with it off.
    Sight     "what do you see?", "what am I holding?", "look left" or F3 takes
              one camera look. "track me" / "stop tracking", F5, or --watch keep
              the webcam open so his eyes follow your face. Off unless you turn
              it on; he dozes off when ignored.

Controls
    F1 (hold) / F2 (toggle)   talk (push-to-talk, works alongside hands-free)
    F3 or Space               look through the camera
    F4                        hands-free listening on/off
    F5                        webcam watching on/off
    type + Enter              same, by keyboard
    1-7                       force an emotion (when the input line is empty)
    Esc                       quit

Speech defaults to local Kokoro with a British voice preset. Sentences are
generated ahead of playback, so a multi-sentence reply does not stutter between
sentences.
"""
from __future__ import annotations

import argparse
import base64
import collections
import http.client
import io
import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import tempfile
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
W, H = 640, 400
BG     = (5, 8, 14)      # Jarvis theme background
PANEL  = (16, 22, 32)     # Updated color: Panel areas  
LINE   = (38, 54, 74)     # Updated color: Lines and borders
EYE    = (230, 240, 250)  # Updated color: Eyes and glows
DIM    = (126, 146, 176)  # Updated color: Dim text and indicators
INK    = (238, 246, 255)  # Updated color: Main text
WARN   = (255, 190, 100)  # Updated color: Warnings and alerts  
REC    = (255, 100, 100)  # Updated color: Recording indicator
ACCENT = (70, 230, 255)   # Updated color: Accent highlights
OK     = (120, 245, 180)  # Updated color: Status indicators
FPS    = 60
FONT_NAME = "menlo,monospace"
HINT = "F1 hold-talk  F2 talk  F3 look  F4 hands-free  F5 watch  Esc"

LISTENING, THINKING, SPEAKING, IDLE = "LISTENING", "THINKING", "SPEAKING", "IDLE"
LABELS = {LISTENING: "listening...", THINKING: "thinking...", SPEAKING: "speaking"}

SYSTEM_PROMPT = (
    "You are a helpful personal assistant. Speak in natural, contemporary "
    "British English. For a straightforward question, answer directly in one "
    "short sentence, ideally under 15 words. When the user asks for a "
    "description, detail, or continuation, give a clear, well-organized answer "
    "with enough concrete facts and context to satisfy that request. Do not "
    "restate the question, narrate your reasoning, or add unsolicited tips or "
    "follow-up offers. Avoid roleplay, catchphrases, and exaggerated emotion. "
    "Do not claim to be human; answer honestly if asked whether you are an AI."
)

DETAIL_REQUEST_PATTERN = re.compile(
    r"\b(describe|descriptive|explain|detail|detailed|everything|in depth|"
    r"long|thorough|elaborate|continue|keep going|tell me more|more about|"
    r"step by step|compare|list|summari[sz]e)\b",
    re.IGNORECASE,
)


def response_token_limit(text: str) -> int:
    """Reserve longer generations for requests that explicitly need detail."""
    return 220 if DETAIL_REQUEST_PATTERN.search(text) else 48


VISION_PROMPT = "In one short sentence, describe the main thing you see."

# Spoken or typed requests that should open the camera instead of only talking.
LOOK_PATTERN = re.compile(
    r"\b(what (do|can) you see|can you see|do you see|look at (this|me|that|my|the)"
    r"|look (left|right|up|down|around|over there)"
    r"|take a look|have a look|what am i (holding|wearing|showing|doing)"
    r"|what('s| is) (this|that) (thing|object|i'm holding)|how do i look"
    r"|see (this|me|my))\b",
    re.IGNORECASE,
)
# "look left" turns his eyes that way before he looks (the robot turns its head).
LOOK_DIRECTIONS = {"left": (7.0, 0.0), "right": (-7.0, 0.0), "up": (0.0, -4.0),
                   "down": (0.0, 4.0)}

# Hands-free voice commands, matching the desk robot he is modelled on
# (github.com/cgro00/desk-robot): "hey Rocky" wakes him, his name alone does not,
# and he stays awake for a while after each exchange.
AWAKE_SECONDS = 60
WAKE_PATTERN = re.compile(r"\b(hey|hi|hay|okay|ok),?\s+rock(y|ie|ey)\b[\s,.!?]*", re.IGNORECASE)
SLEEP_PATTERN = re.compile(
    r"^\W*((hey\s+)?rock(y|ie|ey)\W+)?(go to sleep|sleep|good ?night)\W*$", re.IGNORECASE)
TRACK_ON_PATTERN = re.compile(r"\b(track me|follow me|watch me|start tracking)\b", re.IGNORECASE)
TRACK_OFF_PATTERN = re.compile(r"\b(stop (tracking|following|watching)( me)?)\b", re.IGNORECASE)

state = IDLE
subtitle = ""        # what is being said, or what was heard
note = ""            # transient line: errors, hints
amplitude = 0.0
eyes_emotion = "neutral"
jobs: queue.Queue = queue.Queue()
mic_recording = False
quiet_until = 0.0    # hands-free listening ignores the mic until this time
face_pos = None      # (x, y) in -1..1 of the face the webcam sees, or None
awake_until = 0.0    # hands-free answers without "hey Rocky" until this time
gaze_override = None  # ((x, y), until) - where he was asked to look
response_cancel = threading.Event()
TTS_ENGINE = "kokoro"
SYSTEM_VOICE = "Samantha"
SYSTEM_VOICE_RATE = 185
KOKORO_VOICE = "bf_emma"
_KOKORO_PIPELINE = None


# --- audio --------------------------------------------------------------
def audio_chunks(audio: np.ndarray, rate: int, chunk_ms: int = 20):
    """Yield short PCM blocks and normalized RMS values for playback."""
    frames = max(1, int(rate * chunk_ms / 1000))
    chunks = (audio[i:i + frames] for i in range(0, len(audio), frames))
    peak = max(
        (float(np.sqrt(np.mean(np.square(chunk)))) for chunk in chunks),
        default=0.0,
    )
    if peak <= 0:
        return
    for i in range(0, len(audio), frames):
        chunk = audio[i:i + frames]
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        yield chunk, min(1.0, (rms / peak) ** 0.6)


def play_with_envelope(wav_bytes: bytes, cancel_event: threading.Event | None = None) -> None:
    """Stream decoded PCM in short blocks, publishing its RMS for the eyes."""
    global amplitude, note, quiet_until
    import sounddevice as sd

    audio, rate = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=True)
    if not len(audio) or not np.any(audio):
        note = "generated audio was empty"
        return
    try:
        with sd.OutputStream(samplerate=rate, channels=audio.shape[1], dtype="float32",
                             blocksize=0, latency="low") as stream:
            for chunk, level in audio_chunks(audio, rate):
                if cancel_event is not None and cancel_event.is_set():
                    break
                stream.write(chunk)
                amplitude = level
    except sd.PortAudioError as e:
        note = f"audio device error: {e}"
        print(f"[audio] {note}", file=sys.stderr)
    finally:
        amplitude = 0.0
    # Let the room echo die down before hands-free listening resumes.
    quiet_until = time.monotonic() + 0.4


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
        if self.stream is not None:      # a second F1 must not leave a stream open
            self.stop()
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


class Endpointer:
    """Cuts a stream of short audio frames into utterances by loudness.

    The noise floor adapts while nobody is talking, so a fan or a quiet room
    both work. Speech starts after a few loud frames in a row and ends after a
    stretch of quiet; a short pre-roll keeps the first syllable.
    """

    def __init__(self, rate: int = 16000, frame_ms: int = 20, start_ms: int = 80,
                 end_ms: int = 700, preroll_ms: int = 300, max_s: float = 15.0,
                 min_speech_ms: int = 250) -> None:
        per_s = 1000 / frame_ms
        self.start_frames = max(1, start_ms // frame_ms)
        self.end_frames = max(1, end_ms // frame_ms)
        self.max_frames = int(max_s * per_s)
        self.min_voiced = max(1, min_speech_ms // frame_ms)
        self.preroll = max(1, preroll_ms // frame_ms)
        self.noise = 0.003
        self.reset()

    def reset(self) -> None:
        self.active = False
        self.hits = 0
        self.voiced = 0
        self.silent = 0
        self.buf: list = []
        self.pre: collections.deque = collections.deque(maxlen=self.preroll)

    def threshold(self) -> float:
        return max(0.012, self.noise * 3.5)

    def push(self, frame: np.ndarray):
        """Feed one frame. Returns ("start"|"end"|"drop", audio-or-None) or None."""
        rms = float(np.sqrt(np.mean(np.square(frame)))) if len(frame) else 0.0
        loud = rms > self.threshold()
        if not self.active:
            self.pre.append(frame)
            if loud:
                self.hits += 1
            else:
                self.hits = 0
                self.noise = min(0.05, max(0.001, 0.95 * self.noise + 0.05 * rms))
            if self.hits >= self.start_frames:
                self.active = True
                self.buf = list(self.pre)
                self.voiced, self.silent = self.hits, 0
                return ("start", None)
            return None
        self.buf.append(frame)
        if loud:
            self.voiced += 1
            self.silent = 0
        else:
            self.silent += 1
        if self.silent >= self.end_frames or len(self.buf) >= self.max_frames:
            audio = np.concatenate(self.buf).astype(np.float32)
            voiced = self.voiced
            self.reset()
            return ("end", audio) if voiced >= self.min_voiced else ("drop", None)
        return None


class Ears:
    """Hands-free listening: an always-open mic stream cut into utterances.

    Audio stays on this machine. Rocky stops listening while he is thinking or
    speaking (there is no echo cancellation), so he never hears himself.
    """

    RATE = 16000
    FRAME = 320  # 20 ms

    def __init__(self, end_silence_ms: int = 700) -> None:
        self.enabled = False
        self.error = ""
        self.stream = None
        self.frames: queue.Queue = queue.Queue(maxsize=500)
        self.endpointer = Endpointer(self.RATE, 1000 * self.FRAME // self.RATE,
                                     end_ms=end_silence_ms)
        self.thread = None

    def start(self) -> bool:
        import sounddevice as sd
        if self.enabled:
            return True
        self.error = ""
        try:
            self.stream = sd.InputStream(samplerate=self.RATE, channels=1, dtype="float32",
                                         blocksize=self.FRAME, callback=self._cb)
            self.stream.start()
        except Exception as e:  # noqa: BLE001
            self.error, self.stream = str(e), None
            print(f"[ears] {e}", file=sys.stderr)
            return False
        self.endpointer.reset()
        self.enabled = True
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        return True

    def stop(self) -> None:
        self.enabled = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:  # noqa: BLE001
                pass
            self.stream = None
        self.endpointer.reset()

    def close(self) -> None:
        self.stop()
        self.frames.put(None)

    def _cb(self, indata, frames, time_info, status):
        try:
            self.frames.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def can_hear(self) -> bool:
        return (self.enabled and not mic_recording and state in (IDLE, LISTENING)
                and time.monotonic() >= quiet_until)

    def _loop(self) -> None:
        global state
        while True:
            frame = self.frames.get()
            if frame is None:
                return
            if not self.can_hear():
                if self.endpointer.active and state == LISTENING:
                    state = IDLE
                self.endpointer.reset()
                continue
            event = self.endpointer.push(frame)
            if event is None:
                continue
            kind, audio = event
            if kind == "start" and state == IDLE:
                state = LISTENING
            elif kind == "end":
                state = THINKING
                jobs.put({"audio": audio, "hands_free": True})
            elif kind == "drop" and state == LISTENING:
                state = IDLE


# --- camera -------------------------------------------------------------
class Camera:
    """Opens the webcam only when asked. No idle streaming, nothing uploaded.

    Frames are grabbed, JPEG-compressed at 640x480, and the device is closed
    again - so the camera light only comes on for the moment of a look.
    """

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.live = None  # a running Watcher shares its frames instead of reopening

    def snapshot(self, warmup: int = 5) -> bytes:
        import cv2
        frame = self.live.latest() if self.live is not None else None
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                return buf.tobytes()
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


class Watcher:
    """Opt-in presence sense: keeps the webcam open and watches for a face.

    Off unless turned on (F5 or --watch); the camera light stays on while it
    runs. Frames never leave the machine: face detection is OpenCV's bundled
    Haar cascade, and the vision model only sees a frame when you ask.
    """

    def __init__(self, camera: Camera, fps: float = 4.0, absent_after: float = 8.0) -> None:
        self.camera = camera
        self.period = 1.0 / fps
        self.absent_after = absent_after
        self.enabled = False
        self.error = ""
        self.present = False
        self._frame = None
        self._frame_t = 0.0
        self._lock = threading.Lock()
        self._thread = None

    def start(self) -> bool:
        import cv2
        if self.enabled:
            return True
        self.error = ""
        cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        if cascade.empty():
            self.error = "face detector unavailable"
            return False
        cap = cv2.VideoCapture(self.camera.index)
        if not cap.isOpened():
            self.error = "camera unavailable"
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep frames fresh at a low read rate
        self.enabled, self.present = True, False
        self.camera.live = self
        self._thread = threading.Thread(target=self._loop, args=(cap, cascade), daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        global face_pos
        self.enabled = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self.camera.live = None
        face_pos = None
        with self._lock:
            self._frame = None

    def latest(self, max_age: float = 1.0):
        with self._lock:
            if self._frame is not None and time.monotonic() - self._frame_t <= max_age:
                return self._frame.copy()
        return None

    def _loop(self, cap, cascade) -> None:
        global face_pos
        import cv2
        seen_streak, last_seen = 0, 0.0
        try:
            while self.enabled:
                t0 = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.2)
                    continue
                with self._lock:
                    self._frame, self._frame_t = frame, t0
                small = cv2.resize(frame, (320, 240))
                gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                                 minSize=(36, 36))
                if len(faces):
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    face_pos = ((x + w / 2) / 160 - 1.0, (y + h / 2) / 120 - 1.0)
                    seen_streak, last_seen = seen_streak + 1, t0
                    if not self.present and seen_streak >= 2:
                        self.present = True
                        jobs.put({"event": "arrived"})
                else:
                    seen_streak = 0
                    face_pos = None
                    if self.present and t0 - last_seen > self.absent_after:
                        self.present = False
                        jobs.put({"event": "left"})
                time.sleep(max(0.0, self.period - (time.monotonic() - t0)))
        finally:
            cap.release()
            face_pos = None


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
        self._response_lock = threading.Lock()
        self._active_response = None

    def cancel(self) -> None:
        """Close the active text stream so an interrupted turn can finish."""
        with self._response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except OSError as e:
                print(f"[brain] could not close interrupted response: {e}", file=sys.stderr)

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
        token_limit = response_token_limit(text)
        if self.api == "openai":
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            body = json.dumps({
                "model": self.model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": text}],
                "stream": True,
                "max_tokens": token_limit,
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
            "options": {"num_predict": token_limit, "temperature": 0.8, "top_p": 0.9,
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

    def stream(self, text: str, cancel_event: threading.Event | None = None):
        """Yield content deltas as they arrive."""
        if (cancel_event is not None and cancel_event.is_set()) or not self.available():
            return
        response = None
        try:
            response = urllib.request.urlopen(self._request(text), timeout=120)
            with self._response_lock:
                self._active_response = response
            if cancel_event is not None and cancel_event.is_set():
                return
            for delta in self._deltas(response):
                if cancel_event is not None and cancel_event.is_set():
                    break
                yield delta
        except (urllib.error.URLError, TimeoutError, ValueError, OSError,
                http.client.HTTPException) as e:
            if cancel_event is None or not cancel_event.is_set():
                print(f"[brain] {e}", file=sys.stderr)
        finally:
            with self._response_lock:
                if self._active_response is response:
                    self._active_response = None
            if response is not None:
                response.close()

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
def synthesize(text: str):
    global _KOKORO_PIPELINE
    if TTS_ENGINE == "kokoro":
        if _KOKORO_PIPELINE is None:
            from kokoro import KPipeline
            _KOKORO_PIPELINE = KPipeline(lang_code="b")
        chunks = [audio for _, _, audio in _KOKORO_PIPELINE(
            text, voice=KOKORO_VOICE, speed=1.0
        )]
        if not chunks:
            raise RuntimeError("Kokoro produced no speech audio")
        audio = np.concatenate(chunks)
        wav = io.BytesIO()
        sf.write(wav, audio, 24000, format="WAV", subtype="PCM_16")
        return text, wav.getvalue()

    if TTS_ENGINE == "macos":
        with tempfile.TemporaryDirectory(prefix="rocky-voice-") as directory:
            audio_path = os.path.join(directory, "reply.aiff")
            result = subprocess.run(
                ["/usr/bin/say", "-v", SYSTEM_VOICE, "-r", str(SYSTEM_VOICE_RATE),
                 "-o", audio_path, text],
                capture_output=True, text=True, timeout=60, check=False,
            )
            if result.returncode:
                detail = result.stderr.strip() or f"say exited with status {result.returncode}"
                raise RuntimeError(f"macOS voice {SYSTEM_VOICE!r} failed: {detail}")
            with open(audio_path, "rb") as audio_file:
                return text, audio_file.read()

    raise RuntimeError(f"unsupported TTS engine: {TTS_ENGINE}")


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


def sentence_stream(brain: Brain, text: str,
                    cancel_event: threading.Event | None = None):
    """Turn streamed LLM deltas into sentences, yielding each as it completes."""
    buf = ""
    for delta in brain.stream(text, cancel_event=cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            return
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


def speak(sentences, cancel_event: threading.Event | None = None) -> None:
    """Synthesize ahead of playback; start talking as soon as clause 1 exists."""
    global state, subtitle, eyes_emotion
    prefetch: queue.Queue = queue.Queue(maxsize=3)
    said = ""

    def enqueue(item) -> bool:
        while cancel_event is None or not cancel_event.is_set():
            try:
                prefetch.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def produce():
        global note
        try:
            first = True
            for sentence in sentences:
                if cancel_event is not None and cancel_event.is_set():
                    break
                for chunk in clause_split(sentence, first=first):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    if not enqueue(synthesize(chunk)):
                        return
                    first = False
        except Exception as e:  # noqa: BLE001
            note = f"voice error: {e}"[:68]
            print(f"[tts] {e}", file=sys.stderr)
        finally:
            enqueue(None)

    threading.Thread(target=produce, daemon=True).start()
    while True:
        if cancel_event is not None and cancel_event.is_set():
            break
        try:
            item = prefetch.get(timeout=0.05)
        except queue.Empty:
            continue
        if item is None:
            break
        spoken, wav = item
        said = f"{said} {spoken}".strip()
        subtitle = said
        eyes_emotion = rocky_eyes.mood_for(said)
        if wav is None:
            continue
        state = SPEAKING
        play_with_envelope(wav, cancel_event=cancel_event)


def look(camera, brain: Brain, question: str = "",
         cancel_event: threading.Event | None = None) -> None:
    """Take one webcam frame and answer about it (F3, or a spoken 'look')."""
    global state, subtitle, note, eyes_emotion
    state, eyes_emotion, subtitle = THINKING, "thinking", "looking..."
    if camera is None:
        note, state = "camera disabled", IDLE
        return
    jpeg = camera.snapshot()
    try:      # keep what he saw, for when the answer makes no sense
        with open(os.path.join(rocky.LOGS_DIR, "last_look.jpg"), "wb") as f:
            f.write(jpeg)
    except OSError:
        pass
    prompt = (f'Your friend asks: "{question}" Answer that.' if question
              else "Describe the scene.")
    reply = brain.vision(prompt, jpeg)
    if not reply:
        note, state = f"no vision reply - try: ollama pull {brain.vision_model}", IDLE
        return
    print(f"[rocky] {reply}", file=sys.stderr)
    speak(split_sentences(reply), cancel_event)
    state = IDLE


# faster-whisper sometimes "hears" these in room noise; ignore them hands-free.
PHANTOM_PHRASES = {"", "you", "thank you", "thanks", "thanks for watching", "bye", "okay"}


def stay_awake() -> None:
    global awake_until
    awake_until = time.monotonic() + AWAKE_SECONDS


def say_line(line: str, cancel_event: threading.Event | None = None) -> None:
    """Speak a fixed line, e.g. to confirm a voice command."""
    global state
    state = THINKING
    speak([line], cancel_event)
    state = IDLE


def worker(transcriber: Transcriber, brain: Brain, camera, watcher=None) -> None:
    global state, subtitle, note, eyes_emotion, awake_until, gaze_override
    while True:
        job = jobs.get()
        if job is None:
            return
        response_cancel.clear()
        try:
            note = ""
            if job.get("look") is not None:
                look(camera, brain, cancel_event=response_cancel)
                continue

            event = job.get("event")
            if event == "left":
                if state == IDLE:
                    eyes_emotion, subtitle = "sleepy", ""
                continue
            if event == "arrived":
                # He perks up when you sit down; like the robot, he does not talk
                # unprompted.
                if state == IDLE:
                    eyes_emotion = "happy"
                continue

            if "audio" in job:
                if job["audio"] is None:     # F2 pressed and released with no sound
                    note, state = "didn't catch that", IDLE
                    continue
                state, eyes_emotion = THINKING, "thinking"
                heard = transcriber.transcribe(job["audio"])
                if job.get("hands_free"):
                    if heard.strip(" .!?,").lower() in PHANTOM_PHRASES:
                        state = IDLE
                        continue
                    wake = WAKE_PATTERN.search(heard)
                    if wake is None and time.monotonic() >= awake_until:
                        state = IDLE  # asleep, and nobody said "hey Rocky"
                        continue
                    if wake is not None:
                        stay_awake()
                        rest = heard[wake.end():].strip(" ,.!?")
                        if not rest:  # just his name: look up and wait
                            subtitle, eyes_emotion, state = "you: " + heard, "surprised", IDLE
                            gaze_override = ((0.0, -4.0), time.monotonic() + 2.0)
                            continue
                        heard = rest
                if not heard:
                    note, state = "didn't catch that", IDLE
                    continue
                subtitle = "you: " + heard
                text = heard
            else:
                text = job["text"]
            wake = WAKE_PATTERN.match(text)
            if wake is not None and text[wake.end():].strip():
                text = text[wake.end():].strip()

            if SLEEP_PATTERN.match(text):
                awake_until = 0.0
                say_line("Goodnight, friend.", response_cancel)
                eyes_emotion = "sleepy"
                continue
            stay_awake()

            if TRACK_OFF_PATTERN.search(text) or TRACK_ON_PATTERN.search(text):
                if watcher is None:
                    say_line("No camera, friend.", response_cancel)
                elif TRACK_OFF_PATTERN.search(text):
                    watcher.stop()
                    say_line("Okay. Stop watching.", response_cancel)
                elif watcher.start():
                    say_line("Watching you, friend.", response_cancel)
                else:
                    note = f"watching failed: {watcher.error}"
                    say_line("Cannot see. Camera problem.", response_cancel)
                continue

            if camera is not None and LOOK_PATTERN.search(text):
                direction = re.search(r"\blook (left|right|up|down)\b", text, re.IGNORECASE)
                if direction:
                    gaze_override = (LOOK_DIRECTIONS[direction.group(1).lower()],
                                     time.monotonic() + 4.0)
                print(f"[you] {text} (looking)", file=sys.stderr)
                look(camera, brain, text, cancel_event=response_cancel)
                stay_awake()
                continue

            state, eyes_emotion = THINKING, "thinking"
            if brain.available():
                print(f"[you] {text}", file=sys.stderr)
                speak(sentence_stream(brain, text, response_cancel), response_cancel)
            else:
                # echo mode: he repeats you back in his own grammar
                print(f"[rocky] {text}", file=sys.stderr)
                speak(split_sentences(text), response_cancel)
            if response_cancel.is_set():
                state = IDLE
                continue
            state = IDLE
            stay_awake()
        except Exception as e:  # noqa: BLE001
            note, state = f"error: {e}", IDLE
            print(f"[worker] {e}", file=sys.stderr)


# --- drawing ------------------------------------------------------------
# --- drawing ------------------------------------------------------------
chrome_cache = {}  # keyed by (W, H) to avoid recreating it every frame

def render(screen, font, small, t, st, said, msg, typed, recording, eyes,
           ears_on=False, watching=False, awake=False):
    global chrome_cache
    
    # Build or retrieve static chrome
    chrome_key = (W, H)
    if chrome_key not in chrome_cache:
        chrome = pygame.Surface((W, H), pygame.SRCALPHA)
        chrome.fill(BG)
        
        # Draw 20 px dot grid in LINE at ~40% brightness 
        for y in range(0, H, 20):
            for x in range(0, W, 20):
                pygame.draw.circle(chrome, LINE, (x + 10, y + 10), 1)
        
        # Draw 1 px inset border rect
        border_rect = pygame.Rect(8, 8, W - 16, H - 16)
        pygame.draw.rect(chrome, LINE, border_rect, 1)
        
        # Draw 18 px corner brackets in ACCENT at all four corners (2 px thick L shapes)
        # Top-left bracket
        pygame.draw.line(chrome, ACCENT, (8, 8), (26, 8), 2)
        pygame.draw.line(chrome, ACCENT, (8, 8), (8, 26), 2)
        
        # Top-right bracket  
        pygame.draw.line(chrome, ACCENT, (W-8, 8), (W-26, 8), 2)
        pygame.draw.line(chrome, ACCENT, (W-8, 8), (W-8, 26), 2)
        
        # Bottom-left bracket
        pygame.draw.line(chrome, ACCENT, (8, H-8), (26, H-8), 2)
        pygame.draw.line(chrome, ACCENT, (8, H-8), (8, H-26), 2)
        
        # Bottom-right bracket
        pygame.draw.line(chrome, ACCENT, (W-8, H-8), (W-26, H-8), 2)
        pygame.draw.line(chrome, ACCENT, (W-8, H-8), (W-8, H-26), 2)
        
        chrome_cache[chrome_key] = chrome
    
    # Blit the static chrome
    screen.blit(chrome_cache[chrome_key], (0, 0))
    
    # Draw eyes in the center
    eyes.draw(screen, t, glow=0.5 + amplitude * 0.9)
    
    # Header
    header_y = 14
    
    # Rockey logo
    font_large = pygame.font.SysFont(FONT_NAME, 18)
    rocky_text = font_large.render("ROCKY", True, ACCENT)
    screen.blit(rocky_text, ((W - rocky_text.get_width()) // 2, header_y))
    
    # Separator dot
    sep_dot = pygame.Surface((6, 6), pygame.SRCALPHA)
    pygame.draw.circle(sep_dot, LINE, (3, 3), 3)
    screen.blit(sep_dot, ((W - rocky_text.get_width()) // 2 + rocky_text.get_width() + 8, header_y + 7))
    
    # Mic state  
    mic_x = (W - rocky_text.get_width()) // 2 + rocky_text.get_width() + 24
    if ears_on:
        mic_dot = pygame.Surface((6, 6), pygame.SRCALPHA)
        pygame.draw.circle(mic_dot, OK, (3, 3), 3)  
        screen.blit(mic_dot, (mic_x, header_y + 7))
        mic_text = small.render("MIC ON", True, OK)
    else:
        mic_dot = pygame.Surface((6, 6), pygame.SRCALPHA)
        pygame.draw.circle(mic_dot, DIM, (3, 3), 3)  
        screen.blit(mic_dot, (mic_x, header_y + 7))
        mic_text = small.render("MIC OFF", True, DIM)
    screen.blit(mic_text, (mic_x + 12, header_y))
    
    # Camera state  
    cam_x = mic_x + mic_text.get_width() + 36
    if watching:
        cam_dot = pygame.Surface((6, 6), pygame.SRCALPHA)
        pygame.draw.circle(cam_dot, WARN, (3, 3), 3)  
        screen.blit(cam_dot, (cam_x, header_y + 7))
        cam_text = small.render("CAM ON", True, WARN)
    else:
        cam_dot = pygame.Surface((6, 6), pygame.SRCALPHA)
        pygame.draw.circle(cam_dot, DIM, (3, 3), 3)  
        screen.blit(cam_dot, (cam_x, header_y + 7))
        cam_text = small.render("CAM OFF", True, DIM)
    screen.blit(cam_text, (cam_x + 12, header_y))
    
    # State chip (on right)
    chip_width = 120
    chip_height = 26 
    chip_x = W - chip_width - 16
    chip_y = header_y
    
    state_colors = {
        IDLE: DIM,
        LISTENING: OK,
        THINKING: ACCENT,
        SPEAKING: (255, 206, 120)  # Warm speaking color as specified
    }
    
    # Draw chip background with 12% alpha fill
    state_color = state_colors.get(st, DIM)
    pygame.draw.rect(screen, (*state_color[:3], int(0.12 * 255)), 
                     (chip_x, chip_y, chip_width, chip_height), border_radius=6, 
                     width=0)  # fill with alpha
    
    # Draw border
    pygame.draw.rect(screen, LINE, (chip_x, chip_y, chip_width, chip_height), 
                     border_radius=6, width=1)
    
    # State name text  
    state_text = small.render(st, True, state_color)
    screen.blit(state_text, (chip_x + 12, chip_y + 4))
    
    # Awake/Asleep indicator 
    awake_text = small.render("AWAKE" if awake else "ASLEEP", True, OK if awake else DIM)
    screen.blit(awake_text, (chip_x + state_text.get_width() + 18, chip_y + 4))
    
    # Time text
    time_text = small.render(time.strftime("%H:%M:%S"), True, DIM)
    screen.blit(time_text, (chip_x + state_text.get_width() + awake_text.get_width() + 36, chip_y + 4))
    
    # Assistant core area with eyes at center of screen at (W//2, 200) 
    eye_center = (W // 2, 200)
    
    # Draw full circle around the eyes at radius 108 in LINE
    pygame.draw.circle(screen, LINE, eye_center, 108, 1)
      
    # Draw 24 tick marks on radius 118  
    for i in range(24):
        angle = (i * 360) / 24  # degrees
        radians = math.radians(angle)
        x1 = eye_center[0] + math.cos(radians) * 118
        y1 = eye_center[1] + math.sin(radians) * 118
        if i % 4 == 0:
            length = 8  # Longer ticks every 4th
        else:
            length = 4  # Shorter ticks  
        x2 = eye_center[0] + math.cos(radians) * (118 + length)
        y2 = eye_center[1] + math.sin(radians) * (118 + length)
        pygame.draw.line(screen, LINE, (x1, y1), (x2, y2), 1)
        
    # Draw the state arc
    arc_radius = 108
    arc_width = 2
    rect = pygame.Rect(eye_center[0] - arc_radius, eye_center[1] - arc_radius,
                       arc_radius * 2, arc_radius * 2)
    
    if st == LISTENING:
        # Breathing 90° arc in OK (length modulated by sin(t*2)) 
        arc_length = 90 + 45 * math.sin(t * 2)
        start_angle = -45
        end_angle = start_angle + arc_length
    elif st == THINKING:
        # 120° rotating arc in ACCENT 
        start_angle = t * 180 % 360  
        end_angle = start_angle + 120
    elif st == SPEAKING:
        # Arc from 0° to (90 + 180*amplitude)° in warm color
        start_angle = 0 
        end_angle = 90 + 180 * amplitude
    else:  # IDLE
        # Static 90° arc in DIM  
        start_angle = -45
        end_angle = 45
        
    if st == LISTENING or st == THINKING or st == SPEAKING:
        # Highlight ticks inside active arc with ACCENT color
        for i in range(24):
            angle = (i * 360) / 24  # degrees
            if st == LISTENING or st == SPEAKING:  
                # Show ACCENT for all ticks when listening/speaking
                tick_color = ACCENT
            elif st == THINKING:
                # Use ACCENT for tick inside the thinking arc and LINE for outside 
                if start_angle <= angle <= end_angle or (start_angle < 0 and angle >= 360 + start_angle):
                    tick_color = ACCENT 
                else:
                    tick_color = LINE
            else:
                tick_color = LINE
            
            radians = math.radians(angle)
            x1 = eye_center[0] + math.cos(radians) * 118
            y1 = eye_center[1] + math.sin(radians) * 118
            if i % 4 == 0:
                length = 8  
            else:
                length = 4  
            x2 = eye_center[0] + math.cos(radians) * (118 + length)
            y2 = eye_center[1] + math.sin(radians) * (118 + length)
            pygame.draw.line(screen, tick_color, (x1, y1), (x2, y2), 1)
    
    # Draw arc in state color
    arc_color = state_colors.get(st, DIM) if st != SPEAKING else (255, 206, 120) 
    if recording:
        arc_color = REC
        
    pygame.draw.arc(screen, arc_color, rect, math.radians(start_angle), 
                    math.radians(end_angle), arc_width)
    
    # Recording indicator  
    if recording:
        rec_text = small.render("● REC", True, REC)
        screen.blit(rec_text, (W - 24 - 50, header_y + 16))
        
    # Waveform at y baseline 300, 48 bars, centred, 2px wide with 6px pitch
    waveform_y = 300
    bar_count = 48
    total_width = bar_count * 2 + (bar_count - 1) * 6
    start_x = (W - total_width) // 2
    if amplitude < 0.02:  
        # Hairline at the center  
        pygame.draw.line(screen, LINE, (start_x, waveform_y), (start_x + total_width, waveform_y), 1)
    else:
        for i in range(bar_count):
            wobble = 0.35 + 0.65 * abs(math.sin(t * 6 + i * 0.7))
            bar_height = 2 + 26 * amplitude * wobble
            bar_x = start_x + i * (2 + 6)
            
            # Draw both top and bottom halves symmetrically
            pygame.draw.line(screen, ACCENT, (bar_x, waveform_y - bar_height/2), 
                            (bar_x, waveform_y + bar_height/2), 2)

    # Caption card  
    caption_rect = pygame.Rect(16, 314, W-32, 48)
    pygame.draw.rect(screen, PANEL, caption_rect, border_radius=6, width=1) 
    pygame.draw.line(screen, LINE, (caption_rect.left, caption_rect.top), 
                    (caption_rect.right, caption_rect.top), 1)
    pygame.draw.line(screen, LINE, (caption_rect.left, caption_rect.bottom), 
                    (caption_rect.right, caption_rect.bottom), 1)
    
    # Caption text
    if said:
        # Measure full text first to determine if we need to ellipsize
        text_width = font.size(said)[0]
        if text_width > W - 32 - 20:  # 16 px left/right padding + 4 px margin
            # Need to truncate  
            truncated = said
            while font.size(truncated)[0] > W - 32 - 20 and len(truncated) > 0:
                truncated = truncated[:-1]
            if truncated: 
                if truncated != said:
                    said_text = truncated + "…"
                else:
                    said_text = said
            else:
                said_text = ""
        else:
            said_text = said
            
        screen.blit(font.render(said_text, True, INK), (28, 328))
    elif st == THINKING:
        thinking_text = small.render("thinking…", True, ACCENT)
        screen.blit(thinking_text, (28, 328))
    elif st == IDLE and not said:
        hint_text = small.render(HINT, True, DIM)
        screen.blit(hint_text, (28, 328))
    
    # Command bar
    cmd_x, cmd_y = 16, 368
    cmd_width, cmd_height = W-32, 24
    
    pygame.draw.rect(screen, PANEL, (cmd_x, cmd_y, cmd_width, cmd_height), border_radius=4, width=1)
    
    # Set command bar color based on recording or typing state
    if not recording and typed:
        bar_color = ACCENT 
    else:
        bar_color = LINE
    
    pygame.draw.rect(screen, (*bar_color[:3], 255), (cmd_x + 4, cmd_y + 1, cmd_width - 8, cmd_height - 2), border_radius=3)
        
    # Text in command bar  
    caret = "_" if int(t * 2) % 2 else " "
    full_text = "> " + typed
    displayed_text = full_text
    
    # Check if the command text is too long to fit 
    text_width = small.size(displayed_text)[0] + 10  # add spacing
    if text_width > cmd_width - 28:  # leave about 16 px padding + 12 for caret
        # Find longest substring that fits
        max_chars = len(displayed_text)
        while max_chars > 0:
            test_str = displayed_text[:max_chars]
            if small.size(test_str)[0] <= cmd_width - 28:
                displayed_text = test_str 
                break
            max_chars -= 1
            
        if max_chars == 0:
            displayed_text = ""
    
    # Draw command prompt or empty text  
    if typed:
        screen.blit(small.render(displayed_text, True, INK), (28, 374))
    else: 
        hint = small.render("type a message or hold F1", True, DIM)
        screen.blit(hint, (28, 374))
        
    # Draw caret if typed
    if typed:
        caret_x = 28 + small.size(displayed_text)[0]
        screen.blit(small.render(caret, True, INK), (caret_x, 374)) 
    
    # Msg (errors/notes) - right aligned, then left aligned when needed to fit
    if msg and len(msg) > 0:
        label = small.render(msg[:68], True, WARN)
        # Check if it fits on the right side of caption card
        right_aligned_x = W - 16 - label.get_width() 
        if right_aligned_x > (28 + label.get_width()):  # Has room to be right-aligned  
            screen.blit(label, (right_aligned_x, 328))  
        else:  # Place on left side of command bar
            screen.blit(label, (28, 368 + 12))  # Place under the command bar
            
    pygame.display.flip()


def run(mic: Mic, transcriber: Transcriber, brain: Brain, camera=None,
        ears=None, watcher=None, hands_free: bool = True, watch: bool = False) -> None:
    global state, mic_recording, note
    pygame.init()
    pygame.display.set_caption("Rocky")
    screen = pygame.display.set_mode((W, H))
    font = pygame.font.SysFont(FONT_NAME, 15)
    small = pygame.font.SysFont(FONT_NAME, 13)
    clock = pygame.time.Clock()
    eyes = rocky_eyes.Eyes()

    threading.Thread(target=worker, args=(transcriber, brain, camera, watcher),
                     daemon=True).start()
    threading.Thread(target=transcriber.warm, daemon=True).start()
    threading.Thread(target=brain.warm, daemon=True).start()
    if ears is not None and hands_free and not ears.start():
        note = f"hands-free off: {ears.error}"[:68]
    if watcher is not None and watch and not watcher.start():
        note = f"watching off: {watcher.error}"

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
                    if state in (THINKING, SPEAKING):
                        response_cancel.set()
                        brain.cancel()
                        state = IDLE
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
                elif e.key == pygame.K_F4 and ears is not None:
                    if ears.enabled:
                        ears.stop()
                        if state == LISTENING and not recording:
                            state = IDLE
                        note = "hands-free off - F1/F2 to talk"
                    elif ears.start():
                        note = "hands-free on - just talk"
                    else:
                        note = f"hands-free failed: {ears.error}"[:68]
                elif e.key == pygame.K_F5 and watcher is not None:
                    if watcher.enabled:
                        watcher.stop()
                        note = "watching off - camera closed"
                    elif watcher.start():
                        note = "watching on - camera stays open"
                    else:
                        note = f"watching failed: {watcher.error}"
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

        # emotion follows what the robot is doing; when ignored (asleep, idle,
        # nobody in view) he dozes off like the desk robot does
        if recording and state == IDLE:
            state = LISTENING
        dozing = (ears is not None and ears.enabled and state == IDLE
                  and face_pos is None and now > awake_until + 15)
        if state == LISTENING:
            eyes.set_emotion("neutral")
        elif state == THINKING:
            eyes.set_emotion("thinking")
        elif dozing:
            eyes.set_emotion("sleepy")
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

        seen = face_pos
        override = gaze_override
        if override is not None and now < override[1]:
            g = override[0]
        elif state == THINKING:
            g = (0.0, -4.0)
        elif seen is not None:
            # Look back at the person the webcam sees. The camera is not mirrored:
            # someone on the image's right is on Rocky's right, which is the
            # viewer's left, so his eyes move toward screen-left.
            g = (-seen[0] * 7.0, seen[1] * 4.0)
        elif state == LISTENING:
            g = (0.0, -3.0)
        else:
            g = gaze

        eyes.update(dt, amp=amplitude, blink=bool(blink_until), t=now, gaze=g)
        render(screen, font, small, now, state, subtitle, note, typed, recording, eyes,
               ears_on=ears is not None and ears.enabled,
               watching=watcher is not None and watcher.enabled,
               awake=now < awake_until)
        clock.tick(FPS)

    if ears is not None:
        ears.close()
    if watcher is not None:
        watcher.stop()
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
    ok = senses_selftest() and ok

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
        render(screen, font, small, 0.5, st, "Hello friend! I happy happy happy to meet you." if st == SPEAKING else "what are you looking at",
               "", "are you okay", st == LISTENING, eyes)
        pygame.image.save(screen, os.path.join(outdir, f"app_{label}.png"))
    pygame.quit()
    print(f"[selftest] shots -> {outdir}/app_*.png")
    return 0 if ok else 1


def senses_selftest() -> bool:
    """Hearing and sight checks that need no microphone, camera, or models."""
    ok = True

    # Hearing: room noise, then 1 s of speech-like tone, then silence -> one utterance.
    rng = np.random.default_rng(0)
    rate, frame = 16000, 320
    t = np.arange(rate) / rate
    speech = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    stream = np.concatenate([rng.normal(0, 0.002, rate).astype(np.float32), speech,
                             rng.normal(0, 0.002, rate).astype(np.float32)])
    ep, events = Endpointer(rate, 20), []
    for i in range(0, len(stream) - frame + 1, frame):
        event = ep.push(stream[i:i + frame])
        if event:
            events.append((event[0], 0 if event[1] is None else len(event[1]) / rate))
    heard_ok = [k for k, _ in events] == ["start", "end"] and 1.0 <= events[-1][1] <= 2.2
    print(f"[selftest] hearing endpointer: {events} -> {'ok' if heard_ok else 'FAIL'}")
    ok = ok and heard_ok

    fast_ep = Endpointer(rate, 20, end_ms=300)
    fast_events = []
    for i in range(0, len(stream) - frame + 1, frame):
        event = fast_ep.push(stream[i:i + frame])
        if event:
            fast_events.append((event[0], 0 if event[1] is None else len(event[1]) / rate))
    faster_end_ok = (len(fast_events) == 2 and fast_events[-1][0] == "end"
                     and fast_events[-1][1] < events[-1][1])
    print(f"[selftest] configurable endpoint pause: "
          f"{'ok' if faster_end_ok else 'FAIL'}")
    ok = ok and faster_end_ok

    clicks, ep = [], Endpointer(rate, 20)  # a short click must not become an utterance
    blip = np.concatenate([np.zeros(rate // 2, np.float32), 0.3 * np.ones(1600, np.float32),
                           np.zeros(rate, np.float32)])
    for i in range(0, len(blip) - frame + 1, frame):
        event = ep.push(blip[i:i + frame])
        if event and event[0] == "end":
            clicks.append(event)
    print(f"[selftest] hearing ignores a click: {'ok' if not clicks else 'FAIL'}")
    ok = ok and not clicks

    asks = ("What do you see?", "Rocky, what am I holding", "look at this", "can you see me",
            "Rocky, look left")
    chats = ("I look forward to it", "what is the time", "see you later", "hello friend")
    look_ok = all(LOOK_PATTERN.search(s) for s in asks) and not any(
        LOOK_PATTERN.search(s) for s in chats)
    print(f"[selftest] sight look-intent: {'ok' if look_ok else 'FAIL'}")
    ok = ok and look_ok

    wake = WAKE_PATTERN.search("Hey, Rocky, what time is it?")
    commands_ok = (
        bool(WAKE_PATTERN.search("Hey Rocky.")) and wake is not None
        and "Hey, Rocky, what time is it?"[wake.end():] == "what time is it?"
        and not WAKE_PATTERN.search("Rocky is my friend")      # name alone does not wake
        and not WAKE_PATTERN.search("I like rocky road ice cream")
        and all(SLEEP_PATTERN.match(s) for s in ("Rocky, sleep.", "Goodnight!", "good night"))
        and not SLEEP_PATTERN.match("I need more sleep tonight")
        and bool(TRACK_ON_PATTERN.search("Rocky, track me"))
        and bool(TRACK_OFF_PATTERN.search("stop tracking"))
        and not TRACK_ON_PATTERN.search("stop tracking"))
    print(f"[selftest] hearing commands (wake/sleep/track): {'ok' if commands_ok else 'FAIL'}")
    ok = ok and commands_ok

    response_limits_ok = (
        response_token_limit("What time is it?") == 48
        and response_token_limit("Describe how geothermal turbines work.") == 220
        and response_token_limit("Continue with more detail.") == 220
    )
    print(f"[selftest] response length by request: "
          f"{'ok' if response_limits_ok else 'FAIL'}")
    ok = ok and response_limits_ok

    cancel = threading.Event()

    class CancellingBrain:
        def stream(self, text, cancel_event=None):
            yield "First sentence. "
            cancel_event.set()
            yield "This sentence must not be returned."

    interrupted = list(sentence_stream(CancellingBrain(), "test", cancel))
    cancel_ok = interrupted == ["First sentence."]
    print(f"[selftest] response cancellation: {'ok' if cancel_ok else 'FAIL'}")
    ok = ok and cancel_ok

    pcm = np.concatenate((np.full((480, 1), 0.5, np.float32),
                          np.full((480, 1), 0.25, np.float32),
                          np.zeros((100, 1), np.float32)))
    blocks = list(audio_chunks(pcm, 24000))
    pcm_ok = ([len(block) for block, _ in blocks] == [480, 480, 100]
              and blocks[0][1] == 1.0 and 0.6 < blocks[1][1] < 0.7
              and blocks[2][1] == 0.0)
    print(f"[selftest] PCM playback chunks: {'ok' if pcm_ok else 'FAIL'}")
    ok = ok and pcm_ok

    try:
        import cv2
        cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        face_ok = not cascade.empty()
    except Exception as e:  # noqa: BLE001
        print(f"[selftest] sight face detector: {e}")
        face_ok = False
    print(f"[selftest] sight face detector: {'ok' if face_ok else 'FAIL'}")
    return ok and face_ok


def main() -> None:
    global TTS_ENGINE, SYSTEM_VOICE, KOKORO_VOICE
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
    ap.add_argument("--no-camera", action="store_true", help="disable F3 look and watching")
    ap.add_argument("--watch", action="store_true",
                    help="start with the webcam watching for you (F5 toggles); "
                         "the camera stays open while watching")
    ap.add_argument("--push-to-talk", action="store_true",
                    help="start with hands-free listening off (F4 toggles)")
    ap.add_argument("--snap", metavar="PATH",
                    help="grab one camera frame, save it, exit (permission check)")
    ap.add_argument("--stt-model", default="base.en",
                    help="tiny.en / base.en / small.en")
    ap.add_argument("--end-silence-ms", type=int, default=700, metavar="MS",
                    help="quiet time before hands-free utterances end (200-2000; default 700)")
    ap.add_argument("--tts-engine", choices=["kokoro", "macos"], default="kokoro",
                    help="local speech voice: British Kokoro (default) or macOS system voice")
    ap.add_argument("--system-voice", default="Samantha",
                    help="installed macOS voice name for --tts-engine macos (default Samantha)")
    ap.add_argument("--kokoro-voice", default="bf_emma",
                    help="Kokoro voice preset (default bf_emma, British English)")
    ap.add_argument("--selftest", action="store_true", help="verify stt/brain/eyes, no mic")
    args = ap.parse_args()

    if not 200 <= args.end_silence_ms <= 2000:
        ap.error("--end-silence-ms must be between 200 and 2000")

    if args.selftest:
        sys.exit(selftest(args.no_brain))

    TTS_ENGINE, SYSTEM_VOICE, KOKORO_VOICE = (
        args.tts_engine, args.system_voice, args.kokoro_voice
    )
    selected_voice = (f" ({KOKORO_VOICE})" if TTS_ENGINE == "kokoro" else
                      f" ({SYSTEM_VOICE})" if TTS_ENGINE == "macos" else "")
    print(f"[voice] {TTS_ENGINE}{selected_voice}", file=sys.stderr)

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
    watcher = None if camera is None else Watcher(camera)
    run(Mic(), Transcriber(args.stt_model), brain, camera,
        ears=Ears(end_silence_ms=args.end_silence_ms), watcher=watcher,
        hands_free=not args.push_to_talk, watch=args.watch)


if __name__ == "__main__":
    main()
