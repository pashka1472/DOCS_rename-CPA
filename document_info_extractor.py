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
    text_lines: list[str]
    line_count: int
    character_count: int
    warnings: list[str]
    extracted_fields: dict[str, str | None]
    suggested_file_name: str | None
    renamed_path: str | None = None


@dataclass(frozen=True)
class OCRWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    page_num: int
    block_num: int
    par_num: int
    line_num: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


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


def tesseract_confident_text(value: object) -> bool:
    try:
        return float(str(value)) >= 0
    except ValueError:
        return False


def ocr_words_from_image(prepared_image: Any, pytesseract_module: Any) -> list[OCRWord]:
    data = pytesseract_module.image_to_data(
        prepared_image,
        config="--oem 3 --psm 11",
        output_type=pytesseract_module.Output.DICT,
    )
    words: list[OCRWord] = []
    word_count = len(data.get("text", []))
    for index in range(word_count):
        word = re.sub(r"[ \t]+", " ", str(data["text"][index])).strip()
        raw_confidence = data.get("conf", ["-1"] * word_count)[index]
        if not word or not tesseract_confident_text(raw_confidence):
            continue
        words.append(OCRWord(
            text=word,
            left=int(data.get("left", [index] * word_count)[index]),
            top=int(data.get("top", [0] * word_count)[index]),
            width=int(data.get("width", [0] * word_count)[index]),
            height=int(data.get("height", [0] * word_count)[index]),
            confidence=float(str(raw_confidence)),
            page_num=int(data.get("page_num", [1] * word_count)[index]),
            block_num=int(data.get("block_num", [0] * word_count)[index]),
            par_num=int(data.get("par_num", [0] * word_count)[index]),
            line_num=int(data.get("line_num", [0] * word_count)[index]),
        ))
    return words


def ocr_words_to_line_text(words: list[OCRWord]) -> str:
    line_words: dict[tuple[int, int, int, int], list[OCRWord]] = {}
    for word in words:
        key = (word.page_num, word.block_num, word.par_num, word.line_num)
        line_words.setdefault(key, []).append(word)

    lines = []
    for key, grouped_words in sorted(line_words.items(), key=lambda item: (item[0], min(word.top for word in item[1]))):
        del key
        lines.append(" ".join(word.text for word in sorted(grouped_words, key=lambda word: word.left)))
    return "\n".join(lines)


def extract_line_ordered_ocr_text(prepared_image: Any, pytesseract_module: Any) -> str:
    return ocr_words_to_line_text(ocr_words_from_image(prepared_image, pytesseract_module))


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
        text = extract_line_ordered_ocr_text(prepared, pytesseract)
        if not text:
            text = pytesseract.image_to_string(prepared, config="--oem 3 --psm 11")
    return normalize_text(text), "pytesseract", []


FIELD_LABELS = {
    "payer_name": "PAYER’S name",
    "payer_address": "PAYER address",
    "payer_phone": "PAYER phone",
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
        r"^omb\s+no\.?",
        r"^\d+[a-z]?\.?\s+[a-z]",
    ]
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in label_patterns)


def canonical_ocr_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower().replace("’", "'")).strip()


def fuzzy_ratio(left: str, right: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, canonical_ocr_text(left), canonical_ocr_text(right)).ratio()


def has_payer_name_anchor(value: str) -> bool:
    canonical = canonical_ocr_text(value)
    if re.search(r"\bpayer s name\b|\bpayers name\b|\bpayer name\b", canonical):
        return True
    variants = ["PAYER'S name", "PAYERS name", "PAYER name", "PAYER’S name"]
    words = canonical.split()
    windows = [" ".join(words[index:index + 3]) for index in range(max(len(words) - 1, 1))]
    return any(fuzzy_ratio(window, variant) >= 0.86 for window in windows for variant in variants)


