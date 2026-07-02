const els = {
  audioPlayer: document.querySelector("#audioPlayer"),
  downloadLink: document.querySelector("#downloadLink"),
  form: document.querySelector("#ttsForm"),
  generateButton: document.querySelector("#generateButton"),
  serviceStatus: document.querySelector("#serviceStatus"),
  speedInput: document.querySelector("#speedInput"),
  speedValue: document.querySelector("#speedValue"),
  statusText: document.querySelector("#statusText"),
  textInput: document.querySelector("#textInput"),
  voiceSelect: document.querySelector("#voiceSelect"),
};

let currentAudioUrl = null;

init();

function init() {
  els.form.addEventListener("submit", generateSpeech);
  els.speedInput.addEventListener("input", updateSpeedValue);
  updateSpeedValue();
  checkHealth();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {
      // The app still works without PWA asset caching.
    });
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/healthz", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    els.serviceStatus.textContent = data.model_loaded ? "Model ready" : "Online";
  } catch {
    els.serviceStatus.textContent = "Offline";
  }
}

async function generateSpeech(event) {
  event.preventDefault();

  const text = els.textInput.value.trim();
  const voice = els.voiceSelect.value;
  const speed = Number(els.speedInput.value);

  if (!text) {
    setStatus("Enter text before generating speech.", true);
    return;
  }

  setLoading(true);
  setStatus("Generating KittenTTS audio...");
  revokeCurrentAudio();

  try {
    const response = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, speed }),
    });

    if (!response.ok) {
      let message = `Request failed with HTTP ${response.status}.`;
      try {
        const errorBody = await response.json();
        if (errorBody.error) message = errorBody.error;
      } catch {
        // Keep the HTTP message if the server did not return JSON.
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    currentAudioUrl = URL.createObjectURL(blob);
    els.audioPlayer.src = currentAudioUrl;
    els.downloadLink.href = currentAudioUrl;
    els.downloadLink.download = `kitten-${voice.toLowerCase()}-${speed.toFixed(2)}.wav`;
    els.downloadLink.classList.remove("disabled");
    els.downloadLink.removeAttribute("aria-disabled");
    setStatus("Audio generated.");
    await els.audioPlayer.play().catch(() => {
      setStatus("Audio generated. Tap play to listen.");
    });
    checkHealth();
  } catch (error) {
    setStatus(error.message || "Speech generation failed.", true);
    els.audioPlayer.removeAttribute("src");
    els.downloadLink.classList.add("disabled");
    els.downloadLink.setAttribute("aria-disabled", "true");
    els.downloadLink.removeAttribute("href");
  } finally {
    setLoading(false);
  }
}

function updateSpeedValue() {
  els.speedValue.textContent = Number(els.speedInput.value).toFixed(2);
}

function setLoading(isLoading) {
  els.generateButton.disabled = isLoading;
  els.generateButton.textContent = isLoading ? "Generating..." : "Generate speech";
}

function setStatus(message, isError = false) {
  els.statusText.textContent = message;
  els.statusText.classList.toggle("error", isError);
}

function revokeCurrentAudio() {
  if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
  currentAudioUrl = null;
}
