"""Runtime settings, read once at import time from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql+asyncpg://mt:mt@localhost:5434/mt"
    data_dir: Path = Path("/data")
    log_level: str = "INFO"

    spacy_model: str = "en_core_web_md"

    # Automatic dictionary replenishment: the Wiktionary source is optional so the
    # system stays usable with no network at all.
    enrich_wiktionary_enabled: bool = True
    wiktionary_api: str = "https://en.wiktionary.org/w/api.php"
    wiktionary_user_agent: str = "YazisLab4-MT/1.0 (educational machine-translation project)"
    wiktionary_timeout_s: float = 8.0

    # Translation-memory match thresholds, expressed as trigram similarity.
    tm_exact_threshold: float = 0.98
    tm_fuzzy_threshold: float = 0.70
    tm_max_candidates: int = 5

    # Safety valve: a pasted novel would block the event loop for minutes.
    max_input_chars: int = 60_000

    @property
    def dictionary_seed(self) -> Path:
        return self.data_dir / "dictionary" / "eng-rus.jsonl.gz"

    @property
    def samples_dir(self) -> Path:
        return self.data_dir / "samples"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
