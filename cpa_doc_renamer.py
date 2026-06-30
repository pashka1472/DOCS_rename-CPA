#!/usr/bin/env python3
"""CPA document PDF converter and tax-form renamer.

Converts image/PDF inputs to a PDF output and names the file from document text.
Optional packages improve extraction/conversion: pypdf, pillow, pytesseract.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
PDF_SUFFIX = ".pdf"
UNKNOWN_PREFIX = "unknown_tax_document"


@dataclass(frozen=True)
class NamingResult:
    filename_stem: str
    document_type: str
    issuer: str | None = None
    account_last4: str | None = None


def sanitize_filename_part(value: str) -> str:
    """Return a filesystem-friendly part while preserving readable names."""
    value = value.strip().replace("\u2019", "'").replace("\u2018", "'")
    value = re.sub(r"[\\/:*?\"<>|]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ._-")


def slug_company(value: str) -> str:
    """Return lowercase underscore broker/lender names for compact 1099/1098 names."""
    value = sanitize_filename_part(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


def normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r", "\n"))


def extract_text_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return extract_text_from_simple_pdf(path)

    chunks: list[str] = []
    reader = PdfReader(str(path))
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def decode_pdf_literal(value: bytes) -> str:
    """Decode a basic PDF literal string used by simple generated fixtures."""
    result = bytearray()
    index = 0
    while index < len(value):
        char = value[index]
        if char == 92 and index + 1 < len(value):  # backslash
            index += 1
            escaped = value[index]
            result.extend({
                ord("n"): b"\n",
                ord("r"): b"\r",
                ord("t"): b"\t",
                ord("b"): b"\b",
                ord("f"): b"\f",
                ord("("): b"(",
                ord(")"): b")",
                ord("\\"): b"\\",
            }.get(escaped, bytes([escaped])))
        else:
            result.append(char)
        index += 1
    return result.decode("latin-1", errors="replace")


def extract_text_from_simple_pdf(path: Path) -> str:
    """Best-effort fallback for simple text PDFs when pypdf is unavailable."""
    data = path.read_bytes()
    text_parts = [
        decode_pdf_literal(match.group(1))
        for match in re.finditer(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", data, re.DOTALL)
    ]
    return "\n".join(text_parts)


def extract_text_from_image(path: Path) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return ""

    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


def extract_text(path: Path, fallback_text: str | None = None) -> str:
    if fallback_text:
        return normalize_text(fallback_text)
    suffix = path.suffix.lower()
    if suffix == PDF_SUFFIX:
        return normalize_text(extract_text_from_pdf(path))
    if suffix in IMAGE_SUFFIXES:
        return normalize_text(extract_text_from_image(path))
    return ""


def convert_to_pdf(input_path: Path, output_path: Path) -> None:
    """Convert images to PDF or copy/rewrite existing PDFs to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = input_path.suffix.lower()

    if suffix == PDF_SUFFIX:
        if input_path.resolve() != output_path.resolve():
            shutil.copyfile(input_path, output_path)
        return

    if suffix not in IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported input extension: {input_path.suffix}")

    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Image conversion requires Pillow: pip install pillow") from exc

    with Image.open(input_path) as image:
        frames = []
        for frame_index in range(getattr(image, "n_frames", 1)):
            image.seek(frame_index)
            frame = image.convert("RGB")
            frames.append(frame.copy())
        first, rest = frames[0], frames[1:]
        first.save(output_path, "PDF", save_all=bool(rest), append_images=rest)


