# Evaluation approach and results

## Rubric mapping (Pearson-style brief)

| Brief requirement | Implementation | How we verify |
|-------------------|----------------|---------------|
| Messy PDFs: text + OCR | PyMuPDF native text; Tesseract when below char threshold; PIL contrast/sharpen before OCR | Upload native + low-text PDFs; check `warnings` and `PageBlock.source` |
| Structured downstream fields | Heuristic `StructuredCaseFields` + title/notice lists | Upload response JSON |
| Grounded retrieval | Hybrid Chroma + BM25 + RRF; fusion top-N | `retrieval_debug` in draft response |
| Inspectable evidence | `evidence[]`, `citations[]`, `[E#]` in extractive / prompted LLM drafts | Manual / JSON diff |
| Draft types | Case fact, **title review**, **notice-related**, checklist, internal memo | `DraftTaskType` + UI |
| Improvement from edits | SQLite + Chroma preference snippets; retrieval injects hints | Second draft “Operator preferences” block |
| API + UI + Docker + tests | FastAPI, static UI, compose, pytest | This doc + CI-style commands below |

## Automated tests

Run (from `legal_workflow/` with dependencies installed):

```powershell
$env:PYTHONPATH="."
python -m pytest tests/ -q
```

Or inside Docker (from `Assessment_AI/`):

```powershell
docker compose run --rm api pytest tests/ -q
```

**Expected:** **6** tests pass (health, `/ready`, chunking, RRF, PDF magic validation).

## Manual checks (synthetic lease)

Use `samples/input/synthetic_lease.pdf` (generate via `python scripts/build_sample_pdf.py` if missing).

1. **Upload** `POST /documents/upload`  
   - Expect `200`, UUID `document_id`, `structured.money_amounts` contains `$1,850.00`, `structured.inferred_doc_types` contains `lease_agreement`, and non-empty `title_or_heading_candidates` / `notice_related_snippets` when applicable.

2. **Draft (extractive, no Gemini key)** `POST /drafts/generate` with `task: case_fact_summary`  
   - Expect markdown with `[E#]` citations; `evidence` length matches cited spans; `used_llm` false in `retrieval_debug`.

3. **Draft tasks** `title_review_summary`, `notice_related_summary`  
   - Expect section headers appropriate to task; bullets still cite `[E#]`.

4. **Edit loop** `POST /edits/feedback` with rephrased operator markdown vs system draft  
   - Expect `status: stored`, `learned_snippet_rows` ≥ 1, `vector_preferences_written` ≥ 1.

5. **Regenerate** same document with same task  
   - Optional: confirm “Operator preferences” block appears in markdown when hints retrieved (depends on diff content).

## Production-oriented checks

| Check | Command / action | Pass criteria |
|-------|------------------|---------------|
| Liveness | `GET /health` | `{"status":"ok"}` |
| Readiness | `GET /ready` | `ready: true` (DB + writable data dir) |
| PDF validation | Upload non-PDF bytes renamed `.pdf` | `400` missing `%PDF` |
| Oversize | Upload > `LEGAL_WORKFLOW_MAX_UPLOAD_BYTES` | `400` |
| Auth (when configured) | Omit `X-API-Key` with `LEGAL_WORKFLOW_API_KEY` set | `401` on data routes; `/health` still `200` |
| Rate limit | Burst > limit from one IP | `429` with `Retry-After` (only non-docs routes) |

## Results (representative)

| Check | Outcome |
|-------|---------|
| pytest | **Pass** (6 tests in Docker: health, `/ready`, chunking, RRF, PDF magic, readiness) |
| Upload synthetic lease | **Pass** — structured money + lease tag |
| Grounded draft | **Pass** — extractive cites evidence IDs |
| Edit feedback stored | **Pass** — JSON `stored` + snippet counts |
| Readiness endpoint | **Pass** — returns DB + storage status |

> Re-run the manual rows after any dependency or model change; embedding first-load can take ~60s cold start in Docker.

## Limitations (honest)

- **Handwriting / extreme illegibility:** generic Tesseract only; no specialized HTR.
- **Non-PDF inputs:** out of scope; extend ingestion for images/email separately.
- **Measured retrieval MRR/NDCG:** not computed in CI; hybrid design is the evidence-backed choice for rare tokens + semantics.
