"""PDF upload validation (magic bytes, size handled at route)."""

from __future__ import annotations


def is_pdf_magic(data: bytes) -> bool:
    if len(data) < 4:
        return False
    return data[:4] == b"%PDF"
