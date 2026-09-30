from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.llm import assist
from app.llm.client import GroqLLM, LLMError
from app.state import state

router = APIRouter(prefix="/assist", tags=["assistant"])


class ExplainIn(BaseModel):
    term: str = Field(..., min_length=1, max_length=200)
    context: str = Field("", max_length=20_000)
    title: str = Field("", max_length=500)


class SummarizeIn(BaseModel):
    text: str = Field(..., min_length=20, max_length=200_000)
    title: str = Field("", max_length=500)
    section: str = Field("", max_length=300)


class Answer(BaseModel):
    text: str


def _llm() -> GroqLLM:
    if state.llm is None:
        raise HTTPException(503, "The assistant needs a GROQ_API_KEY in .env")
    llm: GroqLLM = state.llm
    return llm


@router.post("/explain", response_model=Answer)
async def explain(body: ExplainIn) -> Answer:
    try:
        return Answer(text=await assist.explain(_llm(), body.term, body.context, body.title))
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/summarize", response_model=Answer)
async def summarize(body: SummarizeIn) -> Answer:
    try:
        return Answer(text=await assist.summarize(_llm(), body.text, body.title, body.section))
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc
