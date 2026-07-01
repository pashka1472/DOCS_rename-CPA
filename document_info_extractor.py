#!/usr/bin/env python3
"""Extract text from PDF and image documents and write an information file."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
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
    extracted_fields: dict[str, str | None]
    suggested_file_name: str | None
    renamed_path: str | None = None


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

    from PIL import ImageOps  # type: ignore

    with Image.open(path) as image:
        prepared = ImageOps.autocontrast(image.convert("L"))
        prepared = prepared.resize((prepared.width * 2, prepared.height * 2))
        text = pytesseract.image_to_string(prepared, config="--psm 6")
    return normalize_text(text), "pytesseract", []



FIELD_LABELS = {
    "payer_name": "PAYER’S name",
    "form": "Form",
    "account_number": "Account number (see instructions)",
}


def clean_field_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :.-")


def looks_like_label(value: str) -> bool:
    label_patterns = [
        r"^(street address|room or suite no\.?|city or town|state or province|country)$",
        r"^(payer.?s tin|recipient.?s tin|recipient.?s name)$",
        r"^form\b",
        r"^\d+[a-z]?\.\s+",
    ]
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in label_patterns)


def next_value_after_label(lines: list[str], label_pattern: str) -> str | None:
    for index, line in enumerate(lines):
        match = re.search(label_pattern, line, re.IGNORECASE)
        if not match:
            continue
        inline_value = clean_field_value(line[match.end():])
        if inline_value and not looks_like_label(inline_value):
            return inline_value
        for candidate in lines[index + 1:]:
            value = clean_field_value(candidate)
            if value and not looks_like_label(value):
                return value
    return None


def extract_form_value(text: str) -> str | None:
    patterns = [
        r"\bForm\s+([0-9]{4}(?:-[A-Z]+)?|W-?2|K-?1)\b",
        r"\b(1099[-_\s]?(?:NEC|MISC|INT|DIV)|1098|W-?2|K-?1)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_field_value(match.group(1).replace("_", "-").upper())
    return None


def clean_account_number_candidate(value: str) -> str | None:
    value = clean_field_value(value)
    if not value or looks_like_label(value):
        return None
    if re.search(r"2nd\s+TIN|state\s+tax|state/payer", value, re.IGNORECASE):
        return None
    before_amount = re.split(r"\s+\$", value, maxsplit=1)[0]
    match = re.search(r"\b(?:[A-Z]{2,10}-)?\d[A-Z0-9-]*\d\b", before_amount, re.IGNORECASE)
    return clean_field_value(match.group(0)) if match else None


def extract_account_number(text: str, lines: list[str]) -> str | None:
    label_pattern = r"account number(?:\s*\(see instructions\))?"
    for index, line in enumerate(lines):
        match = re.search(label_pattern, line, re.IGNORECASE)
        if not match:
            continue
        inline_value = clean_account_number_candidate(line[match.end():])
        if inline_value:
            return inline_value
        for candidate in lines[index + 1:]:
            value = clean_account_number_candidate(candidate)
            if value:
                return value
    match = re.search(r"\b[A-Z]{2,10}-\d{4}-\d{4,}\b", text, re.IGNORECASE)
    return clean_field_value(match.group(0)) if match else None


def extract_fields(text: str) -> dict[str, str | None]:
    lines = text.splitlines() if text else []
    return {
        FIELD_LABELS["payer_name"]: next_value_after_label(lines, r"payer[’'`]?s name"),
        FIELD_LABELS["form"]: extract_form_value(text),
        FIELD_LABELS["account_number"]: extract_account_number(text, lines),
    }


def normalize_form(form: str | None, text: str) -> str | None:
    normalized_form = form.upper().replace("_", "-").replace(" ", "-") if form else None
    if normalized_form in {"1099-INT", "1099-DIV", "1099-NEC", "1099-MISC", "1098", "W-2", "K-1"}:
        return normalized_form
    haystack = f"{form or ''}\n{text}".lower()
    if "consolidated" in haystack and "1099" in haystack:
        return "1099-CONSOLIDATED"
    if re.search(r"1099[-_\s]?misc|miscellaneous", haystack):
        return "1099-MISC"
    if re.search(r"1099[-_\s]?nec|nonemployee compensation", haystack):
        return "1099-NEC"
    if re.search(r"1099[-_\s]?int|interest income", haystack):
        return "1099-INT"
    if re.search(r"1099[-_\s]?div|dividends", haystack):
        return "1099-DIV"
    if re.search(r"\bw[-_\s]?2\b|wage and tax statement", haystack):
        return "W-2"
    if re.search(r"\bk[-_\s]?1\b|schedule k-1", haystack):
        return "K-1"
    if re.search(r"\b1098\b|mortgage interest statement", haystack):
        return "1098"
    return form


def first_available_value(lines: list[str], patterns: list[str]) -> str | None:
    for pattern in patterns:
        value = next_value_after_label(lines, pattern)
        if value:
            return value
    return None


def party_name_for_form(form: str | None, fields: dict[str, str | None], text: str) -> str | None:
    lines = text.splitlines() if text else []
    payer = fields.get(FIELD_LABELS["payer_name"])
    if form in {"1099-INT", "1099-DIV", "1099-CONSOLIDATED", "1099-NEC", "1099-MISC"}:
        return payer or first_available_value(lines, [r"broker(?:age)?(?: name)?", r"payer", r"financial institution"])
    if form == "W-2":
        return first_available_value(lines, [r"employer[’'`]?s name", r"employer name"]) or payer
    if form == "K-1":
        return first_available_value(lines, [r"partnership[’'`]?s name", r"issuer(?:[’'`]?s)? name", r"entity name"]) or payer
    if form == "1098":
        return first_available_value(lines, [r"lender[’'`]?s name", r"recipient[’'`]?s/lender[’'`]?s name", r"lender name"]) or payer
    return payer


def last_four_digits(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.findall(r"\d", value)
    return "".join(digits[-4:]) if len(digits) >= 4 else None


def sanitize_filename_stem(stem: str) -> str:
    for old, new in {"<": "", ">": "", ":": "", '"': "", "/": "-", "\\": "-", "|": "", "?": "", "*": ""}.items():
        stem = stem.replace(old, new)
    stem = re.sub(r"\s+", "_", stem).strip("._")
    return re.sub(r"_+", "_", stem) or "document"


def append_account_last4(stem: str, account_last4: str | None) -> str:
    return f"{stem}_{account_last4}" if account_last4 else stem


def build_suggested_file_name(info: "DocumentInfo") -> str | None:
    form = normalize_form(info.extracted_fields.get(FIELD_LABELS["form"]), info.text)
    party = party_name_for_form(form, info.extracted_fields, info.text)
    account_last4 = last_four_digits(info.extracted_fields.get(FIELD_LABELS["account_number"]))
    suffix = f".{info.file_extension}"
    if form == "1099-INT" and party:
        stem = append_account_last4(f"1099_int_{party}", account_last4)
    elif form == "1099-DIV" and party:
        stem = append_account_last4(f"1099_dividends_{party}", account_last4)
    elif form == "1099-CONSOLIDATED" and party:
        stem = append_account_last4(f"1099_consolidated_{party}", account_last4)
    elif form == "1099-NEC" and party:
        stem = append_account_last4(f"1099_NEC_{party}", account_last4)
    elif form == "1099-MISC" and party:
        stem = append_account_last4(f"1099_MISC_{party}", account_last4)
    elif form == "W-2" and party:
        stem = append_account_last4(f"W2_{party}", account_last4)
    elif form == "K-1" and party:
        stem = append_account_last4(f"K1_{party}", account_last4)
    elif form == "1098" and party:
        stem = append_account_last4(f"1098_{party}", account_last4)
    else:
        return None
    return f"{sanitize_filename_stem(stem)}{suffix}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not create a unique file name for {path}")


def copy_with_suggested_name(info: DocumentInfo, output_dir: Path) -> DocumentInfo:
    if not info.suggested_file_name:
        return info
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_path(output_dir / info.suggested_file_name)
    shutil.copy2(info.source_path, destination)
    return DocumentInfo(**{**asdict(info), "renamed_path": str(destination)})


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
    info = DocumentInfo(
        source_path=str(resolved),
        file_name=resolved.name,
        file_extension=extension.lstrip("."),
        parser=parser,
        text=text,
        line_count=len(lines),
        character_count=len(text),
        warnings=warnings,
        extracted_fields=extract_fields(text),
        suggested_file_name=None,
    )
    return DocumentInfo(**{**asdict(info), "suggested_file_name": build_suggested_file_name(info)})


def info_to_text(info: DocumentInfo) -> str:
    warnings = "\n".join(f"- {warning}" for warning in info.warnings) or "None"
    return (
        f"Source: {info.source_path}\n"
        f"File name: {info.file_name}\n"
        f"File extension: {info.file_extension}\n"
        f"Parser: {info.parser}\n"
        f"Lines: {info.line_count}\n"
        f"Characters: {info.character_count}\n"
        f"Warnings:\n{warnings}\n"
        f"Suggested file name: {info.suggested_file_name or ''}\n"
        f"Renamed path: {info.renamed_path or ''}\n\n"
        f"Columns:\n"
        f"PAYER’S name: {info.extracted_fields.get('PAYER’S name') or ''}\n"
        f"Form: {info.extracted_fields.get('Form') or ''}\n"
        f"Account number (see instructions): {info.extracted_fields.get('Account number (see instructions)') or ''}\n\n"
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
    parser.add_argument("--rename-dir", type=Path, help="Copy files into this directory using suggested tax document names")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_dependencies:
        print(json.dumps({"dependencies": collect_dependency_status(), "ocr_setup_help": OCR_SETUP_HELP}, indent=2))
        return 0
    if not args.inputs:
        raise SystemExit("No input files provided. Pass documents or use --check-dependencies.")
    infos = [extract_document_info(path) for path in args.inputs]
    if args.rename_dir:
        infos = [copy_with_suggested_name(info, args.rename_dir) for info in infos]
    write_output(infos, args.output, args.format)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
