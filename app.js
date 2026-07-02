const MODEL_CACHE = "kitten-tts-model-cache-v1";
const APP_CACHE = "kitten-tts-app-cache-v2";

const MODEL_ASSETS = [
  {
    name: "Kitten TTS nano int8 ONNX",
    fileName: "kitten_tts_nano_v0_8.onnx",
    sizeLabel: "24.4 MB",
    url: "https://huggingface.co/KittenML/kitten-tts-nano-0.8-int8/resolve/main/kitten_tts_nano_v0_8.onnx",
  },
  {
    name: "Voice embeddings",
    fileName: "voices.npz",
    sizeLabel: "3.28 MB",
    url: "https://huggingface.co/KittenML/kitten-tts-nano-0.8-int8/resolve/main/voices.npz",
  },
  {
    name: "Model config",
    fileName: "config.json",
    sizeLabel: "688 B",
    url: "https://huggingface.co/KittenML/kitten-tts-nano-0.8-int8/resolve/main/config.json",
  },
];

const els = {
  assetList: document.querySelector("#assetList"),
  clearButton: document.querySelector("#clearButton"),
  connectionStatus: document.querySelector("#connectionStatus"),
  downloadButton: document.querySelector("#downloadButton"),
  pauseButton: document.querySelector("#pauseButton"),
  progressBar: document.querySelector("#progressBar"),
  speakButton: document.querySelector("#speakButton"),
  speechStatus: document.querySelector("#speechStatus"),
  speedInput: document.querySelector("#speedInput"),
  statusText: document.querySelector("#statusText"),
  stopButton: document.querySelector("#stopButton"),
  storageEstimate: document.querySelector("#storageEstimate"),
  textInput: document.querySelector("#textInput"),
  voiceSelect: document.querySelector("#voiceSelect"),
};

let assetStates = new Map();
let voices = [];

init();

async function init() {
  renderAssetList();
  updateConnectionStatus();
  window.addEventListener("online", updateConnectionStatus);
  window.addEventListener("offline", updateConnectionStatus);

  if ("serviceWorker" in navigator) {
    try {
      await navigator.serviceWorker.register("./sw.js");
    } catch (error) {
      setStatus(`Service worker registration failed: ${error.message}`);
    }
  }

  await requestPersistentStorage();
  await refreshCacheState();
  await updateStorageEstimate();

  els.downloadButton.addEventListener("click", downloadModel);
  els.clearButton.addEventListener("click", clearModelCache);
  els.speakButton.addEventListener("click", speakText);
  els.pauseButton.addEventListener("click", togglePause);
  els.stopButton.addEventListener("click", stopSpeaking);

  initSpeech();
}

function initSpeech() {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
    els.speakButton.disabled = true;
    els.pauseButton.disabled = true;
    els.stopButton.disabled = true;
    els.speechStatus.textContent = "This browser does not support built-in text to speech.";
    return;
  }

  loadVoices();
  window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
  els.speechStatus.textContent = "Ready to speak using this device's installed voices.";
}

function loadVoices() {
  voices = window.speechSynthesis.getVoices();
  els.voiceSelect.replaceChildren();

  if (voices.length === 0) {
    const option = document.createElement("option");
    option.textContent = "Default device voice";
    option.value = "";
    els.voiceSelect.append(option);
    return;
  }

  const preferred = voices.find((voice) => voice.lang?.toLowerCase().startsWith("en") && voice.localService)
    || voices.find((voice) => voice.lang?.toLowerCase().startsWith("en"))
    || voices[0];

  for (const voice of voices) {
    const option = document.createElement("option");
    option.value = voice.voiceURI;
    option.textContent = `${voice.name} (${voice.lang})${voice.localService ? " local" : ""}`;
    option.selected = voice.voiceURI === preferred.voiceURI;
    els.voiceSelect.append(option);
  }
}

function speakText() {
  const text = els.textInput.value.trim();
  if (!text) {
    els.speechStatus.textContent = "Enter text before speaking.";
    return;
  }

  if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
    window.speechSynthesis.cancel();
  }

  const utterance = new SpeechSynthesisUtterance(text);
  const selectedVoice = voices.find((voice) => voice.voiceURI === els.voiceSelect.value);
  if (selectedVoice) utterance.voice = selectedVoice;
  utterance.rate = Number(els.speedInput.value);
  utterance.pitch = 1;
  utterance.volume = 1;

  utterance.onstart = () => {
    els.speechStatus.textContent = "Speaking...";
    els.pauseButton.textContent = "Pause";
  };
  utterance.onpause = () => {
    els.speechStatus.textContent = "Paused.";
    els.pauseButton.textContent = "Resume";
  };
  utterance.onresume = () => {
    els.speechStatus.textContent = "Speaking...";
    els.pauseButton.textContent = "Pause";
  };
  utterance.onend = () => {
    els.speechStatus.textContent = "Finished.";
    els.pauseButton.textContent = "Pause";
  };
  utterance.onerror = (event) => {
    els.speechStatus.textContent = `Speech failed: ${event.error || "unknown error"}.`;
  };

  window.speechSynthesis.speak(utterance);
}

