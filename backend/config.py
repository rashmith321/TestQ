"""Runtime configuration, read from environment variables with safe defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("LCPA_OUTPUT_DIR", BASE_DIR / "output")))
    request_timeout: float = float(os.getenv("LCPA_REQUEST_TIMEOUT", "15"))
    max_retries: int = int(os.getenv("LCPA_MAX_RETRIES", "3"))
    # Minimum delay between two requests to LeetCode (politeness / rate limiting).
    min_request_interval: float = float(os.getenv("LCPA_MIN_REQUEST_INTERVAL", "0.8"))
    # Recent-activity probing: first batch size, growth factor and hard ceiling.
    activity_start_limit: int = int(os.getenv("LCPA_ACTIVITY_START_LIMIT", "20"))
    activity_max_limit: int = int(os.getenv("LCPA_ACTIVITY_MAX_LIMIT", "100"))
    activity_max_batches: int = int(os.getenv("LCPA_ACTIVITY_MAX_BATCHES", "4"))
    difficulty_batch_size: int = int(os.getenv("LCPA_DIFFICULTY_BATCH_SIZE", "10"))
    save_raw: bool = _env_bool("LCPA_SAVE_RAW", True)
    # Optional Playwright fallback when the plain HTTP client gets a non-JSON page.
    browser_fallback: bool = _env_bool("LCPA_BROWSER_FALLBACK", False)
    cors_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.getenv("LCPA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    )


settings = Settings()
