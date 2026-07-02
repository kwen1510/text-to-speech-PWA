# Kitten TTS PWA

Static PWA shell for text to speech on a phone plus caching Kitten TTS model files. It is designed for GitHub Pages and uses Cache Storage plus the browser persistent-storage API so downloaded model files survive refreshes and normal app restarts.

The current speaking path uses the browser/device `speechSynthesis` engine, so it works without a server. Quality and offline availability depend on the voices installed on the phone. The Kitten TTS model files are cached separately for a later full ONNX + phonemizer browser integration.

## Local test

```bash
python3 -m http.server 4173
```

Open `http://127.0.0.1:4173`, enter text, press **Speak**, then press **Download model**, refresh, and confirm all model files still show as cached.

## GitHub Pages

Publish the repository root with GitHub Pages. The app uses relative paths, so it works from a project URL such as `https://kwen1510.github.io/text-to-speech-PWA/`.

## Cache behavior

Browsers do not provide an absolute "never delete this" guarantee. This app calls `navigator.storage.persist()` and stores model files in a dedicated Cache Storage bucket. On supported browsers, persistent storage makes eviction much less likely. The app also checks the model cache on every load, so a refresh should immediately show the downloaded files as cached.
