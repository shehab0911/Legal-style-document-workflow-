from __future__ import annotations

import difflib
import re
import uuid
from typing import Any

from app.config import settings
from app.models.schemas import (
    CitationRecord,
    DraftTaskType,
    EvidenceSpan,
)
from app.services.retrieval import index_preference_snippet, retrieve_preferences


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _compress_quote(s: str, max_len: int = 320) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _build_evidence_ids(chunks: list[tuple[str, str, int | None, float]]) -> tuple[list[EvidenceSpan], dict[str, str]]:
    """Assign E1, E2, ... to chunks."""
    spans: list[EvidenceSpan] = []
    id_map: dict[str, str] = {}
    for i, (cid, text, page, _) in enumerate(chunks, start=1):
        eid = f"E{i}"
        id_map[cid] = eid
        spans.append(
            EvidenceSpan(
                evidence_id=eid,
                chunk_id=cid,
                page_index=page,
                excerpt=_compress_quote(text),
                full_chunk_text=text,
            )
        )
    return spans, id_map


def _task_query(task: DraftTaskType, user_query: str | None) -> str:
    base = {
        DraftTaskType.CASE_FACT_SUMMARY: "Key parties obligations timeline amounts events risks stated in the document",
        DraftTaskType.DOCUMENT_CHECKLIST: "Required exhibits signatures deadlines filings mentioned in the document",
        DraftTaskType.INTERNAL_MEMO: "Internal summary issues open questions next steps based on the document",
    }[task]
    if user_query:
        return f"{base}. Focus: {user_query}"
    return base


def draft_extractive_case_summary(
    chunks: list[tuple[str, str, int | None, float]],
    task: DraftTaskType,
    preference_hints: list[str],
) -> tuple[str, list[CitationRecord]]:
    """
    Build a grounded first-pass draft using extractive sentences from evidence only.
    Each bullet cites one or more evidence ids.
    """
    evidence_spans, id_map = _build_evidence_ids(chunks)
    eid_by_cid = id_map

    pref_block = ""
    if preference_hints:
        pref_block = "\n## Operator preferences (style / terminology learned from past edits)\n" + "\n".join(
            f"- {h}" for h in preference_hints
        )

    lines: list[str] = ["# Draft (first pass)", ""]
    if pref_block:
        lines.append(pref_block)
        lines.append("")

    if task == DraftTaskType.DOCUMENT_CHECKLIST:
        lines.append("## Checklist items (each item must appear in cited evidence)")
        lines.append("")
        citations: list[CitationRecord] = []
        for ev in evidence_spans:
            # One checklist row per evidence chunk (conservative grounding)
            bullet = f"- [ ] Review: {_compress_quote(ev.excerpt, 200)} [{ev.evidence_id}]"
            lines.append(bullet)
            citations.append(CitationRecord(draft_span=bullet, evidence_ids=[ev.evidence_id]))
        return "\n".join(lines), citations

    if task == DraftTaskType.INTERNAL_MEMO:
        lines.append("## Internal memo")
        lines.append("")
        lines.append("### Facts anchored to source")
        citations = []
        for ev in evidence_spans[:8]:
            sent = _split_sentences(ev.full_chunk_text)
            pick = sent[0] if sent else _compress_quote(ev.full_chunk_text, 240)
            row = f"- {pick} [{ev.evidence_id}]"
            lines.append(row)
            citations.append(CitationRecord(draft_span=row, evidence_ids=[ev.evidence_id]))
        lines.append("")
        lines.append("### Notes")
        lines.append(
            "- This memo is intentionally extractive; verify against full file before external use."
        )
        return "\n".join(lines), citations

    # CASE_FACT_SUMMARY (default)
    lines.append("## Case / matter fact summary")
    lines.append("")
    lines.append("Each bullet is copied or lightly trimmed from a single evidence span.")
    lines.append("")
    citations = []
    for ev in evidence_spans[:10]:
        sents = _split_sentences(ev.full_chunk_text)
        if not sents:
            continue
        longest = max(sents, key=len)
        if len(longest) < 20:
            longest = _compress_quote(ev.full_chunk_text, 280)
        bullet = f"- {_compress_quote(longest, 400)} [{ev.evidence_id}]"
        lines.append(bullet)
        citations.append(CitationRecord(draft_span=bullet, evidence_ids=[ev.evidence_id]))
    return "\n".join(lines), citations