def first_match(patterns: Iterable[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return sanitize_filename_part(match.group(1))
    return None


def find_payer_or_issuer(text: str) -> str | None:
    return first_match(
        [
            r"PAYER['’]?S? name[^\n]*\n\s*([^\n]+)",
            r"Payer(?:'s)?(?: name)?(?: and address)?\s*[:\-]\s*([^\n]+)",
            r"Broker(?:'s)?(?: name)?\s*[:\-]\s*([^\n]+)",
            r"Partnership(?:'s)?(?: name)?\s*[:\-]\s*([^\n]+)",
            r"Employer(?:'s)? name(?:, address, and ZIP code| and address)?\s*[:\-]?\s*([^\n]+)",
            r"Issuer(?:'s)? name\s*[:\-]?\s*([^\n]+)",
            r"Lender(?:'s)?(?: name)?\s*[:\-]\s*([^\n]+)",
            r"^\s*([A-Z][^\n]*(?:Bank|Credit Union|Brokerage|Investments|Securities|Financial)[^\n]*)\s*$",
        ],
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )


def find_broker_or_lender(text: str) -> str | None:
    known = [
        "Fidelity", "Charles Schwab", "Robinhood", "E*TRADE", "Morgan Stanley",
        "Vanguard", "TD Ameritrade", "Interactive Brokers", "Merrill Lynch",
        "Chase Bank", "Wells Fargo", "Bank of America", "Citi", "Capital One",
    ]
    lower = text.lower()
    for name in known:
        if name.lower() in lower:
            return name
    return find_payer_or_issuer(text)


def find_account_last4(text: str) -> str | None:
    account_line = re.search(r"account(?: number| no\.?| #)?[^\n]*", text, re.IGNORECASE)
    if account_line:
        digits = re.findall(r"\d", account_line.group(0))
        if len(digits) >= 4:
            return "".join(digits[-4:])

    return first_match(
        [
            r"(?:x{2,}|\*{2,}|ending in|ends in|last four)\D*(\d{4})(?!\d)",
            r"TIN[^\n]*?(\d{4})(?!\d)",
        ],
        text,
    )


def classify_document(text: str) -> NamingResult:
    text = normalize_text(text)
    lowered = text.lower()
    issuer = find_payer_or_issuer(text)
    broker = find_broker_or_lender(text)
    account_last4 = find_account_last4(text)

    if "form 1098" in lowered or re.search(r"\b1098(?=\W|_|$)", lowered):
        lender = broker or issuer or "unknown_lender"
        return NamingResult(f"1098_{slug_company(lender)}", "1098", lender)

    if "schedule k-1" in lowered or re.search(r"\bk[_-]?1(?=\W|_|$)", lowered):
        name = issuer or "unknown_issuer"
        return NamingResult(f"K1_{sanitize_filename_part(name)}", "K1", name)

    if re.search(r"\bw-?2\b", lowered) and "wage" in lowered:
        name = issuer or "unknown_employer"
        return NamingResult(f"W2_{sanitize_filename_part(name)}", "W2", name)

    if "nonemployee compensation" in lowered or re.search(r"\b1099[\s_-]*nec(?=\W|_|$)", lowered):
        name = issuer or "unknown_payer"
        return NamingResult(f"1099_NEC_{sanitize_filename_part(name)}", "1099-NEC", name)

    if "miscellaneous" in lowered or re.search(r"\b1099[\s_-]*misc(?=\W|_|$)", lowered):
        name = issuer or "unknown_payer"
        return NamingResult(f"1099_misc_{sanitize_filename_part(name)}", "1099-MISC", name)

    broker_slug = slug_company(broker or "unknown_broker")
    acct = account_last4 or "unknown_account"
    if "consolidated" in lowered:
        return NamingResult(f"1099_consolidated_{broker_slug}_{acct}", "1099 consolidated", broker, account_last4)
    if "dividend" in lowered or re.search(r"\b1099[\s_-]*div(?=\W|_|$)", lowered):
        return NamingResult(f"1099_dividends_{broker_slug}_{acct}", "1099-DIV", broker, account_last4)
    if "interest income" in lowered or re.search(r"\b1099[\s_-]*int(?=\W|_|$)", lowered):
        return NamingResult(f"1099_int_{broker_slug}_{acct}", "1099-INT", broker, account_last4)

    return NamingResult(UNKNOWN_PREFIX, "unknown")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique filename for {path}")


def process_document(input_path: Path, output_dir: Path, text_override: str | None = None) -> Path:
    text = extract_text(input_path, text_override)
    result = classify_document(text)
    output_path = unique_path(output_dir / f"{result.filename_stem}.pdf")
    convert_to_pdf(input_path, output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert CPA source documents to PDF and rename by tax form type.")
    parser.add_argument("input", type=Path, help="Input PDF, scan, or photo")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("renamed"), help="Directory for renamed PDFs")
    parser.add_argument("--text", help="Use provided OCR/text instead of extracting from the input file")
    parser.add_argument("--dry-run", action="store_true", help="Only print the filename that would be used")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    text = extract_text(args.input, args.text)
    result = classify_document(text)
    target = unique_path(args.output_dir / f"{result.filename_stem}.pdf")
    if args.dry_run:
        print(target)
        return 0
    convert_to_pdf(args.input, target)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
