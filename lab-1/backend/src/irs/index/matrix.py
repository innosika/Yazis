"""The term–document matrix (formula 1.7) and its latent-semantic decomposition.

The assignment models the collection as an `N × D` matrix `L` whose rows are document
images. This module materialises exactly that matrix — sparse, with the normalised weights
`w_dk` as entries — and decomposes it with a truncated SVD (`L ≈ U Σ Vᵀ`), which is
latent semantic analysis. Keeping only three components projects every document to a
point in 3-D and gives the Relevance Lab something to draw.

Two things are stored so the picture stays consistent:

* the projections `U Σ` of every document, and
* the **basis** `Vᵀ` with the singular values — because a *query* must be projected into
  the same space (`q_3d = q · V`) without moving the documents, and so must an expanded
  Rocchio query. Nothing is refitted per request.

Conventions that make a rebuild reproducible: singular values are returned descending (
``svds`` gives them ascending), the sign of each basis row is normalised so its largest
coordinate is positive (SVD signs are otherwise arbitrary), and ARPACK is seeded.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import svds
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import LsaModel, LsaProjection, Posting, Term
from irs.index.builder import get_collection_stat
from irs.logging import Stopwatch, get_logger

log = get_logger("irs.index.matrix")

Array = npt.NDArray[np.float64]


@dataclass(slots=True)
class SparseTfidf:
    """Matrix 1.7 with `w_dk` entries: rows = documents, columns = reduced vocabulary."""

    document_ids: list[int]
    term_ids: list[int]
    matrix: Any  # scipy.sparse.csr_matrix, shape (len(document_ids), len(term_ids))

    @property
    def column_of_term(self) -> dict[int, int]:
        return {term_id: column for column, term_id in enumerate(self.term_ids)}


async def load_matrix(session: AsyncSession, max_terms: int | None = None) -> SparseTfidf:
    """Read the postings into a sparse matrix over the ``max_terms`` most frequent terms."""
    max_terms = settings.index.lsa_max_terms if max_terms is None else max_terms

    term_ids = [
        int(term_id)
        for (term_id,) in (
            await session.execute(
                select(Term.id)
                .where(Term.document_frequency > 0)
                .order_by(Term.collection_frequency.desc(), Term.id)
                .limit(max_terms)
            )
        ).all()
    ]
    column = {term_id: index for index, term_id in enumerate(term_ids)}
    if not term_ids:
        return SparseTfidf(document_ids=[], term_ids=[], matrix=csr_matrix((0, 0)))

    rows = (
        await session.execute(
            select(Posting.document_id, Posting.term_id, Posting.weight_norm)
            .where(Posting.term_id.in_(term_ids))
            .order_by(Posting.document_id, Posting.term_id)
        )
    ).all()

    document_ids = sorted({int(document_id) for document_id, _, _ in rows})
    row_of = {document_id: index for index, document_id in enumerate(document_ids)}

    data = np.fromiter((float(w) for _, _, w in rows), dtype=np.float64, count=len(rows))
    row_index = np.fromiter((row_of[int(d)] for d, _, _ in rows), dtype=np.int64, count=len(rows))
    col_index = np.fromiter((column[int(t)] for _, t, _ in rows), dtype=np.int64, count=len(rows))

    matrix = csr_matrix(
        (data, (row_index, col_index)), shape=(len(document_ids), len(term_ids)), dtype=np.float64
    )
    return SparseTfidf(document_ids=document_ids, term_ids=term_ids, matrix=matrix)


@dataclass(slots=True)
class LsaDecomposition:
    components: int
    singular_values: list[float]
    basis: Array  # (components, terms) — the rows of Vᵀ, unit-norm, sign-normalised
    coordinates: Array  # (documents, components) — U·Σ, i.e. each document's projection
    explained_variance_ratio: float


def decompose(matrix: Any, components: int, seed: int | None = None) -> LsaDecomposition:
    """Truncated SVD of the term–document matrix."""
    n_documents, n_terms = matrix.shape
    if components < 1 or components >= min(n_documents, n_terms):
        raise ValueError(
            f"cannot keep {components} components of a {n_documents}×{n_terms} matrix: "
            "need 1 ≤ k < min(N, D)"
        )

    rng = np.random.default_rng(settings.evaluation.random_seed if seed is None else seed)
    u_raw, s_raw, vt_raw = svds(matrix.asfptype(), k=components, random_state=rng)
    u = np.asarray(u_raw, dtype=np.float64)
    s = np.asarray(s_raw, dtype=np.float64)
    vt = np.asarray(vt_raw, dtype=np.float64)

    # ARPACK returns ascending singular values; report them descending, as everyone does.
    order = np.argsort(s)[::-1]
    u, s, vt = u[:, order], s[order], vt[order, :]

    # Sign convention: the largest-magnitude coordinate of each basis row is positive.
    for row in range(vt.shape[0]):
        pivot = int(np.argmax(np.abs(vt[row])))
        if vt[row, pivot] < 0:
            vt[row] *= -1.0
            u[:, row] *= -1.0

    frobenius_sq = float(matrix.multiply(matrix).sum())
    explained = float(np.sum(s * s) / frobenius_sq) if frobenius_sq > 0 else 0.0

    return LsaDecomposition(
        components=components,
        singular_values=[float(value) for value in s],
        basis=vt,
        coordinates=u * s,
        explained_variance_ratio=min(explained, 1.0),
    )


def project(
    basis: Array, column_of_term: Mapping[int, int], vector: Mapping[int, float]
) -> list[float]:
    """Project a sparse term vector into the latent space: `Σ_t w_t · V[t]`.

    Terms outside the reduced vocabulary span no latent direction and are ignored.
    """
    point = np.zeros(basis.shape[0], dtype=np.float64)
    for term_id, weight in vector.items():
        col = column_of_term.get(term_id)
        if col is not None:
            point += weight * basis[:, col]
    return [float(value) for value in point]


@dataclass(slots=True)
class LsaBuildStats:
    index_version: int
    documents: int
    terms: int
    components: int
    singular_values: list[float]
    explained_variance_ratio: float
    duration_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "index_version": self.index_version,
            "documents": self.documents,
            "terms": self.terms,
            "components": self.components,
            "singular_values": [round(v, 4) for v in self.singular_values],
            "explained_variance_ratio": round(self.explained_variance_ratio, 4),
            "duration_ms": round(self.duration_ms, 1),
        }


async def build_lsa(session: AsyncSession, components: int | None = None) -> LsaBuildStats:
    """Decompose the current index and persist the model and the projections."""
    components = settings.index.lsa_components if components is None else components
    watch = Stopwatch()
    stat = await get_collection_stat(session)

    tfidf = await load_matrix(session)
    if not tfidf.document_ids:
        raise ValueError("the index is empty — nothing to decompose")
    decomposition = decompose(tfidf.matrix, components)

    await session.execute(
        delete(LsaProjection).where(LsaProjection.index_version == stat.index_version)
    )
    await session.execute(delete(LsaModel).where(LsaModel.index_version == stat.index_version))

    session.add(
        LsaModel(
            index_version=stat.index_version,
            components=components,
            term_ids=list(tfidf.term_ids),
            basis=[float(value) for value in decomposition.basis.reshape(-1)],
            singular_values=decomposition.singular_values,
            explained_variance_ratio=decomposition.explained_variance_ratio,
            built_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    session.add_all(
        [
            LsaProjection(
                document_id=document_id,
                index_version=stat.index_version,
                x=float(coords[0]),
                y=float(coords[1]) if components > 1 else 0.0,
                z=float(coords[2]) if components > 2 else 0.0,
            )
            for document_id, coords in zip(
                tfidf.document_ids, decomposition.coordinates, strict=True
            )
        ]
    )
    await session.flush()

    stats = LsaBuildStats(
        index_version=stat.index_version,
        documents=len(tfidf.document_ids),
        terms=len(tfidf.term_ids),
        components=components,
        singular_values=decomposition.singular_values,
        explained_variance_ratio=decomposition.explained_variance_ratio,
        duration_ms=watch.total_ms,
    )
    log.info("lsa_built", **stats.as_dict())
    return stats


async def load_model(session: AsyncSession, index_version: int) -> LsaModel | None:
    return await session.get(LsaModel, index_version)


def model_basis(model: LsaModel) -> tuple[Array, dict[int, int]]:
    """Reshape a stored model back into ``(basis, column_of_term)``."""
    basis = np.asarray(model.basis, dtype=np.float64).reshape(model.components, len(model.term_ids))
    return basis, {int(term_id): column for column, term_id in enumerate(model.term_ids)}
