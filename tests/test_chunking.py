from app.services.chunking import chunk_pages
from app.models.schemas import PageBlock


def test_chunking_splits_long_page():
    long = "word " * 500
    pages = [PageBlock(page_index=0, text=long, source="native_text")]
    chunks = chunk_pages(pages)
    assert len(chunks) >= 2
    assert all(c.page_index == 0 for c in chunks)
