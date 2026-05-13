from __future__ import annotations

import io
import logging
import re
import uuid
from dataclasses import dataclass

import fitz  # PyMuPDF
from PIL import Image

from app.config import settings
from app.models.schemas import PageBlock, StructuredCaseFields

logger = logging.getLogger(__name__)

try:
    import pytesseract

    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


@dataclass
class IngestResult:
    document_id: str
    pages: list[PageBlock]
    warnings: list[str]


_DATE_PATTERNS = [
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
]
_MONEY_PATTERN = r"\$[\d,]+(?:\.\d{2})?"
_PARTY_KEYWORDS = (
    "plaintiff",
    "defendant",
    "petitioner",
    "respondent",
    "claimant",
    "lessor",
    "lessee",
    "landlord",
    "tenant",
    "buyer",
    "seller",
)


def _extract_dates(text: str) -> list[str]:
    found: set[str] = set()
    for pat in _DATE_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            found.add(m.group(0).strip())
    return sorted(found)[:50]


def _extract_money(text: str) -> list[str]:
    return list({m.group(0) for m in re.finditer(_MONEY_PATTERN, text)})[:30]


def _infer_parties_lines(text: str) -> list[str]:
    hints: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if any(k in low for k in _PARTY_KEYWORDS) and len(line.strip()) < 200:
            hints.append(line.strip())
    return hints[:25]


def _section_headings(text: str) -> list[str]:
    heads: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(ARTICLE|SECTION|I{1,3}V?|VI{0,3}|IX|X|XI{0,3})\b", s, re.I):
            heads.append(s[:200])
        elif len(s) < 80 and s.isupper():
            heads.append(s)
    return heads[:30]


def _infer_doc_types(text: str) -> list[str]:
    low = text.lower()
    tags: list[str] = []
    mapping = [
        ("lease", "lease_agreement"),
        ("employment", "employment_related"),
        ("complaint", "pleading"),
        ("motion", "motion"),
        ("contract", "contract"),
        ("notice", "notice"),
        ("settlement", "settlement"),
        ("confidential", "confidentiality"),
    ]
    for needle, label in mapping:
        if needle in low:
            tags.append(label)
    return sorted(set(tags))


def extract_structured_fields(full_text: str) -> StructuredCaseFields:
    notes: list[str] = []
    if len(full_text.strip()) < 50:
        notes.append("Very little text extracted; document may be image-only or corrupted.")
    return StructuredCaseFields(
        inferred_doc_types=_infer_doc_types(full_text),
        dates_mentioned=_extract_dates(full_text),
        party_hints=_infer_parties_lines(full_text),
        money_amounts=_extract_money(full_text),
        section_headings=_section_headings(full_text),
        confidence_notes=notes,
    )


def _ocr_image(pil_image: Image.Image) -> str:
    if not _HAS_TESSERACT:
        return ""
    try:
        return pytesseract.image_to_string(pil_image) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("OCR failed: %s", e)
        return ""


def ingest_pdf_bytes(data: bytes, filename: str = "upload.pdf") -> IngestResult:
    warnings: list[str] = []
    doc_id = str(uuid.uuid4())
    pages: list[PageBlock] = []

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not open PDF: {e}") from e

    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            text = page.get_text("text") or ""
            text = text.strip()
            source = "native_text"
            if len(text) < settings.ocr_char_threshold:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_text = _ocr_image(img)
                if ocr_text.strip():
                    text = ocr_text.strip()
                    source = "ocr"
                else:
                    if not _HAS_TESSERACT:
                        warnings.append(
                            f"Page {i + 1}: low native text and pytesseract/Tesseract not available for OCR."
                        )
                    else:
                        warnings.append(f"Page {i + 1}: OCR produced little text (noisy or blank scan).")
            pages.append(PageBlock(page_index=i, text=text, source=source))
    finally:
        doc.close()

    if not pages:
        warnings.append("No pages found in PDF.")

    return IngestResult(document_id=doc_id, pages=pages, warnings=warnings)


def ingest_pdf_path(path: str) -> IngestResult:
    with open(path, "rb") as f:
        return ingest_pdf_bytes(f.read(), filename=path)
