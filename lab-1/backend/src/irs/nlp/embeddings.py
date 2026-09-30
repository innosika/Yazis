"""Dense text embeddings.

Backs the semantic ranker. FastEmbed is used rather than sentence-transformers because it
runs the model through ONNX Runtime and therefore does not pull in PyTorch — the
difference between a ~150 MB image layer and a ~2.5 GB one, which matters for something
that has to be built and shipped as a container.

The default model is BAAI/bge-small-en-v1.5: 384 dimensions, English, and small enough
to embed a few hundred documents in seconds on a CPU.

Embedding is synchronous and CPU-bound, so every public entry point here is an async
wrapper that hands the work to a thread. Left on the event loop it would stall the API
and, in the worker, stop the broker's connection being read.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from irs.config import settings
from irs.logging import get_logger

if TYPE_CHECKING:
    from fastembed import TextEmbedding

log = get_logger("irs.nlp.embeddings")


class Embedder:
    """Lazily-loaded, thread-safe embedding model."""

    def __init__(self) -> None:
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    @property
    def dimensions(self) -> int:
        return settings.semantic.dimensions

    @property
    def model_name(self) -> str:
        return settings.semantic.model_name

    def _load(self) -> TextEmbedding:
        from fastembed import TextEmbedding

        model = TextEmbedding(
            model_name=settings.semantic.model_name,
            cache_dir=settings.semantic.cache_dir,
        )
        log.info(
            "embedding_model_loaded",
            model=settings.semantic.model_name,
            dimensions=settings.semantic.dimensions,
            cache_dir=settings.semantic.cache_dir,
        )
        return model

    @property
    def model(self) -> TextEmbedding:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load()
        return self._model

    # ------------------------------------------------------------------- sync ----

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch. Blocking — call through the async wrappers instead."""
        if not texts:
            return []
        vectors = list(self.model.embed(texts, batch_size=settings.semantic.batch_size))
        return [vector.tolist() for vector in vectors]

    # ------------------------------------------------------------------ async ----

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts off the event loop."""
        if not texts:
            return []
        return await asyncio.to_thread(self.embed_sync, texts)

    async def embed_one(self, text: str) -> list[float] | None:
        vectors = await self.embed([text])
        return vectors[0] if vectors else None

    async def embed_document(self, title: str, text: str) -> list[float] | None:
        """Embed a document.

        Only the opening ``max_chars`` are encoded. The model truncates at 512 tokens
        regardless, so feeding it a whole Wikipedia article would spend time producing a
        vector for text the model never sees. The title is prepended because it is the
        most informative sentence a document has and would otherwise fall outside the
        window for any long page.
        """
        head = f"{title}. {text}"[: settings.semantic.max_chars].strip()
        return await self.embed_one(head) if head else None

    async def warm(self) -> None:
        await self.embed(["warm up the encoder"])


embedder = Embedder()
