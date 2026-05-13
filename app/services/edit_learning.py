from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import LearnedSnippetRecord, OperatorEditRecord
from app.services.generation import (
    extract_learned_snippets,
    persist_learned_snippets,
    summarize_diff,
)


async def record_operator_edit(
    session: AsyncSession,
    *,
    document_public_id: str,
    task: str,
    system_draft: str,
    operator_final: str,
) -> dict[str, Any]:
    diff = summarize_diff(system_draft, operator_final)
    snippets = extract_learned_snippets(system_draft, operator_final)
    n_vec = persist_learned_snippets(document_public_id, snippets)

    for ctx, orig, rev in snippets:
        session.add(
            LearnedSnippetRecord(
                document_public_id=document_public_id,
                context_before=ctx[-500:],
                original_fragment=orig[:2000],
                revised_fragment=rev[:2000],
            )
        )

    session.add(
        OperatorEditRecord(
            document_public_id=document_public_id,
            task=task,
            system_draft=system_draft,
            operator_final=operator_final,
            diff_summary_json=json.dumps(diff),
        )
    )
    await session.commit()

    return {
        "diff_summary": diff,
        "learned_snippet_rows": len(snippets),
        "vector_preferences_written": n_vec,
    }


async def list_recent_edits(session: AsyncSession, document_public_id: str, limit: int = 10) -> list[OperatorEditRecord]:
    q = await session.exec(
        select(OperatorEditRecord)
        .where(OperatorEditRecord.document_public_id == document_public_id)
        .order_by(desc(OperatorEditRecord.created_at))
    )
    rows = q.all()
    return list(rows[:limit])
