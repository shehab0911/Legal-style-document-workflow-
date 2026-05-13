from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class DocumentRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: str = Field(index=True, unique=True)
    filename: str
    page_count: int = 0
    char_count: int = 0
    structured_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DraftRunRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_public_id: str = Field(index=True)
    task: str
    draft_markdown: str
    evidence_json: str
    citations_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OperatorEditRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_public_id: str = Field(index=True)
    task: str
    system_draft: str
    operator_final: str
    diff_summary_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChunkRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_public_id: str = Field(index=True)
    chunk_id: str = Field(index=True)
    page_index: Optional[int] = None
    text: str
    source: str = "native_text"


class LearnedSnippetRecord(SQLModel, table=True):
    """Reusable operator preference snippets (text pairs) for retrieval-time injection."""

    id: Optional[int] = Field(default=None, primary_key=True)
    document_public_id: str = Field(index=True)
    context_before: str
    original_fragment: str
    revised_fragment: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
