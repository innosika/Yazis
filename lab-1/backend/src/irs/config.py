"""Application configuration.

Every knob the system exposes lives here so that the lab report can state the exact
parameters a given evaluation run used. Settings are read from the environment (or a
local ``.env``) and are immutable for the process lifetime.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["json", "console"]
LogBase = Literal["e", "2", "10"]


class CrawlerSettings(BaseSettings):
    """Politeness and shape of the web crawl (variant 34: «Сеть Интернет»)."""

    model_config = SettingsConfigDict(env_prefix="CRAWLER_")

    user_agent: str = (
        "IRS-Lab1-Crawler/1.0 (+academic coursework; contact: student@university.local)"
    )
    #: Hard ceilings so a runaway crawl cannot exhaust the machine.
    max_pages_per_job: int = 500
    max_depth: int = 3
    #: Per-host politeness. Overridden upward by a robots.txt Crawl-delay directive.
    default_delay_seconds: float = 1.0
    max_concurrency: int = 8
    request_timeout_seconds: float = 15.0
    max_retries: int = 2
    #: Reject responses larger than this before parsing (bytes).
    max_content_bytes: int = 4 * 1024 * 1024
    #: Documents shorter than this after boilerplate removal are not worth indexing.
    min_extracted_chars: int = 400
    #: SimHash Hamming distance at or below which two documents count as near-duplicates.
    near_duplicate_distance: int = 3
    respect_robots_txt: bool = True
    allowed_content_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")


class IndexSettings(BaseSettings):
    """Parameters of the term-weighting scheme."""

    model_config = SettingsConfigDict(env_prefix="INDEX_")

    #: Base of the logarithm in B_i = log(N / P_i) (formula 1.5).
    #:
    #: This is configurable for transparency, not because it changes the ranking: the base
    #: is a constant factor shared by the numerator and the denominator of the normalized
    #: weight w_dk, so it cancels exactly. It *does* scale the unnormalized keyword weights
    #: A_i^j from formula 1.6, which is why the report pins it down.
    log_base: LogBase = "e"
    #: Drop terms occurring in fewer than this many documents (noise/typos). 1 = keep all.
    min_document_frequency: int = 1
    #: Terms appearing in more than this fraction of the collection carry ~no information.
    #: Note B_i = log(N/P_i) already drives these to 0; this is an efficiency cut.
    max_document_frequency_ratio: float = 1.0
    #: spaCy coarse POS tags kept as index terms. Function words are discarded.
    keep_pos_tags: tuple[str, ...] = ("NOUN", "PROPN", "VERB", "ADJ", "ADV", "NUM", "X")
    min_token_length: int = 2
    max_token_length: int = 40
    #: How many terms the "keywords of this document" view shows (ranked by formula 1.6).
    keywords_per_document: int = 20
    #: Rank of the truncated SVD used for the Relevance Lab's latent-semantic projection.
    lsa_components: int = 3
    #: Cap on the vocabulary fed to the SVD, by descending collection frequency.
    lsa_max_terms: int = 20_000

    @computed_field  # type: ignore[prop-decorator]
    @property
    def log_divisor(self) -> float:
        """``math.log(x) / log_divisor`` yields the logarithm in the configured base."""
        return {"e": 1.0, "2": math.log(2.0), "10": math.log(10.0)}[self.log_base]


class SearchSettings(BaseSettings):
    """Defaults for the document-selection module (the variant-34 «AI element»)."""

    model_config = SettingsConfigDict(env_prefix="SEARCH_")

    default_limit: int = 10
    max_limit: int = 100
    #: Length of the snippet exposed on SearchResult, per the PDF's class diagram.
    snippet_chars: int = 300
    #: How many inverted-index candidates to score before truncating to `limit`.
    candidate_pool: int = 1_000
    #: BM25 free parameters (baseline ranker for the arena).
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    #: Reciprocal-rank-fusion constant for the hybrid ranker.
    rrf_k: int = 60
    #: Rocchio relevance-feedback coefficients (alpha*q + beta*rel - gamma*nonrel).
    rocchio_alpha: float = 1.0
    rocchio_beta: float = 0.75
    rocchio_gamma: float = 0.15
    #: Terms retained in the expanded query vector after a feedback round.
    rocchio_max_terms: int = 60
    #: Pseudo-relevance feedback (the `vector_prf` ranker): how many top documents of the
    #: initial vector run are assumed relevant, and how many expansion terms survive.
    prf_feedback_docs: int = 5
    prf_expansion_terms: int = 20


class SemanticSettings(BaseSettings):
    """Dense-embedding ranker. Optional: the system runs fully without it."""

    model_config = SettingsConfigDict(env_prefix="SEMANTIC_")

    enabled: bool = True
    model_name: str = "BAAI/bge-small-en-v1.5"
    dimensions: int = 384
    #: Characters of each document fed to the encoder (the model truncates at 512 tokens).
    max_chars: int = 2_000
    batch_size: int = 32
    cache_dir: str = "/models/fastembed"


class EvalSettings(BaseSettings):
    """Quality-evaluation module."""

    model_config = SettingsConfigDict(env_prefix="EVAL_")

    #: Cutoffs reported for P@k / nDCG@k.
    cutoffs: tuple[int, ...] = (1, 5, 10, 20)
    #: Results retrieved per query when scoring a run.
    run_depth: int = 100
    #: Depth of each ranker's contribution to the judgment pool.
    pool_depth: int = 10
    #: Unjudged documents sampled at random per topic, from outside the pool. If ~0% of
    #: them prove relevant, that is empirical evidence of the pool's near-completeness.
    pool_random_sample: int = 5
    #: Topics selected for judging out of those authored (ROMIP's anti-tuning device:
    #: author many, judge a subset chosen only after every run is frozen).
    judged_topics: int = 25
    #: Ranker that executes each topic's hand-built oracle query. BM25, because the
    #: oracle exists to find what the *vector model's* query misses, so it must not share
    #: that model's binary-query weakness — and because it is the strongest lexical
    #: ranker here, which maximises relevant documents found per judgment spent.
    oracle_ranker: str = "bm25"
    #: Name of the hand-authored topical collection seeded from `seeds/topics.yaml`.
    topical_collection_name: str = "topical (LLM-judged)"
    #: Graded relevance 0..3; this grade and above counts as relevant for binary metrics.
    binary_relevance_threshold: int = 1
    #: Bootstrap resamples for confidence intervals on ranker differences.
    bootstrap_samples: int = 10_000
    random_seed: int = 20_240_229


class AssessorSettings(BaseSettings):
    """The LLM assessor that judges the topical pool.

    Any OpenAI-compatible chat-completions endpoint works. The default is the ``ollama``
    compose service (profile ``llm``), which runs the model locally on the CPU.
    """

    model_config = SettingsConfigDict(env_prefix="ASSESSOR_LLM_")

    base_url: str = "http://ollama:11434/v1"
    model: str = "qwen2.5:3b-instruct"
    #: Ollama ignores the key but the OpenAI client shape requires one.
    api_key: str = "ollama"
    timeout_seconds: float = 180.0
    max_retries: int = 3
    #: Deterministic decoding, so a re-run over the same pool gives the same grades.
    temperature: float = 0.0
    #: Characters of the document shown to the model: a lead plus a query-biased passage.
    #: Bounded because prompt processing dominates CPU inference time.
    max_document_chars: int = 1_500
    #: Bumped whenever the prompt text changes; part of the assessor's identity.
    prompt_version: str = "v1"


class Settings(BaseSettings):
    """Root settings object."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Information Retrieval System"
    environment: Literal["dev", "prod", "test"] = "dev"
    api_prefix: str = "/api"

    # Constructed rather than given as a bare string so the annotation and the default
    # agree; pydantic still validates any value supplied through the environment.
    postgres_dsn: PostgresDsn = PostgresDsn("postgresql+asyncpg://irs:irs@postgres:5432/irs")
    redis_dsn: RedisDsn = RedisDsn("redis://redis:6379/0")

    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False

    log_level: str = "INFO"
    log_format: LogFormat = "console"
    #: Mirror every log record onto a Redis channel so the UI can stream it live.
    log_stream_enabled: bool = True
    log_stream_channel: str = "irs.logs"
    #: Ring buffer of recent records served to a client that has just connected.
    log_stream_backlog: int = 200

    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:8080")

    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    semantic: SemanticSettings = Field(default_factory=SemanticSettings)
    evaluation: EvalSettings = Field(default_factory=EvalSettings)
    assessor: AssessorSettings = Field(default_factory=AssessorSettings)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_postgres_dsn(self) -> str:
        """Alembic drives migrations through the synchronous psycopg/pg8000 path."""
        return str(self.postgres_dsn).replace("+asyncpg", "")

    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide singleton. Cached so env parsing happens exactly once."""
    return Settings()


settings = get_settings()
