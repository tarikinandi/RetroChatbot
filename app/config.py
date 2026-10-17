import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Ordered fallback list; the *-latest names are Google's moving aliases.
DEFAULT_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
)
DEFAULT_MODEL = DEFAULT_MODELS[0]


@dataclass
class Settings:
    api_key: str
    model: str
    data_dir: Path
    models: tuple[str, ...] = ()


def get_models() -> list[str]:
    """GEMINI_MODEL (legacy, first) + GEMINI_MODELS, defaults when no list is given. No key needed."""
    names: list[str] = []
    single = os.environ.get("GEMINI_MODEL", "").strip()
    if single:
        names.append(single)
    listed = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",")]
    # Without an explicit list, a lone GEMINI_MODEL still gets the defaults as
    # fallbacks so one stale name can never take the whole demo down.
    names += [m for m in listed if m] or list(DEFAULT_MODELS)
    seen: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def get_settings() -> Settings:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY ortam degiskeni bulunamadi. .env dosyasini kontrol edin."
        )
    models = get_models()
    return Settings(
        api_key=api_key, model=models[0], data_dir=DATA_DIR, models=tuple(models)
    )
