from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import phonemizer
from huggingface_hub import hf_hub_download

try:
    import espeakng_loader

    os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", espeakng_loader.get_library_path())
    os.environ.setdefault("PHONEMIZER_ESPEAK_DATA_PATH", espeakng_loader.get_data_path())
except Exception:
    # Phonemizer can still use system eSpeak if the bundled loader is unavailable.
    pass


def basic_english_tokenize(text: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", text)


def ensure_punctuation(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in ".!?,;:":
        return text + ","
    return text


def chunk_text(text: str, max_len: int = 400) -> list[str]:
    sentences = re.split(r"[.!?]+", text)
    chunks: list[str] = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) <= max_len:
            chunks.append(ensure_punctuation(sentence))
            continue

        current = ""
        for word in sentence.split():
            if len(current) + len(word) + 1 <= max_len:
                current = f"{current} {word}".strip()
            else:
                if current:
                    chunks.append(ensure_punctuation(current))
                current = word
        if current:
            chunks.append(ensure_punctuation(current))

    return chunks


class TextCleaner:
    def __init__(self) -> None:
        pad = "$"
        punctuation = ';:,.!?¡¿—…"«»"" '
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        letters_ipa = "ɑɐɒæɓʙβɔɕçɗɖðʤəɘɚɛɜɝɞɟʄɡɠɢʛɦɧħɥʜɨɪʝɭɬɫɮʟɱɯɰŋɳɲɴøɵɸθœɶʘɹɺɾɻʀʁɽʂʃʈʧʉʊʋⱱʌɣɤʍχʎʏʑʐʒʔʡʕʢǀǁǂǃˈˌːˑʼʴʰʱʲʷˠˤ˞↓↑→↗↘'̩'ᵻ"
        symbols = [pad] + list(punctuation) + list(letters) + list(letters_ipa)
        self.word_index_dictionary = {symbol: index for index, symbol in enumerate(symbols)}

    def __call__(self, text: str) -> list[int]:
        return [self.word_index_dictionary[char] for char in text if char in self.word_index_dictionary]


class KittenOnnxModel:
    def __init__(
        self,
        model_path: str | Path,
        voices_path: str | Path,
        speed_priors: dict[str, float] | None = None,
        voice_aliases: dict[str, str] | None = None,
    ) -> None:
        self.model_path = str(model_path)
        self.voices = np.load(voices_path)
        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session_options.intra_op_num_threads = int(os.getenv("ORT_INTRA_OP_THREADS", "1"))
        session_options.inter_op_num_threads = int(os.getenv("ORT_INTER_OP_THREADS", "1"))
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            self.model_path,
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self.phonemizer = phonemizer.backend.EspeakBackend(
            language="en-us",
            preserve_punctuation=True,
            with_stress=True,
        )
        self.text_cleaner = TextCleaner()
        self.speed_priors = speed_priors or {}
        self.voice_aliases = voice_aliases or {}
        self.available_voices = [
            "expr-voice-2-m",
            "expr-voice-2-f",
            "expr-voice-3-m",
            "expr-voice-3-f",
            "expr-voice-4-m",
            "expr-voice-4-f",
            "expr-voice-5-m",
            "expr-voice-5-f",
        ]
        self.all_voice_names = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]

    def _prepare_inputs(self, text: str, voice: str, speed: float) -> dict[str, np.ndarray]:
        if voice in self.voice_aliases:
            voice = self.voice_aliases[voice]

        if voice not in self.available_voices:
            raise ValueError(f"Voice '{voice}' not available.")

        if voice in self.speed_priors:
            speed = speed * self.speed_priors[voice]

        phonemes_list = self.phonemizer.phonemize([text])
        phonemes = " ".join(basic_english_tokenize(phonemes_list[0]))
        tokens = self.text_cleaner(phonemes)
        tokens.insert(0, 0)
        tokens.append(10)
        tokens.append(0)

        input_ids = np.array([tokens], dtype=np.int64)
        ref_id = min(len(text), self.voices[voice].shape[0] - 1)
        ref_s = self.voices[voice][ref_id : ref_id + 1]

        return {
            "input_ids": input_ids,
            "style": ref_s,
            "speed": np.array([speed], dtype=np.float32),
        }

    def generate_single_chunk(self, text: str, voice: str, speed: float) -> np.ndarray:
        outputs = self.session.run(None, self._prepare_inputs(text, voice, speed))
        return outputs[0][..., :-5000]

    def generate(self, text: str, voice: str, speed: float) -> np.ndarray:
        chunks = [self.generate_single_chunk(text_chunk, voice, speed) for text_chunk in chunk_text(text)]
        if not chunks:
            return np.zeros((1, 0), dtype=np.float32)
        return np.concatenate(chunks, axis=-1)


class KittenTTS:
    def __init__(self, model_name: str = "KittenML/kitten-tts-nano-0.8", cache_dir: str | None = None) -> None:
        repo_id = model_name if "/" in model_name else f"KittenML/{model_name}"
        self.model = download_from_huggingface(repo_id, cache_dir)

    @property
    def available_voices(self) -> list[str]:
        return self.model.all_voice_names

    def generate(self, text: str, voice: str = "Bella", speed: float = 1.0) -> np.ndarray:
        return self.model.generate(text, voice, speed)


def download_from_huggingface(repo_id: str, cache_dir: str | None = None) -> KittenOnnxModel:
    config_path = hf_hub_download(repo_id=repo_id, filename="config.json", cache_dir=cache_dir)
    with open(config_path, "r", encoding="utf-8") as file:
        config: dict[str, Any] = json.load(file)

    if config.get("type") not in ["ONNX1", "ONNX2"]:
        raise ValueError("Unsupported KittenTTS model type.")

    model_path = hf_hub_download(repo_id=repo_id, filename=config["model_file"], cache_dir=cache_dir)
    voices_path = hf_hub_download(repo_id=repo_id, filename=config["voices"], cache_dir=cache_dir)

    return KittenOnnxModel(
        model_path=model_path,
        voices_path=voices_path,
        speed_priors=config.get("speed_priors", {}),
        voice_aliases=config.get("voice_aliases", {}),
    )