def split_payer_anchor_line(line: str) -> tuple[str | None, str]:
    descriptor_pattern = (
        r"(?:payer[’'`]s|payers|payer)\s+name\s*,?\s*"
        r"(?:street\s+address|address|city\s+or\s+town|state\s+or\s+province|"
        r"country|zip|foreign\s+postal\s+code|telephone\s+no\.?).*"
    )
    patterns = [
        descriptor_pattern,
        r"payer[’'`]s\s+name",
        r"payers\s+name",
        r"payer\s+name",
    ]
    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(0), line[match.end():]
    return (line, "") if has_payer_name_anchor(line) else (None, line)


def is_payer_header_fragment(value: str) -> bool:
    canonical = canonical_ocr_text(value)
    header_terms = [
        "street address",
        "city or town",
        "state or province",
        "country",
        "zip",
        "foreign postal code",
        "telephone no",
    ]
    return any(term in canonical for term in header_terms)


def strip_neighbor_fields(value: str) -> str:
    neighbor_pattern = (
        r"\b(?:payer[’'`]?s?\s+tin|recipient[’'`]?s?\s+tin|recipient[’'`]?s?\s+name|"
        r"account\s+number|form\s+1099|omb\s+no\.?|\d+[a-z]?\.?\s+[a-z])\b"
    )
    return re.split(neighbor_pattern, value, maxsplit=1, flags=re.IGNORECASE)[0]


def line_is_neighbor_field(value: str) -> bool:
    value = clean_field_value(value)
    if not value:
        return False
    return bool(re.search(
        r"^(?:payer[’'`]?s?\s+tin|recipient[’'`]?s?\s+tin|recipient[’'`]?s?\s+name|"
        r"account\s+number|form\s+1099|omb\s+no\.?|\d+[a-z]?\.?\s+[a-z])\b",
        value,
        re.IGNORECASE,
    ))


