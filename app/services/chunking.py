from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from app.config import settings
from app.models.schemas import PageBlock


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class TextChunk:
    chunk_id: str
    page_index: int | None
    text: str
    source: str


def chunk_pages(pages: list[PageBlock]) -> list[TextChunk]:
    size = settings.chunk_size
    overlap = settings.chunk_overlap
    chunks: list[TextChunk] = []

    for pb in pages:
        raw = _norm_ws(pb.text)
        if not raw:
            continue
        start = 0
        n = len(raw)
        while start < n:
            end = min(n, start + size)
            piece = raw[start:end]
            if piece:
                stable = f"{pb.page_index}:{start}:{hashlib.sha256(piece.encode()).hexdigest()[:12]}"
                cid = str(uuid.uuid5(uuid.NAMESPACE_URL, stable))
                chunks.append(
                    TextChunk(
                        chunk_id=cid,
                        page_index=pb.page_index,
                        text=piece,
                        source=pb.source,
                    )
                )
            if end >= n:
                break
            start = max(0, end - overlap)

    return chunks
