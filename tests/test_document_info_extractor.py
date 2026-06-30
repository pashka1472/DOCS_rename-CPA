import json

import pytest

from document_info_extractor import extract_document_info, main, write_output


def write_simple_pdf(path, text):
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
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
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    path.write_bytes(bytes(pdf))


def test_extracts_text_from_simple_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    write_simple_pdf(pdf_path, "Hello CPA document")

    info = extract_document_info(pdf_path)

    assert info.file_name == "sample.pdf"
    assert info.file_extension == "pdf"
    assert info.text == "Hello CPA document"
    assert info.line_count == 1
    assert info.character_count == len("Hello CPA document")


def test_writes_json_output(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    output_path = tmp_path / "info.json"
    write_simple_pdf(pdf_path, "Income statement")
    info = extract_document_info(pdf_path)

    write_output([info], output_path, "json")

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["documents"][0]["text"] == "Income statement"
    assert payload["documents"][0]["file_name"] == "sample.pdf"


def test_writes_text_output(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    output_path = tmp_path / "info.txt"
    write_simple_pdf(pdf_path, "Mortgage document")
    info = extract_document_info(pdf_path)

    write_output([info], output_path, "txt")

    text = output_path.read_text(encoding="utf-8")
    assert "File name: sample.pdf" in text
    assert "Mortgage document" in text


def test_rejects_unsupported_extension(tmp_path):
    bad_path = tmp_path / "sample.docx"
    bad_path.write_text("not supported")

    with pytest.raises(ValueError, match="Unsupported file extension"):
        extract_document_info(bad_path)


def test_image_without_ocr_dependencies_returns_setup_help(tmp_path, monkeypatch):
    image_path = tmp_path / "nec.png"
    image_path.write_bytes(b"not a real image; dependency check happens first")
    monkeypatch.setattr("document_info_extractor.module_available", lambda name: False)

    info = extract_document_info(image_path)

    assert info.parser == "ocr_unavailable"
    assert info.text == ""
    assert "missing: PIL, pytesseract" in info.warnings[0]
    assert "python -m pip install -r requirements.txt" in info.warnings[1]


def test_check_dependencies_does_not_require_inputs(capsys):
    exit_code = main(["--check-dependencies"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dependencies" in captured.out
    assert "ocr_setup_help" in captured.out
