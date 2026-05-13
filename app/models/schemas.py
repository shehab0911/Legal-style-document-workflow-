from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DraftTaskType(str, Enum):
    CASE_FACT_SUMMARY = "case_fact_summary"
    DOCUMENT_CHECKLIST = "document_checklist"
    INTERNAL_MEMO = "internal_memo"


class PageBlock(BaseModel):
    page_index: int
    text: str
    source: str = Field(description="native_text | ocr")
    bbox: tuple[float, float, float, float] | None = None


class StructuredCaseFields(BaseModel):
    """Lightweight structured fields extracted heuristically for downstream use."""

    inferred_doc_types: list[str] = Field(default_factory=list)
    dates_mentioned: list[str] = Field(default_factory=list)
    party_hints: list[str] = Field(default_factory=list)
    money_amounts: list[str] = Field(default_factory=list)
    section_headings: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)


class DocumentIngestResponse(BaseModel):
    document_id: str
    page_count: int
    char_count: int
    structured: StructuredCaseFields
    warnings: list[str] = Field(default_factory=list)


class EvidenceSpan(BaseModel):
    evidence_id: str
    chunk_id: str
    page_index: int | None
    excerpt: str
    full_chunk_text: str


class DraftRequest(BaseModel):
    document_id: str
    task: DraftTaskType = DraftTaskType.CASE_FACT_SUMMARY
    query: str | None = Field(
        default=None,
        description="Optional focus for retrieval (e.g. 'timeline of payments').",
    )


class CitationRecord(BaseModel):
    """Maps a span of the draft to supporting evidence."""

    draft_span: str
    evidence_ids: list[str]


class DraftResponse(BaseModel):
    document_id: str
    task: DraftTaskType
    draft_markdown: str
    evidence: list[EvidenceSpan]
    citations: list[CitationRecord]
    retrieval_debug: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EditFeedbackRequest(BaseModel):
    document_id: str
    system_draft_markdown: str
    operator_final_markdown: str
    task: DraftTaskType = DraftTaskType.CASE_FACT_SUMMARY
    notes: str | None = None
