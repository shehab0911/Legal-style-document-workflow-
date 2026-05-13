from app.services.pdf_validate import is_pdf_magic


def test_pdf_magic_accepts_minimal_header():
    assert is_pdf_magic(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")


def test_pdf_magic_rejects_non_pdf():
    assert not is_pdf_magic(b"<!DOCTYPE html>")
    assert not is_pdf_magic(b"")
