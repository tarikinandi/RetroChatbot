import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DEFAULT_MODEL = "gemini-3.8-flash"


@dataclass
class Settings:
    api_key: str
    model: str
    data_dir: Path


def get_settings() -> Settings:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY ortam degiskeni bulunamadi. .env dosyasini kontrol edin."
        )
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    return Settings(api_key=api_key, model=model, data_dir=DATA_DIR)
