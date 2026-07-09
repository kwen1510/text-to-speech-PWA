from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("HF_HOME", ".cache/huggingface")
os.environ.setdefault("XDG_CACHE_HOME", ".cache")


def main() -> None:
    from pocket_tts import TTSModel

    language = os.getenv("POCKET_TTS_LANGUAGE", "english")
    default_voice = os.getenv("POCKET_TTS_DEFAULT_VOICE", "alba")
    quantize = os.getenv("POCKET_TTS_QUANTIZE", "0") == "1"

    model = TTSModel.load_model(language=language, quantize=quantize)
    model.get_state_for_audio_prompt(default_voice)
    print(
        f"Preloaded Pocket-TTS language={language} voice={default_voice} "
        f"sample_rate={model.sample_rate}"
    )


if __name__ == "__main__":
    main()
