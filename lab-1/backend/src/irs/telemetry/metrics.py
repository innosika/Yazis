"""Prometheus instrumentation.

Exposed at ``/metrics``. Kept deliberately small: the counters that matter for the
report's performance section are search latency by ranker, crawl outcomes by reason,
and indexing throughput.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

SEARCH_LATENCY = Histogram(
    "irs_search_duration_seconds",
    "End-to-end search latency.",
    labelnames=("ranker",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

SEARCH_REQUESTS = Counter(
    "irs_search_requests_total",
    "Searches served.",
    labelnames=("ranker", "outcome"),
)

CRAWL_PAGES = Counter(
    "irs_crawl_pages_total",
    "Pages processed by the crawler, by outcome.",
    labelnames=("outcome",),
)

CRAWL_FETCH_LATENCY = Histogram(
    "irs_crawl_fetch_duration_seconds",
    "Time to fetch one URL.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

INDEX_DOCUMENTS = Gauge("irs_index_documents", "Documents currently indexed (N).")
INDEX_TERMS = Gauge("irs_index_terms", "Distinct terms in the dictionary (D).")

INDEX_BUILD_LATENCY = Histogram(
    "irs_index_build_duration_seconds",
    "Full index rebuild duration.",
    buckets=(0.5, 1.0, 5.0, 15.0, 60.0, 300.0),
)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
