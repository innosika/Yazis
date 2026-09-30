"""Request and response models of the dictionary utility."""

from pydantic import BaseModel, Field


class TranslationOut(BaseModel):
    id: int
    idx: int
    form_accented: str
    form_plain: str
    is_user: bool


class SenseOut(BaseModel):
    id: int
    idx: int
    gloss: str
    labels: list[str]
    domain_scores: dict[str, float]
    translations: list[TranslationOut]


class EntryOut(BaseModel):
    id: int
    headword: str
    headword_norm: str
    pos: str | None
    ipa: str | None
    word_count: int
    source: str
    is_user: bool
    senses: list[SenseOut]


class EntryPage(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[EntryOut]


class TranslationIn(BaseModel):
    form: str = Field(min_length=1, max_length=200)


class SenseIn(BaseModel):
    gloss: str = ""
    labels: list[str] = []
    translations: list[str] = Field(min_length=1)


class EntryIn(BaseModel):
    headword: str = Field(min_length=1, max_length=200)
    pos: str | None = Field(default="n", max_length=32)
    ipa: str | None = None
    senses: list[SenseIn] = Field(min_length=1)


class EntryPatch(BaseModel):
    headword: str | None = None
    pos: str | None = None
    ipa: str | None = None


class SensePatch(BaseModel):
    gloss: str | None = None
    labels: list[str] | None = None


class TranslationsPatch(BaseModel):
    forms: list[str] = Field(min_length=1)
    """Replaces the sense's translation list, in the given order."""


class SuggestionOut(BaseModel):
    lemma: str
    pos: str
    source: str
    confidence: float
    forms: list[str]
    explanation: str


class OovOut(BaseModel):
    id: int
    lemma: str
    pos: str
    occurrences: int
    status: str
    suggestion: SuggestionOut | None
    context: str | None
    first_seen: str
    last_seen: str


class OovPage(BaseModel):
    total: int
    pending: int
    items: list[OovOut]


class OovAccept(BaseModel):
    forms: list[str] = Field(min_length=1)
    gloss: str = ""
    pos: str | None = None


class ScanRequest(BaseModel):
    text: str = Field(min_length=1)
    domain: str = "general"
    limit: int = Field(default=40, ge=1, le=200)


class ScanResult(BaseModel):
    scanned_words: int
    found: int
    suggestions: list[SuggestionOut]


class OverrideIn(BaseModel):
    headword: str
    pos: str
    domain_code: str
    sense_id: int
    translation_id: int | None = None
    note: str | None = None


class OverrideOut(BaseModel):
    id: int
    headword_norm: str
    pos: str
    domain_code: str
    sense_id: int
    translation_id: int | None
    translation: str
    gloss: str
    note: str | None
    created_at: str
