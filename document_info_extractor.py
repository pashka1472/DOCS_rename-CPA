#!/usr/bin/env python3
"""Extract text from PDF and image documents and write an information file."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".img", ".jpeg", ".jpg"}
IMAGE_EXTENSIONS = {".png", ".img", ".jpeg", ".jpg"}
PDF_EXTENSION = ".pdf"
OCR_SETUP_HELP = (
    "Install Python packages with: python -m pip install -r requirements.txt. "
    "Also install the Tesseract OCR application and ensure the tesseract command is on PATH."
)


@dataclass(frozen=True)
class DocumentInfo:
    source_path: str
    file_name: str
    file_extension: str
    parser: str
    text: str
    line_count: int
    character_count: int
    warnings: list[str]


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def decode_pdf_literal(value: bytes) -> str:
    result = bytearray()
    index = 0
    while index < len(value):
        char = value[index]
        if char == 92 and index + 1 < len(value):
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
    data = path.read_bytes()
    text_parts = [
        decode_pdf_literal(match.group(1))
        for match in re.finditer(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", data, re.DOTALL)
    ]
    return normalize_text("\n".join(text_parts))


def extract_text_from_pdf(path: Path) -> tuple[str, str, list[str]]:
    if module_available("pypdf"):
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return normalize_text(text), "pypdf", []

    text = extract_text_from_simple_pdf(path)
    warning = "pypdf is not installed; used simple PDF text fallback"
    return text, "simple_pdf_fallback", [warning]


def extract_text_from_image(path: Path) -> tuple[str, str, list[str]]:
    missing = [name for name in ("PIL", "pytesseract") if not module_available(name)]
    if missing:
        warning = "image OCR requires Pillow and pytesseract; missing: " + ", ".join(missing)
        return "", "ocr_unavailable", [warning, OCR_SETUP_HELP]

    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore

    with Image.open(path) as image:
        text = pytesseract.image_to_string(image)
    return normalize_text(text), "pytesseract", []


def extract_document_info(path: Path) -> DocumentInfo:
    resolved = path.expanduser().resolve()
    extension = resolved.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file extension '{extension}'. Supported extensions: {supported}")
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    if not resolved.is_file():
        raise ValueError(f"Not a file: {resolved}")

    if extension == PDF_EXTENSION:
        text, parser, warnings = extract_text_from_pdf(resolved)
    else:
        text, parser, warnings = extract_text_from_image(resolved)

    lines = text.splitlines() if text else []
    return DocumentInfo(
        source_path=str(resolved),
        file_name=resolved.name,
        file_extension=extension.lstrip("."),
        parser=parser,
        text=text,
        line_count=len(lines),
        character_count=len(text),
        warnings=warnings,
    )


def info_to_text(info: DocumentInfo) -> str:
    warnings = "\n".join(f"- {warning}" for warning in info.warnings) or "None"
    return (
        f"Source: {info.source_path}\n"
        f"File name: {info.file_name}\n"
        f"File extension: {info.file_extension}\n"
        f"Parser: {info.parser}\n"
        f"Lines: {info.line_count}\n"
        f"Characters: {info.character_count}\n"
        f"Warnings:\n{warnings}\n\n"
        f"Extracted text:\n{info.text}\n"
    )


def write_output(infos: list[DocumentInfo], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        payload: dict[str, Any] = {"documents": [asdict(info) for info in infos]}
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    sections = []
    for index, info in enumerate(infos, start=1):
        sections.append(f"Document {index}\n{'=' * 10}\n{info_to_text(info)}")
    output_path.write_text("\n".join(sections), encoding="utf-8")


def collect_dependency_status() -> dict[str, bool]:
    return {
        "pypdf": module_available("pypdf"),
        "Pillow": module_available("PIL"),
        "pytesseract": module_available("pytesseract"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract text from PDF/image documents and save document information.")
    parser.add_argument("inputs", nargs="*", type=Path, help="Input files: pdf, png, img, jpeg, jpg")
    parser.add_argument("-o", "--output", type=Path, default=Path("document_info.json"), help="Output info file")
    parser.add_argument("--format", choices=("json", "txt"), default="json", help="Output file format")
    parser.add_argument("--check-dependencies", action="store_true", help="Print optional PDF/OCR dependency status and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_dependencies:
        print(json.dumps({"dependencies": collect_dependency_status(), "ocr_setup_help": OCR_SETUP_HELP}, indent=2))
        return 0
    if not args.inputs:
        raise SystemExit("No input files provided. Pass documents or use --check-dependencies.")
    infos = [extract_document_info(path) for path in args.inputs]
    write_output(infos, args.output, args.format)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
