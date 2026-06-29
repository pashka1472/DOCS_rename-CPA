#!/usr/bin/env python3
"""Generate filled sample tax-form PDFs for local CPA renamer testing.

The PDFs are intentionally simple text PDFs so they can be generated without
third-party dependencies and read by the fallback extractor in cpa_doc_renamer.py.
They contain fake data only and are not suitable for filing.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "samples" / "source_forms"

SAMPLES: dict[str, list[str]] = {
    "W2_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "Form W-2 Wage and Tax Statement",
        "Employer's name, address, and ZIP code",
        "Hudson Sample Manufacturing Inc.",
        "245 River Road, Suite 200",
        "Jersey City, NJ 07302",
        "Employee: Alex R. Morgan",
        "Wages, tips, other compensation: $84,750.00",
    ],
    "1099_INT_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "Form 1099-INT Interest Income",
        "PAYER'S name, street address, city or town, state or province, country, ZIP",
        "Garden State Community Bank",
        "100 Market Street",
        "Newark, NJ 07102",
        "Account number SAV-77120493",
        "Interest income: $742.36",
    ],
    "1099_DIV_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "1099_DIV_filled_sample",
        "Payer: Fidelity Investments LLC",
        "Recipient: John A Smith",
        "TIN: XXX-XX-4821",
        "Ordinary dividends: $1,845.70",
        "Qualified dividends: $1,500.20",
    ],
    "1099_NEC_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "1099_NEC_filled_sample",
        "Payer: ABC Construction LLC",
        "Recipient: John A Smith",
        "TIN: XXX-XX-4821",
        "Nonemployee compensation: $42,680.00",
    ],
    "1099_MISC_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "1099_MISC_filled_sample",
        "Payer: Sunrise Properties LLC",
        "Recipient: John A Smith",
        "TIN: XXX-XX-4821",
        "Rents: $18,000.00",
        "Other income: $250.00",
    ],
    "1098_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "1098_filled_sample",
        "Lender: Bank of America",
        "Borrower: John A Smith",
        "Borrower TIN: XXX-XX-4821",
        "Mortgage interest: $11,842.17",
        "Outstanding principal: $356,420.00",
    ],
    "K1_filled_sample.pdf": [
        "SAMPLE - NOT FOR FILING",
        "K1_filled_sample",
        "Partnership: ABC Holdings LLC",
        "Partner: John A Smith",
        "Partner TIN: XXX-XX-4821",
        "Ordinary business income: $18,250",
        "Interest income: $420",
    ],
}


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_text_pdf(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 12 Tf", "72 742 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            content_lines.append("T*")
        content_lines.append(f"({pdf_escape(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f\n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n\n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, lines in SAMPLES.items():
        path = OUTPUT_DIR / filename
        path.write_bytes(build_text_pdf(lines))
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
