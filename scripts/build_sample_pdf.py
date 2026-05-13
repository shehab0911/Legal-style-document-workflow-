"""Create a small synthetic legal-style PDF for local testing (no external assets).

Uses fpdf2 only so `python scripts/build_sample_pdf.py` works after
`pip install fpdf2` even if PyMuPDF (fitz) is not installed yet.
"""

from __future__ import annotations

import sys
from pathlib import Path


def build_pdf(out: Path) -> None:
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise SystemExit(
            "Missing dependency: pip install fpdf2\n"
            "(or install full stack: pip install -r requirements.txt)"
        ) from e

    text = """
RESIDENTIAL LEASE AGREEMENT

This Lease is entered into as of March 12, 2024 between Lessor ABC Properties LLC
("Landlord") and Lessee Jane Doe ("Tenant") for the premises at 100 Main Street.

1. Term. The lease term shall be twelve (12) months commencing April 1, 2024.

2. Rent. Monthly rent shall be $1,850.00 due on the first of each month. Late fees of $75
apply after the 5th calendar day.

3. Security Deposit. Tenant shall deposit $1,850.00 as security, refundable subject to
deductions for unpaid rent or damage beyond ordinary wear and tear.

4. Notice. Either party may terminate with thirty (30) days written notice after the
initial term.

5. Maintenance. Tenant must promptly notify Landlord of water leaks or electrical hazards.
""".strip()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, text)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    print("Wrote", out)


if __name__ == "__main__":
    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "samples" / "input" / "synthetic_lease.pdf"
    )
    build_pdf(target)
