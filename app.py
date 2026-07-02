from __future__ import annotations

import io
import os
import threading
import time
import wave
from typing import Any

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file


SAMPLE_RATE = 24_000
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "1000"))
DEFAULT_MODEL_NAME = os.getenv("KITTEN_MODEL_NAME", "KittenML/kitten-tts-nano-0.8")
FALLBACK_MODEL_NAME = os.getenv("KITTEN_FALLBACK_MODEL_NAME", "KittenML/kitten-tts-mini-0.8")
MODEL_CACHE_DIR = os.getenv("KITTEN_CACHE_DIR", ".cache/huggingface")
VOICE_NAMES = ("Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo")


app = Flask(__name__)

_model: Any | None = None
_model_name: str | None = None
_model_lock = threading.Lock()


def get_tts_model() -> Any:
    global _model, _model_name

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        from kitten_runtime import KittenTTS

        try:
            _model = KittenTTS(DEFAULT_MODEL_NAME, cache_dir=MODEL_CACHE_DIR)
            _model_name = DEFAULT_MODEL_NAME
        except Exception:
            if FALLBACK_MODEL_NAME == DEFAULT_MODEL_NAME:
                raise
            _model = KittenTTS(FALLBACK_MODEL_NAME, cache_dir=MODEL_CACHE_DIR)
            _model_name = FALLBACK_MODEL_NAME

        return _model


def validate_tts_payload(payload: Any) -> tuple[str, str, float] | tuple[None, None, None]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be JSON.")

    text = str(payload.get("text", "")).strip()
    voice = str(payload.get("voice", "Bella")).strip()

    try:
        speed = float(payload.get("speed", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Speed must be a number.") from exc

    if not text:
        raise ValueError("Text is required.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text must be {MAX_TEXT_LENGTH} characters or fewer.")
    if voice not in VOICE_NAMES:
        raise ValueError("Voice must be one of the supported KittenTTS voices.")
    if speed < 0.7 or speed > 1.4:
        raise ValueError("Speed must be between 0.7 and 1.4.")

    return text, voice, speed


def audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> io.BytesIO:
    samples = np.asarray(audio, dtype=np.float32)
    samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    buffer.seek(0)
    return buffer


@app.get("/")
def index():
    return render_template(
        "index.html",
        voices=VOICE_NAMES,
        max_text_length=MAX_TEXT_LENGTH,
    )


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "ok": True,
            "model_loaded": _model is not None,
            "model_name": _model_name,
            "sample_rate": SAMPLE_RATE,
        }
    )


@app.get("/api/voices")
def voices():
    return jsonify({"voices": list(VOICE_NAMES)})


@app.post("/api/tts")
def tts():
    start_time = time.perf_counter()
    load_done = start_time
    generate_done = start_time
    try:
        text, voice, speed = validate_tts_payload(request.get_json(silent=True))
        model = get_tts_model()
        load_done = time.perf_counter()
        audio = model.generate(text, voice=voice, speed=speed)
        generate_done = time.perf_counter()
        wav_buffer = audio_to_wav_bytes(audio)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("KittenTTS synthesis failed")
        return jsonify({"error": f"KittenTTS synthesis failed: {exc}"}), 500

    filename = f"kitten-{voice.lower()}-{speed:.2f}.wav"
    response = send_file(
        wav_buffer,
        mimetype="audio/wav",
        as_attachment=False,
        download_name=filename,
    )
    response.headers["Cache-Control"] = "no-store"
    total_done = time.perf_counter()
    response.headers["Server-Timing"] = (
        f"load;dur={(load_done - start_time) * 1000:.1f}, "
        f"generate;dur={(generate_done - load_done) * 1000:.1f}, "
        f"wav;dur={(total_done - generate_done) * 1000:.1f}"
    )
    app.logger.info(
        "tts timing text_len=%s voice=%s load=%.3fs generate=%.3fs wav=%.3fs total=%.3fs",
        len(text),
        voice,
        load_done - start_time,
        generate_done - load_done,
        total_done - generate_done,
        total_done - start_time,
    )
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
