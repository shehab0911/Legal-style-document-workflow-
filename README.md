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
│       ├── generation.py       # Extractive drafts + optional OpenAI
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
$env:PYTHONPATH="."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Web UI:** http://127.0.0.1:8000/  
- **OpenAPI:** http://127.0.0.1:8000/docs  

**Data directory** (SQLite + Chroma): defaults to `./data`. Override with `LEGAL_WORKFLOW_DATA_DIR`.

**Optional LLM drafting:** set `OPENAI_API_KEY` (or `LEGAL_WORKFLOW_OPENAI_API_KEY` via `.env`). Without it, the service uses **strict extractive** drafting from retrieved chunks only.

## Docker

```powershell
cd legal_workflow
docker compose up --build
```

The image installs Tesseract for OCR. Mount `/data` via the compose volume for persistence.

## API (summary)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/documents/upload` | multipart `file` (PDF) → `document_id`, structured fields, chunk index |
| POST | `/drafts/generate` | JSON `DraftRequest` → markdown draft + `evidence[]` + `citations[]` |
| POST | `/edits/feedback` | system vs operator markdown → diff summary + learned snippets (SQL + Chroma) |
| GET | `/documents/{id}/edits` | recent edit sessions |

