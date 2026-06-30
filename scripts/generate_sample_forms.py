#!/usr/bin/env python3
"""Generate filled, form-like sample tax-form PDFs for local CPA renamer testing.

The samples are fake training documents. They are intentionally generated with
plain PDF drawing commands (no third-party dependencies) so contributors can
rebuild them in a minimal environment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "samples" / "source_forms"
PAGE_WIDTH = 792
PAGE_HEIGHT = 612


@dataclass
class PdfCanvas:
    commands: list[str] = field(default_factory=list)

    def text(self, x: float, y: float, value: str, size: int = 10, bold: bool = False) -> None:
        font = "F2" if bold else "F1"
        self.commands.append(f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({pdf_escape(value)}) Tj ET")

    def rect(self, x: float, y: float, width: float, height: float, stroke: bool = True, fill_gray: float | None = None) -> None:
        if fill_gray is not None:
            self.commands.append(f"q {fill_gray:.2f} g {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f Q")
        if stroke:
            self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re S")

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def thick_rect(self, x: float, y: float, width: float, height: float, line_width: float = 2.0) -> None:
        self.commands.append(f"q {line_width:.2f} w {x:.2f} {y:.2f} {width:.2f} {height:.2f} re S Q")

    def label_value(self, x: float, y: float, label: str, value: str, width: float = 220, height: float = 44) -> None:
        self.rect(x, y, width, height)
        self.text(x + 6, y + height - 14, label, 8, bold=True)
        self.text(x + 6, y + 10, value, 10)


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(canvas: PdfCanvas) -> bytes:
    stream = "\n".join(canvas.commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 792 612] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
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
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def w2_canvas() -> PdfCanvas:
    c = PdfCanvas()
    c.rect(12, 84, 768, 500)
    c.thick_rect(175, 548, 185, 36, 2)
    c.text(185, 570, "a  Employee's social security number", 10, True)
    c.text(235, 558, "XXX-XX-4821", 10)
    c.text(372, 556, "OMB No. 1545-0029", 10)
    c.text(476, 568, "Safe, accurate,", 10, True)
    c.text(476, 556, "FAST! Use", 10, True)
    c.text(650, 568, "Visit the IRS website at", 10)
    c.text(655, 556, "www.irs.gov/efile.", 10, True)

    c.label_value(12, 505, "b  Employer identification number (EIN)", "12-3456789", 420, 43)
    c.rect(12, 395, 420, 110)
    c.text(20, 490, "c  Employer's name, address, and ZIP code", 10, True)
    c.text(20, 470, "ATLANTIC INDUSTRIAL SERVICES INC", 10)
    c.text(20, 454, "420 MARKET ST", 10)
    c.text(20, 438, "NEWARK, NJ 07105", 10)
    c.label_value(12, 360, "d  Control number", "A1B2C3", 420, 35)
    c.rect(12, 215, 420, 145)
    c.text(20, 348, "e  Employee's first name and initial", 10, True)
    c.text(210, 348, "Last name", 10)
    c.text(400, 348, "Suff.", 10)
    c.text(20, 330, "JOHN A", 10)
    c.text(210, 330, "SMITH", 10)
    c.text(20, 275, "125 MAIN ST APT 2B", 10)
    c.text(20, 259, "NEWARK, NJ 07102", 10)
    c.text(20, 220, "f  Employee's address and ZIP code", 10, True)

    x = 432
    box_w = 174
    labels = [
        ("1  Wages, tips, other compensation", "85,000.00"),
        ("3  Social security wages", "85,000.00"),
        ("5  Medicare wages and tips", "85,000.00"),
        ("7  Social security tips", "0.00"),
        ("11  Nonqualified plans", "0.00"),
    ]
    y = 548
    for label, value in labels:
        c.rect(x, y - 34, box_w, 34)
        c.text(x + 10, y - 14, label, 10, True)
        c.text(x + box_w - 52, y - 30, value, 10)
        y -= 34
    labels_right = [
        ("2  Federal income tax withheld", "10,250.00"),
        ("4  Social security tax withheld", "5,270.00"),
        ("6  Medicare tax withheld", "1,232.50"),
        ("8  Allocated tips", "0.00"),
        ("10  Dependent care benefits", "0.00"),
    ]
    y = 548
    for label, value in labels_right:
        c.rect(x + box_w, y - 34, box_w, 34)
        c.text(x + box_w + 10, y - 14, label, 10, True)
        c.text(x + 2 * box_w - 58, y - 30, value, 10)
        y -= 34
    c.rect(432, 283, 174, 62)
    c.text(438, 328, "13", 10, True)
    c.text(456, 328, "Statutory", 7)
    c.text(456, 319, "employee", 7)
    c.rect(456, 304, 14, 14)
    c.text(507, 328, "Retirement", 7)
    c.text(507, 319, "plan", 7)
    c.rect(508, 304, 14, 14)
    c.text(513, 307, "X", 10, True)
    c.text(558, 328, "Third-party", 7)
    c.text(558, 319, "sick pay", 7)
    c.rect(560, 304, 14, 14)
    c.rect(606, 215, 174, 130)
    for i, code in enumerate(["12a  Code D     8,200.00", "12b  Code DD    7,950.00", "12c  Code C         0.00", "12d  Code W         0.00"]):
        yy = 326 - i * 31
        c.text(612, yy, code, 9, True if i == 0 else False)
        if i:
            c.line(606, yy + 10, 780, yy + 10)
    c.rect(432, 215, 174, 68)
    c.text(438, 268, "14a Other", 10, True)
    c.text(438, 252, "NJ UI/WF/SWF 185.00", 8)
    c.text(438, 222, "14b Treasury Tipped Occupation Code(s)", 9, True)

    c.rect(12, 84, 768, 68)
    for xline in [54, 238, 362, 474, 598, 710]:
        c.line(xline, 84, xline, 152)
    c.text(16, 140, "15  State", 9, True)
    c.text(62, 140, "Employer's state ID number", 9)
    c.text(242, 140, "16  State wages, tips, etc.", 9, True)
    c.text(366, 140, "17  State income tax", 9, True)
    c.text(478, 140, "18  Local wages, tips, etc.", 9, True)
    c.text(602, 140, "19  Local income tax", 9, True)
    c.text(716, 140, "20  Locality name", 9, True)
    c.text(16, 98, "NJ", 9)
    c.text(60, 98, "NJ-123456789", 9)
    c.text(320, 98, "85,000.00", 9)
    c.text(436, 98, "3,100.00", 9)
    c.text(562, 98, "85,000.00", 9)
    c.text(676, 98, "1,125.00", 9)
    c.text(728, 98, "NEWARK", 8)
    c.text(42, 48, "Form", 10, True)
    c.text(72, 40, "W-2", 26, True)
    c.text(140, 46, "Wage and Tax Statement", 14, True)
    c.text(375, 36, "2026", 30, True)
    c.text(540, 50, "Department of the Treasury--Internal Revenue Service", 10)
    c.text(12, 24, "Copy B--To Be Filed With Employee's FEDERAL Tax Return.", 11, True)
    return c


def header_form(title: str, subtitle: str) -> PdfCanvas:
    c = PdfCanvas()
    c.rect(36, 72, 720, 480)
    c.text(50, 526, "SAMPLE - NOT FOR FILING", 9)
    c.text(555, 522, title, 22, True)
    c.text(555, 496, subtitle, 16, True)
    c.line(36, 472, 756, 472)
    c.line(520, 72, 520, 552)
    return c


def info_block(c: PdfCanvas, heading: str, lines: list[str]) -> None:
    c.text(50, 450, heading, 9, True)
    y = 426
    for line in lines:
        c.text(50, y, line, 10)
        y -= 18


def tax_form_canvas(kind: str) -> PdfCanvas:
    if kind == "1099_INT":
        c = header_form("Form 1099-INT", "Interest Income")
        info_block(c, "PAYER'S name, street address, city or town, state or province, country, ZIP", [
            "Garden State Community Bank", "100 Market Street", "Newark, NJ 07102", "Account number SAV-77120493",
        ])
        boxes = [("1 Interest income", "742.36"), ("3 Interest on U.S. Savings Bonds", "125.40"), ("4 Federal income tax withheld", "74.00")]
    elif kind == "1099_DIV":
        c = header_form("Form 1099-DIV", "Dividends and Distributions")
        info_block(c, "Payer:", ["Fidelity Investments LLC", "Recipient: John A Smith", "TIN: XXX-XX-4821"])
        c.text(50, 502, "1099_DIV_filled_sample", 9)
        boxes = [("1a Ordinary dividends", "1,845.70"), ("1b Qualified dividends", "1,500.20"), ("2a Capital gain dist.", "380.50")]
    elif kind == "1099_NEC":
        c = header_form("Form 1099-NEC", "Nonemployee Compensation")
        info_block(c, "Payer:", ["ABC Construction LLC", "Recipient: John A Smith", "TIN: XXX-XX-4821"])
        c.text(50, 502, "1099_NEC_filled_sample", 9)
        boxes = [("1 Nonemployee compensation", "42,680.00"), ("4 Federal income tax withheld", "0.00")]
    elif kind == "1099_MISC":
        c = header_form("Form 1099-MISC", "Miscellaneous Information")
        info_block(c, "Payer:", ["Sunrise Properties LLC", "Recipient: John A Smith", "TIN: XXX-XX-4821"])
        c.text(50, 502, "1099_MISC_filled_sample", 9)
        boxes = [("1 Rents", "18,000.00"), ("3 Other income", "250.00")]
    elif kind == "1098":
        c = header_form("Form 1098", "Mortgage Interest Statement")
        info_block(c, "Lender:", ["Bank of America", "Borrower: John A Smith", "Borrower TIN: XXX-XX-4821"])
        c.text(50, 502, "1098_filled_sample", 9)
        boxes = [("1 Mortgage interest received", "11,842.17"), ("2 Outstanding mortgage principal", "356,420.00")]
    else:
        c = header_form("Schedule K-1", "Partner's Share of Income")
        info_block(c, "Partnership:", ["ABC Holdings LLC", "Partner: John A Smith", "Partner TIN: XXX-XX-4821"])
        c.text(50, 502, "K1_filled_sample", 9)
        boxes = [("1 Ordinary business income", "18,250"), ("5 Interest income", "420"), ("6 Dividends", "260")]
    y = 420
    for label, value in boxes:
        c.rect(540, y - 52, 180, 52)
        c.text(548, y - 16, label, 9, True)
        c.text(650, y - 42, value, 11)
        y -= 52
    c.text(545, 92, "Copy B - For recipient records", 9, True)
    return c


BUILDERS = {
    "W2_filled_sample.pdf": w2_canvas,
    "1099_INT_filled_sample.pdf": lambda: tax_form_canvas("1099_INT"),
    "1099_DIV_filled_sample.pdf": lambda: tax_form_canvas("1099_DIV"),
    "1099_NEC_filled_sample.pdf": lambda: tax_form_canvas("1099_NEC"),
    "1099_MISC_filled_sample.pdf": lambda: tax_form_canvas("1099_MISC"),
    "1098_filled_sample.pdf": lambda: tax_form_canvas("1098"),
    "K1_filled_sample.pdf": lambda: tax_form_canvas("K1"),
}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, builder in BUILDERS.items():
        path = OUTPUT_DIR / filename
        path.write_bytes(build_pdf(builder()))
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