def meaningful_payer_block_lines(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        anchor, remainder = split_payer_anchor_line(line)
        if not anchor:
            continue
        candidates = [remainder, *lines[index + 1:]]
        block_lines: list[str] = []
        for candidate in candidates:
            candidate = clean_field_value(strip_neighbor_fields(candidate))
            if not candidate:
                continue
            if has_payer_name_anchor(candidate):
                continue
            if is_payer_header_fragment(candidate):
                continue
            if line_is_neighbor_field(candidate):
                break
            if looks_like_label(candidate):
                continue
            block_lines.append(candidate)
        return block_lines
    return []


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
    if not value:
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


def clean_party_name(value: str | None) -> str | None:
    if not value:
        return None
    value = clean_field_value(value)
    business_suffix_match = re.search(
        r"^(.+\b(?:LLC|L\.?L\.?C\.?|Inc\.?|Corp\.?|Corporation|Company|Co\.?|LLP|L\.?L\.?P\.?|LP|L\.?P\.?|Bank))\b",
        value,
        re.IGNORECASE,
    )
    if business_suffix_match:
        return clean_field_value(business_suffix_match.group(1))
    return value


def extract_payer_name(lines: list[str]) -> str | None:
    block_lines = meaningful_payer_block_lines(lines)
    if block_lines:
        return clean_party_name(block_lines[0])
    return clean_party_name(next_value_after_label(lines, r"payer[’'`]?s name"))


def extract_fields(text: str) -> dict[str, str | None]:
    lines = text.splitlines() if text else []
    return {
        FIELD_LABELS["payer_name"]: extract_payer_name(lines),
        FIELD_LABELS["payer_address"]: None,
        FIELD_LABELS["payer_phone"]: None,
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
    payer = clean_party_name(fields.get(FIELD_LABELS["payer_name"]))
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


def word_bbox(words: list[OCRWord]) -> tuple[int, int, int, int]:
    return (
        min(word.left for word in words),
        min(word.top for word in words),
        max(word.right for word in words),
        max(word.bottom for word in words),
    )


def grouped_ocr_lines(words: list[OCRWord]) -> list[tuple[str, tuple[int, int, int, int]]]:
    grouped: dict[tuple[int, int, int, int], list[OCRWord]] = {}
    for word in words:
        key = (word.page_num, word.block_num, word.par_num, word.line_num)
        grouped.setdefault(key, []).append(word)
    lines = []
    for line_words in grouped.values():
        ordered = sorted(line_words, key=lambda word: word.left)
        lines.append((" ".join(word.text for word in ordered), word_bbox(ordered)))
    return sorted(lines, key=lambda line: (line[1][1], line[1][0]))


def find_text_anchor_bbox(words: list[OCRWord], predicate: Any) -> tuple[int, int, int, int] | None:
    best: tuple[str, tuple[int, int, int, int]] | None = None
    for line in grouped_ocr_lines(words):
        text, bbox = line
        if predicate(text):
            if best is None or (bbox[1], bbox[0]) < (best[1][1], best[1][0]):
                best = line
    return best[1] if best else None


def find_payer_anchor_bbox(words: list[OCRWord]) -> tuple[int, int, int, int] | None:
    return find_text_anchor_bbox(words, has_payer_name_anchor)


def has_account_number_anchor(value: str) -> bool:
    return bool(re.search(r"account\s+number(?:\s*\(see instructions\))?", value, re.IGNORECASE))


def has_form_anchor(value: str) -> bool:
    return bool(re.search(r"\bform\s+(?:1099[-_\s]?(?:NEC|MISC|INT|DIV)|1098|W[-_\s]?2|K[-_\s]?1)\b", value, re.IGNORECASE))


def dark_pixel(value: int) -> bool:
    return value < 80


def find_horizontal_boundary(image: Any, top: int, left: int, right: int) -> int:
    grayscale = image.convert("L")
    width, height = grayscale.size
    left = max(0, min(left, width - 1))
    right = max(left + 1, min(right, width))
    pixels = grayscale.load()
    for y in range(min(height - 1, top + 5), height):
        dark_count = sum(1 for x in range(left, right) if dark_pixel(pixels[x, y]))
        if dark_count / max(right - left, 1) >= 0.45:
            return y
    return height


def find_vertical_boundaries(image: Any, anchor_bbox: tuple[int, int, int, int], bottom: int) -> tuple[int, int]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    anchor_left, anchor_top, anchor_right, _ = anchor_bbox
    bottom = max(anchor_top + 1, min(bottom, height))
    pixels = grayscale.load()

    def is_vertical_line(x: int) -> bool:
        dark_count = sum(1 for y in range(anchor_top, bottom) if dark_pixel(pixels[x, y]))
        return dark_count / max(bottom - anchor_top, 1) >= 0.35

    left = 0
    for x in range(max(0, anchor_left), -1, -1):
        if is_vertical_line(x):
            left = x
            break

    right = width
    for x in range(min(width - 1, anchor_right + 1), width):
        if is_vertical_line(x):
            right = x
            break
    return left, right


def crop_anchored_block_image(prepared_image: Any, words: list[OCRWord], anchor_bbox: tuple[int, int, int, int]) -> Any:
    _, top, _, bottom = anchor_bbox
    estimated_right = min(prepared_image.size[0], max(word.right for word in words if word.top >= top) + 10)
    block_bottom = find_horizontal_boundary(prepared_image, bottom, 0, estimated_right)
    block_left, block_right = find_vertical_boundaries(prepared_image, anchor_bbox, block_bottom)
    padding = 2
    return prepared_image.crop((
        max(0, block_left + padding),
        max(0, top),
        min(prepared_image.size[0], block_right - padding),
        min(prepared_image.size[1], block_bottom),
    ))


def crop_payer_block_image(prepared_image: Any, words: list[OCRWord]) -> Any | None:
    anchor_bbox = find_payer_anchor_bbox(words)
    if not anchor_bbox:
        return None
    return crop_anchored_block_image(prepared_image, words, anchor_bbox)


def payer_block_content_lines(block_text: str) -> list[str]:
    result = []
    for line in block_text.splitlines():
        value = clean_field_value(strip_neighbor_fields(line))
        if not value:
            continue
        if has_payer_name_anchor(value) or is_payer_header_fragment(value):
            continue
        if line_is_neighbor_field(value):
            break
        result.append(value)
    return result


def extract_anchored_block_text(
    prepared_image: Any,
    words: list[OCRWord],
    pytesseract_module: Any,
    predicate: Any,
    fallback_psm: int = 6,
) -> str | None:
    anchor_bbox = find_text_anchor_bbox(words, predicate)
    if anchor_bbox is None:
        return None
    crop = crop_anchored_block_image(prepared_image, words, anchor_bbox)
    text = extract_line_ordered_ocr_text(crop, pytesseract_module)
    if not text:
        text = pytesseract_module.image_to_string(crop, config=f"--oem 3 --psm {fallback_psm}")
    return normalize_text(text)


def extract_anchored_block_text_from_image(path: Path, predicate: Any, fallback_psm: int = 6) -> str | None:
    if not all(module_available(name) for name in ("PIL", "pytesseract")):
        return None
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore
    from PIL import ImageOps  # type: ignore

    with Image.open(path) as image:
        prepared = ImageOps.autocontrast(image.convert("L"))
        prepared = prepared.resize((prepared.width * 2, prepared.height * 2))
        words = ocr_words_from_image(prepared, pytesseract)
        return extract_anchored_block_text(prepared, words, pytesseract, predicate, fallback_psm)


def extract_payer_block_text_from_image(path: Path) -> str | None:
    return extract_anchored_block_text_from_image(path, has_payer_name_anchor)


def payer_block_fields(block_text: str | None) -> dict[str, str | None]:
    lines = payer_block_content_lines(block_text or "")
    phone_pattern = r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}"
    phone = next((line for line in lines if re.search(phone_pattern, line)), None)
    address_lines = [line for line in lines[1:] if line != phone]
    return {
        FIELD_LABELS["payer_name"]: clean_party_name(lines[0]) if lines else None,
        FIELD_LABELS["payer_address"]: "\n".join(address_lines) if address_lines else None,
        FIELD_LABELS["payer_phone"]: phone,
    }


def form_block_fields(block_text: str | None) -> dict[str, str | None]:
    return {FIELD_LABELS["form"]: extract_form_value(block_text or "")}


def account_block_fields(block_text: str | None) -> dict[str, str | None]:
    text = block_text or ""
    return {FIELD_LABELS["account_number"]: extract_account_number(text, text.splitlines())}


def extract_image_block_fields(path: Path) -> dict[str, str | None]:
    if not all(module_available(name) for name in ("PIL", "pytesseract")):
        return {}
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore
    from PIL import ImageOps  # type: ignore

    with Image.open(path) as image:
        prepared = ImageOps.autocontrast(image.convert("L"))
        prepared = prepared.resize((prepared.width * 2, prepared.height * 2))
        words = ocr_words_from_image(prepared, pytesseract)
        fields = payer_block_fields(extract_anchored_block_text(
            prepared, words, pytesseract, has_payer_name_anchor,
        ))
        fields = merge_preferred_fields(
            fields,
            form_block_fields(extract_anchored_block_text(prepared, words, pytesseract, has_form_anchor)),
        )
        fields = merge_preferred_fields(
            fields,
            account_block_fields(extract_anchored_block_text(
                prepared, words, pytesseract, has_account_number_anchor,
            )),
        )
    return fields


def merge_preferred_fields(
    base_fields: dict[str, str | None],
    preferred_fields: dict[str, str | None],
) -> dict[str, str | None]:
    merged = dict(base_fields)
    for key, value in preferred_fields.items():
        if value:
            merged[key] = value
    return merged


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
    fields = extract_fields(text)
    if extension in IMAGE_EXTENSIONS:
        fields = merge_preferred_fields(fields, extract_image_block_fields(resolved))
    info = DocumentInfo(
        source_path=str(resolved),
        file_name=resolved.name,
        file_extension=extension.lstrip("."),
        parser=parser,
        text=text,
        text_lines=lines,
        line_count=len(lines),
        character_count=len(text),
        warnings=warnings,
        extracted_fields=fields,
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
        f"PAYER address: {info.extracted_fields.get('PAYER address') or ''}\n"
        f"PAYER phone: {info.extracted_fields.get('PAYER phone') or ''}\n"
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
