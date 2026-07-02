from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kitten_runtime import download_from_huggingface


def main() -> None:
    model_name = os.getenv("KITTEN_MODEL_NAME", "KittenML/kitten-tts-nano-0.8")
    fallback_name = os.getenv("KITTEN_FALLBACK_MODEL_NAME", "KittenML/kitten-tts-mini-0.8")
    cache_dir = os.getenv("KITTEN_CACHE_DIR", ".cache/huggingface")

    try:
        download_from_huggingface(model_name, cache_dir=cache_dir)
        print(f"Preloaded {model_name} into {cache_dir}")
    except Exception:
        if fallback_name == model_name:
            raise
        download_from_huggingface(fallback_name, cache_dir=cache_dir)
        print(f"Preloaded fallback {fallback_name} into {cache_dir}")


if __name__ == "__main__":
    main()
