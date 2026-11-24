"""Settings, read from environment at call time (so tests can override)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:  # load SolarTrack/.env if present (real environment variables still win)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def database_url() -> str:
    # MySQL example: mysql+pymysql://user:pass@localhost:3306/solar_monitor
    return os.getenv("DATABASE_URL") or f"sqlite:///{ROOT / 'dev.db'}"


def upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_DIR") or ROOT / "uploads")


def extraction_mode() -> str:
    return os.getenv("EXTRACTION_MODE") or "gemini"  # "gemini" | "mock"


def gemini_model() -> str:
    # Model names change often: check Google's current list and set GEMINI_MODEL.
    return os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"


def gemini_models() -> list[str]:
    """Main model first, then GEMINI_FALLBACK_MODELS (comma separated), no duplicates."""
    models = [gemini_model()]
    fallback_str = os.getenv("GEMINI_FALLBACK_MODELS")
    fallbacks = fallback_str.split(",") if fallback_str is not None else ["gemini-2.5-flash-lite"]
    for m in fallbacks:
        m = m.strip()
        if m and m not in models:
            models.append(m)
    return models
