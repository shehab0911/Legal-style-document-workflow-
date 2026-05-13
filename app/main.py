from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.db.models import ChunkRecord, DocumentRecord, DraftRunRecord
from app.db.session import get_session, init_db
from app.deps import require_api_key
from app.middleware.production import RateLimitMiddleware, RequestContextMiddleware
from app.models.schemas import (
    DocumentIngestResponse,
    DraftRequest,
    DraftResponse,
    EditFeedbackRequest,
)
from app.services.chunking import chunk_pages
from app.services.edit_learning import list_recent_edits, record_operator_edit
from app.services.generation import _task_query, draft_with_optional_gemini, load_preference_hints
from app.services.ingestion import extract_structured_fields, ingest_pdf_bytes
from app.services.pdf_validate import is_pdf_magic
from app.services.retrieval import hybrid_retrieve, index_chunks

log = logging.getLogger("legal_workflow")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(
    title="Legal Workflow — Ingest, Ground, Draft, Learn",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error")
    if settings.is_production:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Dependency checks for orchestrators (DB readable, data dir writable)."""
    issues: list[str] = []
    try:
        await session.exec(select(DocumentRecord).limit(1))
    except Exception as e:  # noqa: BLE001
        issues.append(f"database:{type(e).__name__}")
    if not os.access(settings.data_dir, os.W_OK):
        issues.append("data_dir_not_writable")
    if issues:
        return JSONResponse(
            status_code=503,
            content={"ready": False, "issues": issues},
        )
    return {"ready": True, "database": "ok", "storage": "writable"}


@app.post("/documents/upload", response_model=DocumentIngestResponse, dependencies=[Depends(require_api_key)])
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentIngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF uploads are supported in this reference implementation.")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(400, f"File too large (max {settings.max_upload_bytes // (1024 * 1024)}MB).")
    if not is_pdf_magic(data):
        raise HTTPException(400, "File does not appear to be a valid PDF (missing %PDF header).")

    try:
        ing = ingest_pdf_bytes(data, filename=file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

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
    try:
        index_chunks(
            ing.document_id,
            [(c.chunk_id, c.text, c.page_index, c.source) for c in chunks],
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return DocumentIngestResponse(
        document_id=ing.document_id,
        page_count=len(ing.pages),
        char_count=len(full_text),
        structured=structured,
        warnings=ing.warnings,
    )


@app.post("/drafts/generate", response_model=DraftResponse, dependencies=[Depends(require_api_key)])
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

    md, cites, evidence, used_llm = await draft_with_optional_gemini(ranked, body.task, prefs)
    dbg["used_llm"] = used_llm

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


@app.post("/edits/feedback", dependencies=[Depends(require_api_key)])
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


@app.get("/documents/{document_id}/edits", dependencies=[Depends(require_api_key)])
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
    return "<p>API running. See <a href=\"/docs\">DOCS</a>.</p>"
