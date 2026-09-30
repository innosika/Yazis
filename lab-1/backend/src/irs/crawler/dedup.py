"""Duplicate and near-duplicate detection.

A web crawl produces the same content under different URLs constantly — print views,
tracking parameters, session ids, mirrors, and pagination that repeats a summary. Left
unfiltered these inflate `N`, which deflates every inverse frequency in the collection
and makes the whole index subtly wrong. Two mechanisms are used:

* **Exact duplicates** — SHA-256 of the normalised text. Cheap and certain.
* **Near duplicates** — a 64-bit SimHash compared by Hamming distance. SimHash is a
  locality-sensitive hash: unlike a cryptographic digest, similar inputs produce similar
  outputs, so documents differing only in a byline or a navigation fragment land within
  a few bits of each other.
"""

from __future__ import annotations

import hashlib
import re

#: Words are the SimHash features. Character shingles would be more robust to word
#: reordering, but words are what the index itself is built from, so a near-duplicate by
#: this measure is also a near-duplicate as far as retrieval is concerned.
_TOKEN = re.compile(r"[a-z0-9]+")

_HASH_BITS = 64
_MASK = (1 << _HASH_BITS) - 1


def normalize_for_hashing(text: str) -> str:
    """Collapse whitespace and case so that cosmetic differences do not defeat hashing."""
    return " ".join((text or "").lower().split())


def content_hash(text: str) -> str:
    """SHA-256 of the normalised text — the exact-duplicate key."""
    return hashlib.sha256(normalize_for_hashing(text).encode("utf-8")).hexdigest()


def simhash(text: str, bits: int = _HASH_BITS) -> int:
    """Compute Charikar's SimHash of ``text``.

    Each distinct token votes on every bit position, weighted by how often the token
    occurs; a bit ends up 1 when the weighted vote for it is positive. Two documents
    sharing most of their weighted vocabulary therefore agree on most bits.

    Returns 0 for text with no tokens, which callers treat as "no fingerprint" rather
    than as a fingerprint that happens to be zero.
    """
    tokens = _TOKEN.findall(normalize_for_hashing(text))
    if not tokens:
        return 0

    frequencies: dict[str, int] = {}
    for token in tokens:
        frequencies[token] = frequencies.get(token, 0) + 1

    vector = [0] * bits
    for token, weight in frequencies.items():
        digest = int.from_bytes(
            hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
        )
        for position in range(bits):
            if digest >> position & 1:
                vector[position] += weight
            else:
                vector[position] -= weight

    fingerprint = 0
    for position in range(bits):
        if vector[position] > 0:
            fingerprint |= 1 << position
    return fingerprint


def hamming_distance(left: int, right: int) -> int:
    """Number of differing bits — the near-duplicate distance."""
    return ((left ^ right) & _MASK).bit_count()


def to_signed_64(value: int) -> int:
    """Map an unsigned 64-bit fingerprint into PostgreSQL's signed ``bigint`` range.

    Postgres has no unsigned integer type, so a fingerprint with the top bit set would
    overflow ``bigint``. Reinterpreting the same bits as two's-complement preserves the
    Hamming distance exactly, which is all the comparison depends on.
    """
    value &= _MASK
    return value - (1 << _HASH_BITS) if value >= 1 << (_HASH_BITS - 1) else value


def from_signed_64(value: int) -> int:
    """Inverse of :func:`to_signed_64`."""
    return value + (1 << _HASH_BITS) if value < 0 else value