function togglePause() {
  if (!window.speechSynthesis.speaking && !window.speechSynthesis.paused) return;

  if (window.speechSynthesis.paused) {
    window.speechSynthesis.resume();
  } else {
    window.speechSynthesis.pause();
  }
}

function stopSpeaking() {
  window.speechSynthesis.cancel();
  els.pauseButton.textContent = "Pause";
  els.speechStatus.textContent = "Stopped.";
}

async function requestPersistentStorage() {
  if (!navigator.storage?.persist) {
    setStatus("This browser does not expose persistent storage. Cached models may still survive refreshes.");
    return false;
  }

  const alreadyPersisted = await navigator.storage.persisted();
  if (alreadyPersisted) {
    setStatus("Persistent storage is already enabled for this PWA.");
    return true;
  }

  const granted = await navigator.storage.persist();
  setStatus(granted
    ? "Persistent storage enabled. The browser should avoid evicting downloaded models."
    : "Persistent storage was not granted yet. The model cache still survives refreshes, but may be evicted under storage pressure.");
  return granted;
}

async function refreshCacheState() {
  const cache = await caches.open(MODEL_CACHE);
  const entries = await Promise.all(MODEL_ASSETS.map(async (asset) => {
    const response = await cache.match(asset.url);
    return [asset.url, Boolean(response)];
  }));
  assetStates = new Map(entries);
  renderAssetList();
  updateProgress();
}

async function downloadModel() {
  els.downloadButton.disabled = true;
  els.clearButton.disabled = true;
  setStatus("Downloading model files...");

  try {
    const cache = await caches.open(MODEL_CACHE);
    let completed = 0;

    for (const asset of MODEL_ASSETS) {
      setStatus(`Downloading ${asset.fileName}...`);
      const request = new Request(asset.url, { mode: "cors" });
      const response = await fetch(request);

      if (!response.ok) {
        throw new Error(`${asset.fileName} failed with HTTP ${response.status}`);
      }

      await cache.put(asset.url, response.clone());
      completed += 1;
      assetStates.set(asset.url, true);
      renderAssetList();
      setProgress((completed / MODEL_ASSETS.length) * 100);
    }

    await updateStorageEstimate();
    setStatus("Model files are cached. Refresh the page or open the PWA offline to verify.");
  } catch (error) {
    setStatus(`Download failed: ${error.message}`);
  } finally {
    els.downloadButton.disabled = false;
    els.clearButton.disabled = false;
    await refreshCacheState();
  }
}

async function clearModelCache() {
  els.clearButton.disabled = true;
  await caches.delete(MODEL_CACHE);
  setStatus("Model cache cleared.");
  setProgress(0);
  await refreshCacheState();
  await updateStorageEstimate();
  els.clearButton.disabled = false;
}

function renderAssetList() {
  els.assetList.replaceChildren(...MODEL_ASSETS.map((asset) => {
    const cached = assetStates.get(asset.url) === true;
    const li = document.createElement("li");
    li.className = "asset-row";
    li.innerHTML = `
      <div>
        <div class="asset-name"></div>
        <div class="asset-meta"></div>
      </div>
      <span class="asset-state ${cached ? "cached" : "missing"}"></span>
    `;
    li.querySelector(".asset-name").textContent = asset.name;
    li.querySelector(".asset-meta").textContent = `${asset.fileName} · ${asset.sizeLabel}`;
    li.querySelector(".asset-state").textContent = cached ? "Cached" : "Missing";
    return li;
  }));
}

function updateProgress() {
  const cachedCount = MODEL_ASSETS.filter((asset) => assetStates.get(asset.url)).length;
  setProgress((cachedCount / MODEL_ASSETS.length) * 100);
  if (cachedCount === MODEL_ASSETS.length) {
    setStatus("All model files are cached.");
  } else if (cachedCount === 0) {
    setStatus("Model files are not cached yet.");
  } else {
    setStatus(`${cachedCount} of ${MODEL_ASSETS.length} model files are cached.`);
  }
}

async function updateStorageEstimate() {
  if (!navigator.storage?.estimate) {
    els.storageEstimate.textContent = "Storage unavailable";
    return;
  }

  const estimate = await navigator.storage.estimate();
  const usage = formatBytes(estimate.usage || 0);
  const quota = formatBytes(estimate.quota || 0);
  els.storageEstimate.textContent = `${usage} used of ${quota}`;
}

function updateConnectionStatus() {
  els.connectionStatus.textContent = navigator.onLine ? "Online" : "Offline";
}

function setStatus(message) {
  els.statusText.textContent = message;
}

function setProgress(value) {
  els.progressBar.style.width = `${Math.max(0, Math.min(100, value))}%`;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export { APP_CACHE, MODEL_ASSETS, MODEL_CACHE };