async def draft_with_optional_openai(
    chunks: list[tuple[str, str, int | None, float]],
    task: DraftTaskType,
    preference_hints: list[str],
) -> tuple[str, list[CitationRecord], list[EvidenceSpan], bool]:
    evidence_spans, _ = _build_evidence_ids(chunks)
    used_llm = False

    if not settings.openai_api_key:
        md, cites = draft_extractive_case_summary(chunks, task, preference_hints)
        return md, cites, evidence_spans, used_llm

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        evidence_block = "\n\n".join(
            f"[{e.evidence_id}] (page {e.page_index + 1 if e.page_index is not None else '?'}): {e.full_chunk_text}"
            for e in evidence_spans
        )
        pref = "\n".join(preference_hints) if preference_hints else "(none)"

        task_instr = {
            DraftTaskType.CASE_FACT_SUMMARY: "Produce a case fact summary as bullet points.",
            DraftTaskType.DOCUMENT_CHECKLIST: "Produce a checklist of concrete action items implied by the document.",
            DraftTaskType.INTERNAL_MEMO: "Produce a short internal memo with Facts / Issues / Next steps.",
        }[task]

        prompt = f"""You are drafting inside a law firm workflow. Use ONLY the evidence blocks below.
Rules:
- Every factual sentence MUST end with one or more bracketed citations like [E1] or [E1][E2].
- Do not invent parties, dates, amounts, or obligations not clearly supported.
- If evidence conflicts, say so explicitly and cite both.
- Apply OPERATOR_PREFERENCES only for wording/style where still faithful to evidence.

OPERATOR_PREFERENCES:
{pref}

EVIDENCE:
{evidence_block}

{task_instr}
Return markdown."""

        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
        used_llm = True

        cites: list[CitationRecord] = []
        for line in content.splitlines():
            found = re.findall(r"\[E\d+\]", line)
            if not found:
                continue
            eids = [x.strip("[]") for x in found]
            cites.append(CitationRecord(draft_span=line.strip(), evidence_ids=eids))

        return content, cites, evidence_spans, used_llm
    except Exception:
        md, cites = draft_extractive_case_summary(chunks, task, preference_hints)
        return md, cites, evidence_spans, used_llm


def summarize_diff(system_draft: str, operator_final: str) -> dict[str, Any]:
    sm = difflib.SequenceMatcher(a=system_draft, b=operator_final)
    ops = sm.get_opcodes()
    replacements: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "replace":
            replacements.append(
                {
                    "before": system_draft[i1:i2].strip(),
                    "after": operator_final[j1:j2].strip(),
                }
            )
        elif tag == "delete":
            replacements.append({"before": system_draft[i1:i2].strip(), "after": ""})
        elif tag == "insert":
            replacements.append({"before": "", "after": operator_final[j1:j2].strip()})
    return {"replacement_count": len(replacements), "samples": replacements[:25]}


def extract_learned_snippets(
    system_draft: str,
    operator_final: str,
    context_chars: int = 80,
) -> list[tuple[str, str, str]]:
    """
    Returns list of (context_before, original_fragment, revised_fragment) for meaningful changes.
    """
    sm = difflib.SequenceMatcher(a=system_draft, b=operator_final)
    out: list[tuple[str, str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag not in {"replace", "insert", "delete"}:
            continue
        before_frag = system_draft[i1:i2]
        after_frag = operator_final[j1:j2]
        if tag == "insert" and len(after_frag.strip()) < 8:
            continue
        if tag == "delete" and len(before_frag.strip()) < 8:
            continue
        if tag == "replace" and len(before_frag.strip()) < 6 and len(after_frag.strip()) < 6:
            continue
        ctx_start = max(0, i1 - context_chars)
        ctx = system_draft[ctx_start:i1]
        out.append((ctx[-context_chars:], before_frag, after_frag))
    return out[:40]


def persist_learned_snippets(document_id: str, snippets: list[tuple[str, str, str]]) -> int:
    n = 0
    for ctx, orig, rev in snippets:
        sid = str(uuid.uuid4())
        text = (
            "When drafting similar content, prefer replacing:\n"
            f"FROM: {orig.strip()[:500]}\n"
            f"TO: {rev.strip()[:500]}\n"
            f"(Nearby context: ...{ctx.strip()[-200:]})"
        )
        index_preference_snippet(document_id, sid, text)
        n += 1
    return n


def load_preference_hints(document_id: str, task: DraftTaskType, extra_query: str | None) -> list[str]:
    q = _task_query(task, extra_query)
    return retrieve_preferences(q, document_id=document_id, top_k=6)
