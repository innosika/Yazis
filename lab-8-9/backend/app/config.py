"""Runtime configuration, read from the environment (and `.env` during local runs)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    models_dir: Path = Path("/models")
    log_level: str = "INFO"

    groq_api_key: str = ""
    groq_asr_model: str = "whisper-large-v3-turbo"
    groq_llm_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    tts_threads: int = 6
    tts_cache_limit_mb: int = 2048
    # Tests and the frontend dev loop run without the 1 GB of speech models.
    fake_engines: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lector.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def kokoro_repo(self) -> str:
        return "hexgrad/Kokoro-82M"

    @property
    def parakeet_dir(self) -> Path:
        return self.models_dir / "parakeet-tdt-0.6b-v3"

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
