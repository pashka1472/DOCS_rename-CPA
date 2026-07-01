import json

import pytest

from document_info_extractor import extract_document_info, extract_fields, main, write_output


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



def test_extracts_requested_columns_from_supplied_1099_nec_text():
    text = """PAYER’S name
ABC Consulting LLC
CORRECTED (if checked)
OMB No. 1545-0116
Form 1099-NEC
789 Business Park Dr Nonemployee
Account number (see instructions)
INV-2026-00421
Form 1099-NEC (Rev. 12-2026)
"""

    fields = extract_fields(text)

    assert fields["PAYER’S name"] == "ABC Consulting LLC"
    assert fields["Form"] == "1099-NEC"
    assert fields["Account number (see instructions)"] == "INV-2026-00421"


def test_json_output_includes_suggested_name_for_supplied_1099_nec(tmp_path):
    pdf_path = tmp_path / "nec.pdf"
    output_path = tmp_path / "info.json"
    write_simple_pdf(
        pdf_path,
        "PAYER'S name\nABC Consulting LLC\nForm 1099-NEC\nAccount number (see instructions)\nINV-2026-00421",
    )

    info = extract_document_info(pdf_path)
    write_output([info], output_path, "json")

    document = json.loads(output_path.read_text(encoding="utf-8"))["documents"][0]
    assert document["extracted_fields"] == {
        "PAYER’S name": "ABC Consulting LLC",
        "Form": "1099-NEC",
        "Account number (see instructions)": "INV-2026-00421",
    }
    assert document["suggested_file_name"] == "1099_NEC_ABC Consulting LLC_0421.pdf"


def test_suggests_requested_tax_document_names(tmp_path):
    examples = [
        ("interest.pdf", "Form 1099-INT\nPAYER'S name\nFidelity\nAccount number (see instructions)\nABC-5555123718", "1099_int_Fidelity_3718.pdf"),
        ("div.pdf", "Form 1099-DIV\nPAYER'S name\nFidelity\nAccount number (see instructions)\n3218", "1099_dividends_Fidelity_3218.pdf"),
        ("consolidated.pdf", "Consolidated Form 1099\nPAYER'S name\nFidelity\nAccount number (see instructions)\n3718", "1099_consolidated_Fidelity_3718.pdf"),
        ("nec.pdf", "Form 1099-NEC\nPAYER'S name\nApex Marketing Solutions, Inc.", "1099_NEC_Apex Marketing Solutions, Inc.pdf"),
        ("misc.pdf", "Form 1099-MISC\nPAYER'S name\nApex Marketing Solutions, Inc.", "1099_misc_Apex Marketing Solutions, Inc.pdf"),
        ("w2.pdf", "Form W-2\nEmployer's name\nApex Marketing Solutions, Inc.", "W2_Apex Marketing Solutions, Inc.pdf"),
        ("k1.pdf", "Schedule K-1\nPartnership's name\nApex Marketing Solutions, Inc.", "K1_Apex Marketing Solutions, Inc.pdf"),
        ("1098.pdf", "Form 1098\nLender's name\nChase Bank", "1098_Chase Bank.pdf"),
    ]

    for filename, text, expected in examples:
        pdf_path = tmp_path / filename
        write_simple_pdf(pdf_path, text)
        assert extract_document_info(pdf_path).suggested_file_name == expected


def test_rename_dir_copies_file_with_suggested_name(tmp_path):
    pdf_path = tmp_path / "nec.pdf"
    output_path = tmp_path / "info.json"
    rename_dir = tmp_path / "renamed"
    write_simple_pdf(pdf_path, "Form 1099-NEC\nPAYER'S name\nApex Marketing Solutions, Inc.\nAccount number (see instructions)\nINV-2026-00421")

    exit_code = main([str(pdf_path), "--output", str(output_path), "--rename-dir", str(rename_dir)])

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    renamed_path = rename_dir / "1099_NEC_Apex Marketing Solutions, Inc_0421.pdf"
    assert exit_code == 0
    assert renamed_path.exists()
    assert payload["documents"][0]["suggested_file_name"] == renamed_path.name
    assert payload["documents"][0]["renamed_path"] == str(renamed_path)
