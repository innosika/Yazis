"""Request and response models of the translation API."""

from pydantic import BaseModel, Field

from app.config import settings


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=settings.max_input_chars)
    domain: str = "general"
    mode: str = Field(default="transfer", pattern="^(transfer|direct)$")
    include_direct: bool = True
    """Also run the word-for-word architecture, for the side-by-side comparison."""
    use_memory: bool = True
    save: bool = True
    title: str = ""


class TagInfoOut(BaseModel):
    code: str
    name: str
    description: str
    examples: str = ""


class SignalOut(BaseModel):
    name: str
    value: float
    weight: float
    contribution: float
    detail: str


class CandidateOut(BaseModel):
    sense_id: int
    translation_id: int | None
    entry_pos: str | None
    sense_index: int
    gloss: str
    labels: list[str]
    translation: str
    translation_accented: str
    alternatives: list[str]
    score: float
    signals: list[SignalOut]
    selected: bool
    locked: bool


class AmbiguityOut(BaseModel):
    sentence: int
    token: int
    text: str
    lemma: str
    upos: str
    pos_name: str
    context: str
    margin: float
    candidates: list[CandidateOut]


class PieceOut(BaseModel):
    surface: str
    kind: str
    source_indices: list[int]
    source_text: str
    lemma: str = ""
    tag: str = ""
    decoded: list[str] = []
    case: str | None = None
    note: str = ""


class MemoryMatchOut(BaseModel):
    id: int
    similarity: float
    source_text: str
    target_text: str
    domain_code: str
    origin: str
    exact: bool


class SentenceOut(BaseModel):
    index: int
    source: str
    target: str
    pieces: list[PieceOut]
    stages: dict[str, str]
    memory: MemoryMatchOut | None = None
    direct: str = ""


class WordRowOut(BaseModel):
    lemma: str
    upos: str
    tag: str
    count: int
    forms: list[str]
    translation: str
    translation_accented: str
    gloss: str
    sense_index: int
    sense_count: int
    translated: bool
    pos_name: str
    pos_description: str
    tag_name: str
    tag_description: str
    features: list[str]
    ambiguous: bool
    from_user: bool
    dropped_by_rule: bool
    note: str


class TokenOut(BaseModel):
    sentence: int
    index: int
    text: str
    lemma: str
    upos: str
    tag: str
    morph: str
    dep: str
    head: int
    translation: str
    translation_accented: str
    gloss: str
    sense_count: int
    ambiguous: bool
    translated: bool
    dropped_by_rule: bool
    target_tag: str
    target_decoded: list[str]
    note: str
    features: list[str]
    pos_name: str
    tag_name: str


class TreeNodeOut(BaseModel):
    id: int
    text: str
    lemma: str
    upos: str
    pos_name: str
    tag: str
    tag_name: str
    tag_description: str
    dep: str
    dep_description: str
    features: list[str]
    translation: str
    target_decoded: list[str]
    depth: int
    width: int
    children: list["TreeNodeOut"] = []


class TreeOut(BaseModel):
    sentence: int
    text: str
    root: TreeNodeOut | None


class OovOut(BaseModel):
    lemma: str
    upos: str
    occurrences: int
    context: str


class StatsOut(BaseModel):
    characters: int
    sentences: int
    words: int
    content_words: int
    translated_words: int
    untranslated_words: int
    unique_lemmas: int
    coverage: float
    ambiguous_words: int
    dropped_tokens: int
    inserted_tokens: int
    pos_distribution: dict[str, int]


class TranslateResponse(BaseModel):
    document_id: int | None
    domain: str
    mode: str
    source: str
    target: str
    direct_target: str
    duration_ms: float
    stats: StatsOut
    sentences: list[SentenceOut]
    words: list[WordRowOut]
    tokens: list[TokenOut]
    trees: list[TreeOut]
    ambiguities: list[AmbiguityOut]
    oov: list[OovOut]
    memory_hits: int


class SampleOut(BaseModel):
    name: str
    title: str
    domain: str
    characters: int
    text: str
