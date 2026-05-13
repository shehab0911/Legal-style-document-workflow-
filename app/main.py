from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.db.models import ChunkRecord, DocumentRecord, DraftRunRecord
from app.db.session import get_session, init_db
from app.models.schemas import (
    DocumentIngestResponse,
    DraftRequest,
    DraftResponse,
    EditFeedbackRequest,
)
from app.services.chunking import chunk_pages
from app.services.edit_learning import list_recent_edits, record_operator_edit
from app.services.generation import _task_query, draft_with_optional_openai, load_preference_hints
from app.services.ingestion import extract_structured_fields, ingest_pdf_bytes
from app.services.retrieval import hybrid_retrieve, index_chunks

app = FastAPI(title="Legal Workflow — Ingest, Ground, Draft, Learn", version="1.0.0")


@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/documents/upload", response_model=DocumentIngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentIngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF uploads are supported in this reference implementation.")
    data = await file.read()
    if len(data) > 40 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 40MB).")

    ing = ingest_pdf_bytes(data, filename=file.filename)
    full_text = "\n\n".join(p.text for p in ing.pages)
    structured = extract_structured_fields(full_text)

    session.add(
        DocumentRecord(
            public_id=ing.document_id,
            filename=file.filename,
            page_count=len(ing.pages),
            char_count=len(full_text),
            structured_json=structured.model_dump_json(),
        )
    )

    chunks = chunk_pages(ing.pages)
    for ch in chunks:
        session.add(
            ChunkRecord(
                document_public_id=ing.document_id,
                chunk_id=ch.chunk_id,
                page_index=ch.page_index,
                text=ch.text,
                source=ch.source,
            )
        )
    await session.commit()

    index_chunks(
        ing.document_id,
        [(c.chunk_id, c.text, c.page_index, c.source) for c in chunks],
    )

    return DocumentIngestResponse(
        document_id=ing.document_id,
        page_count=len(ing.pages),
        char_count=len(full_text),
        structured=structured,
        warnings=ing.warnings,
    )


@app.post("/drafts/generate", response_model=DraftResponse)
async def generate_draft(
    body: DraftRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftResponse:
    r = await session.exec(select(DocumentRecord).where(DocumentRecord.public_id == body.document_id))
    doc = r.first()
    if not doc:
        raise HTTPException(404, "document_id not found")

    r2 = await session.exec(select(ChunkRecord).where(ChunkRecord.document_public_id == body.document_id))
    rows = r2.all()
    if not rows:
        raise HTTPException(400, "No chunks for document; re-upload may be required.")

    chunk_tuples = [(c.chunk_id, c.text, c.page_index) for c in rows]
    q = _task_query(body.task, body.query)
    ranked, dbg = hybrid_retrieve(body.document_id, q, chunk_tuples)
    if not ranked:
        dbg["fallback"] = "No fusion hits; using first chunks from document."
        ranked = [
            (c.chunk_id, c.text, c.page_index, 1.0)
            for c in sorted(rows, key=lambda x: (x.page_index or 0, x.chunk_id))[: settings.retrieval_fusion_top_n]
        ]

    prefs = load_preference_hints(body.document_id, body.task, body.query)

    md, cites, evidence, used_llm = await draft_with_optional_openai(ranked, body.task, prefs)
    dbg["used_openai"] = used_llm

    resp = DraftResponse(
        document_id=body.document_id,
        task=body.task,
        draft_markdown=md,
        evidence=evidence,
        citations=cites,
        retrieval_debug=dbg,
    )

    session.add(
        DraftRunRecord(
            document_public_id=body.document_id,
            task=body.task.value,
            draft_markdown=md,
            evidence_json=json.dumps([e.model_dump() for e in evidence]),
            citations_json=json.dumps([c.model_dump() for c in cites]),
        )
    )
    await session.commit()
    return resp


@app.post("/edits/feedback")
async def edits_feedback(
    body: EditFeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    r = await session.exec(select(DocumentRecord).where(DocumentRecord.public_id == body.document_id))
    if not r.first():
        raise HTTPException(404, "document_id not found")
    summary = await record_operator_edit(
        session,
        document_public_id=body.document_id,
        task=body.task.value,
        system_draft=body.system_draft_markdown,
        operator_final=body.operator_final_markdown,
    )
    return {"status": "stored", **summary, "notes": body.notes}


@app.get("/documents/{document_id}/edits")
async def get_edits(document_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    rows = await list_recent_edits(session, document_id, limit=20)
    return {
        "document_id": document_id,
        "edits": [
            {
                "created_at": e.created_at.isoformat(),
                "task": e.task,
                "diff_summary": json.loads(e.diff_summary_json),
            }
            for e in rows
        ],
    }


static_dir = Path(__file__).resolve().parent / "static"


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    index = static_dir / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return "<p>API running. Open <code>/docs</code> for OpenAPI.</p>"
