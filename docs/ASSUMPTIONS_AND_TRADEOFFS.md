# Assumptions and tradeoffs

## Assumptions

- Primary file format for this reference build is **PDF**; other “messy legal” containers (email .msg, scans bundled as PNG) are out of scope but the OCR path is the extension point.
- **Operators are trusted**; there is no multi-tenant hardening, authn/z, or encryption at rest beyond filesystem permissions.
- **“Legal correctness”** is explicitly out of scope per the brief; the system optimizes for **grounding and traceability**, not substantive legal advice.
- Edit learning is **document-scoped** by default (preferences keyed to `document_id`). Cross-matter style transfer would need an explicit org-level namespace and governance.

## Tradeoffs

| Area | Choice | Why |
|------|--------|-----|
| Extraction | Heuristics vs LLM | Predictable, cheap, offline-friendly; misses nuance but avoids hallucinated “structure”. |
| Retrieval | Chroma + BM25 + RRF | Better recall on proper nouns and amounts than dense-only; more moving parts than a single retriever. |
| Drafting | Extractive default | Maximizes grounding; reads less fluently than abstractive LLM prose. |
| OCR | Tesseract optional | Strong baseline without cloud OCR; struggles on handwriting compared with specialized APIs. |
| Storage | SQLite + local Chroma | Simple ops for assessment/demo; production at scale would likely use Postgres + managed vector store + object storage for originals. |
| Learning | Snippet + vector memory | Lightweight improvement loop without full model fine-tuning; not a substitute for curated playbooks. |

## Known limitations

- Very large PDF corpora are not sharded; ingestion is synchronous in the request.  
- Chroma metadata uses integer `page_index` (-1 sentinel when unknown in older paths); UI should treat unknown pages gracefully.  
- First embedding model download is heavy; pin versions in `requirements.txt` for reproducibility.
