"""Create a small synthetic legal-style PDF for local testing (no external assets)."""

from __future__ import annotations

import sys
from pathlib import Path

import fitz


def build_pdf(out: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
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
    page.insert_text((72, 72), text, fontsize=11, fontname="helv")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    doc.close()
    print("Wrote", out)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "samples" / "input" / "synthetic_lease.pdf"
    build_pdf(target)
