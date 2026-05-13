# Legal-style document workflow 

Internal-style workflow: **ingest** messy PDFs (native text + optional OCR), **extract** lightweight structured fields, **retrieve** with hybrid dense + BM25 fusion, **draft** grounded outputs with **inspectable evidence IDs**, and **learn** from operator edits via stored diff snippets and a preference vector index.

## Folder layout

```
legal_workflow/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, routes, demo HTML
│   ├── config.py
│   ├── static/
│   │   └── index.html          # Minimal operator UI
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLModel tables
│   │   └── session.py          # Async SQLite + Chroma paths
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic API contracts
│   └── services/
│       ├── __init__.py
│       ├── ingestion.py        # PyMuPDF + optional Tesseract OCR
│       ├── chunking.py
│       ├── retrieval.py        # Chroma + BM25 + RRF fusion
│       ├── generation.py       # Extractive drafts + optional Gemini (Google AI)
│       └── edit_learning.py    # Persist edits + vector preferences
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ASSUMPTIONS_AND_TRADEOFFS.md
│   └── EVALUATION.md
├── samples/
│   ├── input/                  # synthetic_lease.pdf (see script)
│   └── output/                 # example JSON shape
├── scripts/
│   └── build_sample_pdf.py
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
└── README.md
```

## Setup

**Prerequisites:** Python 3.10+, ~4GB free disk for first-time `sentence-transformers` / PyTorch wheels, optional [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for scanned PDFs.

```powershell
cd legal_workflow
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts\build_sample_pdf.py
```

The sample PDF script uses **`fpdf2` only** (listed in `requirements.txt`), so it does not require PyMuPDF (`import fitz`). To generate the sample without installing the full stack: `pip install fpdf2`, then run the script.

```powershell
$env:PYTHONPATH="."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Web UI:** http://127.0.0.1:8000/  
- **DOCS (Swagger):** http://127.0.0.1:8000/docs  

**Data directory** (SQLite + Chroma): defaults to `./data`. Override with `LEGAL_WORKFLOW_DATA_DIR`.

**Optional LLM drafting:** set `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com/apikey) (also accepted: `GEMINI_API_KEY`, or `LEGAL_WORKFLOW_GOOGLE_API_KEY` in `.env`). Override the model with `LEGAL_WORKFLOW_GEMINI_MODEL` (default `gemini-2.0-flash`). Without a key, the service uses **strict extractive** drafting from retrieved chunks only.

## Docker

From this folder:

```powershell
cd legal_workflow
docker compose up --build
```

From the parent `Assessment_AI` folder (repo root), you can run the same stack with `docker compose up --build` using the root `docker-compose.yml`.

The image installs Tesseract for OCR. Mount `/data` via the compose volume for persistence. Pass a **Google AI Studio** key for Gemini-backed drafts, for example:

```powershell
$env:GOOGLE_API_KEY="your-key"
docker compose up --build
```

Or set `GOOGLE_API_KEY` in a `.env` file next to `docker-compose.yml`.

## API (summary)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB + storage) |
| POST | `/documents/upload` | multipart `file` (PDF) → `document_id`, structured fields, chunk index |
| POST | `/drafts/generate` | JSON `DraftRequest` → markdown draft + `evidence[]` + `citations[]` |
| POST | `/edits/feedback` | system vs operator markdown → diff summary + learned snippets (SQL + Chroma) |
| GET | `/documents/{id}/edits` | recent edit sessions |

**Draft tasks:** `case_fact_summary`, `title_review_summary`, `notice_related_summary`, `document_checklist`, `internal_memo`.

## Assessment brief coverage

PDF ingest (native + OCR + light image enhancement), structured fields (including title/notice-oriented lists), hybrid retrieval, five grounded draft modes, evidence/citation inspection, edit-learning loop, samples, docs (`docs/`), API, UI, Docker, and tests. See `docs/EVALUATION.md` for rubric mapping. Handwriting HTR, non-PDF formats, and hyperscale multi-tenant ops remain extension points (`docs/ASSUMPTIONS_AND_TRADEOFFS.md`).

## Production-style deployment

| Variable | Purpose |
|----------|---------|
| `LEGAL_WORKFLOW_ENVIRONMENT` | `development` (default) or `production` — production returns generic 500 bodies |
| `LEGAL_WORKFLOW_API_KEY` | If set, data routes require `X-API-Key` or `Authorization: Bearer` |
| `LEGAL_WORKFLOW_RATE_LIMIT_REQUESTS_PER_MINUTE` | Per-IP limit (`0` = off; default `120`) |
| `LEGAL_WORKFLOW_MAX_UPLOAD_BYTES` | Upload cap (default 40MB) |
| `LEGAL_WORKFLOW_MAX_PDF_PAGES` | Page cap (default 500) |
| `LEGAL_WORKFLOW_LOG_LEVEL` | e.g. `INFO` |

Docker: **HEALTHCHECK** on `/health`, Tesseract included, CPU PyTorch. For real production, add TLS at a reverse proxy, secret management, backups, and consider Postgres + managed vector search at scale.

