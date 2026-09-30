"""Aggregates every versioned API route under a single router."""

from __future__ import annotations

from fastapi import APIRouter

from irs.api.routes import corpus, crawl, evaluation, health, lab, search, stream

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(search.router)
api_router.include_router(corpus.router)
api_router.include_router(crawl.router)
api_router.include_router(stream.router)
api_router.include_router(evaluation.router)
api_router.include_router(lab.router)
