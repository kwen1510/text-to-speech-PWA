# Kitten TTS Render Web App

Single-service Flask app for running real KittenTTS text to speech on Render. Flask serves the mobile web UI and the `/api/tts` endpoint returns generated WAV audio.

This is online synthesis, not offline phone inference. Render Free can run it for personal testing, but idle services spin down and the first request after sleep can be slow.

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
curl -X POST http://127.0.0.1:5000/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from Kitten TTS.","voice":"Bella","speed":1.0}' \
  --output kitten.wav
```

## Render deployment

Create a Render Web Service from this repository. `render.yaml` defines:

- build command: `pip install -r requirements.txt`
- start command: `gunicorn app:app --workers 1 --threads 2 --timeout 180`
- health check: `/healthz`

The service uses one Gunicorn worker so the KittenTTS model is loaded once per process.

## API

`GET /api/voices`

Returns:

```json
{"voices":["Bella","Jasper","Luna","Bruno","Rosie","Hugo","Kiki","Leo"]}
```

`POST /api/tts`

Body:

```json
{"text":"Hello world","voice":"Bella","speed":1.0}
```

Returns `audio/wav`.

Validation:

- text is required
- text is capped by `MAX_TEXT_LENGTH`, default `1000`
- voice must be one of the 8 KittenTTS voices
- speed must be between `0.7` and `1.4`
