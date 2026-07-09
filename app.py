from __future__ import annotations

import io
import os
import threading
import time
import wave
import gc
from typing import Any

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file


os.environ.setdefault("HF_HOME", ".cache/huggingface")
os.environ.setdefault("XDG_CACHE_HOME", ".cache")
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "300"))
POCKET_LANGUAGE = os.getenv("POCKET_TTS_LANGUAGE", "english")
POCKET_QUANTIZE = os.getenv("POCKET_TTS_QUANTIZE", "1") == "1"
DEFAULT_VOICE = os.getenv("POCKET_TTS_DEFAULT_VOICE", "alba")
VOICE_NAMES = (
    "alba",
    "anna",
    "charles",
    "mary",
    "michael",
    "vera",
    "george",
    "jane",
)


app = Flask(__name__)

_model: Any | None = None
_model_lock = threading.Lock()
_voice_states: dict[str, Any] = {}
_voice_lock = threading.Lock()
_runtime_lock = threading.Lock()
_generation_lock = threading.Lock()


def get_tts_model() -> Any:
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        from pocket_tts import TTSModel

        _model = TTSModel.load_model(language=POCKET_LANGUAGE, quantize=POCKET_QUANTIZE)
        gc.collect()
        return _model


def get_voice_state(voice: str) -> Any:
    if voice in _voice_states:
        return _voice_states[voice]

    with _voice_lock:
        if voice in _voice_states:
            return _voice_states[voice]

        model = get_tts_model()
        _voice_states[voice] = model.get_state_for_audio_prompt(voice)
        return _voice_states[voice]


def validate_tts_payload(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be JSON.")

    text = str(payload.get("text", "")).strip()
    voice = str(payload.get("voice", DEFAULT_VOICE)).strip().lower()

    if not text:
        raise ValueError("Text is required.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text must be {MAX_TEXT_LENGTH} characters or fewer.")
    if voice not in VOICE_NAMES:
        raise ValueError("Voice must be one of the supported Pocket-TTS voices.")

    return text, voice


def audio_to_wav_bytes(audio: Any, sample_rate: int) -> io.BytesIO:
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()

    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
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
        default_voice=DEFAULT_VOICE,
        max_text_length=MAX_TEXT_LENGTH,
    )


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "ok": True,
            "engine": "pocket-tts",
            "model_loaded": _model is not None,
            "language": POCKET_LANGUAGE,
            "quantize": POCKET_QUANTIZE,
            "sample_rate": _model.sample_rate if _model is not None else None,
            "loaded_voices": sorted(_voice_states),
        }
    )


@app.get("/api/voices")
def voices():
    return jsonify({"voices": list(VOICE_NAMES), "default_voice": DEFAULT_VOICE})


@app.post("/api/warmup")
def warmup():
    start_time = time.perf_counter()
    try:
        with _runtime_lock:
            model = get_tts_model()
            get_voice_state(DEFAULT_VOICE)
    except Exception as exc:
        app.logger.exception("Pocket-TTS warmup failed")
        return jsonify({"error": f"Pocket-TTS warmup failed: {exc}"}), 500

    return jsonify(
        {
            "ok": True,
            "engine": "pocket-tts",
            "language": POCKET_LANGUAGE,
            "sample_rate": model.sample_rate,
            "voice": DEFAULT_VOICE,
            "elapsed_seconds": round(time.perf_counter() - start_time, 3),
        }
    )


@app.post("/api/tts")
def tts():
    start_time = time.perf_counter()
    model_done = start_time
    voice_done = start_time
    generate_done = start_time
    try:
        text, voice = validate_tts_payload(request.get_json(silent=True))
        with _runtime_lock:
            model = get_tts_model()
            model_done = time.perf_counter()
            voice_state = get_voice_state(voice)
            voice_done = time.perf_counter()
            with _generation_lock:
                audio = model.generate_audio(voice_state, text)
            generate_done = time.perf_counter()
        wav_buffer = audio_to_wav_bytes(audio, model.sample_rate)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Pocket-TTS synthesis failed")
        return jsonify({"error": f"Pocket-TTS synthesis failed: {exc}"}), 500

    filename = f"pocket-{voice}.wav"
    response = send_file(
        wav_buffer,
        mimetype="audio/wav",
        as_attachment=False,
        download_name=filename,
    )
    response.headers["Cache-Control"] = "no-store"
    total_done = time.perf_counter()
    response.headers["Server-Timing"] = (
        f"model;dur={(model_done - start_time) * 1000:.1f}, "
        f"voice;dur={(voice_done - model_done) * 1000:.1f}, "
        f"generate;dur={(generate_done - voice_done) * 1000:.1f}, "
        f"wav;dur={(total_done - generate_done) * 1000:.1f}"
    )
    app.logger.info(
        "tts timing engine=pocket text_len=%s voice=%s model=%.3fs voice_state=%.3fs "
        "generate=%.3fs wav=%.3fs total=%.3fs",
        len(text),
        voice,
        model_done - start_time,
        voice_done - model_done,
        generate_done - voice_done,
        total_done - generate_done,
        total_done - start_time,
    )
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
