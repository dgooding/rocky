#!/usr/bin/env python3
"""Persistent local MLX worker for Rocky's Drama 3 voice."""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import sys
import traceback
import wave

import numpy as np


def wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    pcm = np.clip(np.rint(audio * 32767), -32768, 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text", required=True)
    args = parser.parse_args()

    try:
        with contextlib.redirect_stdout(sys.stderr):
            from mlx_audio.tts.utils import load_model
            model = load_model(args.model)
    except Exception as error:
        print(f"Could not load local Drama 3 model: {error}", file=sys.stderr)
        return 1

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("shutdown"):
                break
            text = request["text"]
            chunks = []
            with contextlib.redirect_stdout(sys.stderr):
                for result in model.generate(
                    text=text,
                    ref_audio=args.ref_audio,
                    ref_text=args.ref_text,
                    max_tokens=256,
                    stream=True,
                    streaming_interval=0.32,
                    first_chunk_frames=4,
                    temperature=0.7,
                    top_p=0.7,
                    top_k=30,
                ):
                    audio = np.asarray(result.audio)
                    if audio.size:
                        chunks.append(audio)
            if not chunks:
                raise RuntimeError("Drama 3 produced no speech audio")
            audio_bytes = wav_bytes(np.concatenate(chunks), model.sample_rate)
            response = {"audio": base64.b64encode(audio_bytes).decode("ascii")}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            response = {"error": str(error)}
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
