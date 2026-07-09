# Pocket TTS Render Web App

Single-service Flask app for running Kyutai Pocket-TTS from a mobile-friendly PWA shell. Flask serves the UI and `/api/tts` returns generated WAV audio.

This is online server-side synthesis, not offline phone inference. The model stays loaded in the Python process while the service is awake.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --debug
```

Open `http://127.0.0.1:5000`.

Useful checks:

```bash
curl http://127.0.0.1:5000/healthz
curl http://127.0.0.1:5000/api/voices
curl -X POST http://127.0.0.1:5000/api/warmup
curl -X POST http://127.0.0.1:5000/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from Pocket TTS.","voice":"alba"}' \
  --output pocket.wav
```

## Render deployment

Create a Render Web Service from this repository. `render.yaml` defines:

- build command: `pip install -r requirements.txt && python scripts/preload_model.py`
- start command: `gunicorn app:app`
- health check: `/healthz`

The service uses `gunicorn.conf.py` to set one worker, two threads, and a 180 second timeout. The build step loads the default Pocket-TTS English model and the default `alba` voice once, so Hugging Face files are cached before runtime.

Render Free may still be slow or memory-constrained because Pocket-TTS uses PyTorch CPU. For fast personal use, a Mac mini or a paid CPU instance is a better target than Render Free.

## API

`GET /api/voices`

Returns:

```json
{"voices":["alba","anna","charles","mary","michael","vera","george","jane"],"default_voice":"alba"}
```

`POST /api/warmup`

Loads the model and default voice state into memory.

`POST /api/tts`

Body:

```json
{"text":"Hello world","voice":"alba"}
```

Returns `audio/wav`.

Validation:

- text is required
- text is capped by `MAX_TEXT_LENGTH`, default `1000`
- voice must be one of the configured Pocket-TTS voices

## Configuration

- `POCKET_TTS_LANGUAGE`: default `english`
- `POCKET_TTS_DEFAULT_VOICE`: default `alba`
- `POCKET_TTS_QUANTIZE`: default `0`; set `1` only after adding compatible quantization dependencies
- `MAX_TEXT_LENGTH`: default `1000`
- `HF_HOME`: default `.cache/huggingface`
- `XDG_CACHE_HOME`: default `.cache`
