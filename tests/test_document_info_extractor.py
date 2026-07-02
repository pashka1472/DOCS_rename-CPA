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
    assert document["suggested_file_name"] == "1099_NEC_ABC_Consulting_LLC_0421.pdf"


def test_suggests_requested_tax_document_names(tmp_path):
    examples = [
        ("interest.pdf", "Form 1099-INT\nPAYER'S name\nFidelity\nAccount number (see instructions)\nABC-5555123718", "1099_int_Fidelity_3718.pdf"),
        ("div.pdf", "Form 1099-DIV\nPAYER'S name\nFidelity\nAccount number (see instructions)\n3218", "1099_dividends_Fidelity_3218.pdf"),
        ("consolidated.pdf", "Consolidated Form 1099\nPAYER'S name\nFidelity\nAccount number (see instructions)\n3718", "1099_consolidated_Fidelity_3718.pdf"),
        ("nec.pdf", "Form 1099-NEC\nPAYER'S name\nApex Marketing Solutions, Inc.", "1099_NEC_Apex_Marketing_Solutions,_Inc.pdf"),
        ("misc.pdf", "Form 1099-MISC\nPAYER'S name\nApex Marketing Solutions, Inc.", "1099_MISC_Apex_Marketing_Solutions,_Inc.pdf"),
        ("w2.pdf", "Form W-2\nEmployer's name\nApex Marketing Solutions, Inc.", "W2_Apex_Marketing_Solutions,_Inc.pdf"),
        ("k1.pdf", "Schedule K-1\nPartnership's name\nApex Marketing Solutions, Inc.", "K1_Apex_Marketing_Solutions,_Inc.pdf"),
        ("1098.pdf", "Form 1098\nLender's name\nChase Bank", "1098_Chase_Bank.pdf"),
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
    renamed_path = rename_dir / "1099_NEC_Apex_Marketing_Solutions,_Inc_0421.pdf"
    assert exit_code == 0
    assert renamed_path.exists()
    assert payload["documents"][0]["suggested_file_name"] == renamed_path.name
    assert payload["documents"][0]["renamed_path"] == str(renamed_path)



def test_1099_misc_ocr_layout_uses_explicit_form_and_account_line():
    text = """PAYER’S name 1. Rents OMB No. 1545-0115
SAMPLE CAPITAL LLC
123 Market Street
Form 1099-MISC Miscellaneous
8 Substitute payments in lieu of dividends or interest
Account number (see instructions) 2nd TIN not. 16 State tax withheld | 17 State/Payer’s stateno. | 18 State income
987654821 $ 12.25 NJ - 22-1234567
Form 1099-MISC (Rev. 12-2026)
ACC-947251"""

    pdf_info = type("Info", (), {
        "extracted_fields": extract_fields(text),
        "text": text,
        "file_extension": "png",
    })()

    assert pdf_info.extracted_fields["PAYER’S name"] == "SAMPLE CAPITAL LLC"
    assert pdf_info.extracted_fields["Form"] == "1099-MISC"
    assert pdf_info.extracted_fields["Account number (see instructions)"] == "987654821"
    assert extract_document_info_from_fields_for_test(pdf_info) == "1099_MISC_SAMPLE_CAPITAL_LLC_4821.png"


def extract_document_info_from_fields_for_test(info):
    from document_info_extractor import build_suggested_file_name
    return build_suggested_file_name(info)


def test_payer_name_skips_inline_omb_label_for_1099_nec():
    text = """PAYER’S name OMB No. 1545-0116
ABC Consulting LLC
Form 1099-NEC
Account number (see instructions) 2nd TIN not. 5 State tax withheld
INV-2026-00421 Ce eee ee eee"""

    fields = extract_fields(text)
    info = type("Info", (), {"extracted_fields": fields, "text": text, "file_extension": "png"})()

    assert fields["PAYER’S name"] == "ABC Consulting LLC"
    assert fields["Form"] == "1099-NEC"
    assert fields["Account number (see instructions)"] == "INV-2026-00421"
    assert extract_document_info_from_fields_for_test(info) == "1099_NEC_ABC_Consulting_LLC_0421.png"


def test_payer_name_skips_inline_numbered_box_and_trims_business_suffix():
    text = """PAYER’S name 1 Rents OMB No. 1545-0115
SAMPLE CAPITAL LLC Mi
- iscellaneous
123 Market Street $ 1,250.00 Form 1099-MISC
8 Substitute payments in lieu of dividends or interest
Account number (see instructions) 2nd TIN not. 16 State tax withheld 17 State/Payer’s state no. 18 State income
987654321 UO $ 12.25 NJ - 22-1234567 $ 375.42
Form 1099-MISC (rev. 12-2026)"""

    fields = extract_fields(text)
    info = type("Info", (), {"extracted_fields": fields, "text": text, "file_extension": "png"})()

    assert fields["PAYER’S name"] == "SAMPLE CAPITAL LLC"
    assert fields["Form"] == "1099-MISC"
    assert fields["Account number (see instructions)"] == "987654321"
    assert extract_document_info_from_fields_for_test(info) == "1099_MISC_SAMPLE_CAPITAL_LLC_4321.png"


def test_1099_div_payer_name_uses_standard_anchor_and_skips_address_block():
    text = """Form 1099-DIV
PAYER'S name, street address, city or town, state or province, country, ZIP or foreign postal code, and telephone no.
SAMPLE CAPITAL LLC
123 Market Street, Suite 1000
New York, NY 10001
(212) 555-7890
PAYER'S TIN RECIPIENT'S TIN
12-3456789 987-65-4321
Account number (see instructions)
DIV-2026-12345678
"""

    fields = extract_fields(text)

    assert fields["PAYER’S name"] == "SAMPLE CAPITAL LLC"
    assert fields["Form"] == "1099-DIV"
    assert fields["Account number (see instructions)"] == "DIV-2026-12345678"


def test_1099_div_payer_name_accepts_ocr_anchor_variants_and_inline_neighbor_field():
    text = """Form 1099-DIV
PAYERS name, street address, city or town, state or province, country, ZIP or foreign postal code, and telephone no.
Charles Schwab PAYER'S TIN 12-3456789
Recipient's name Jane Investor
Account number (see instructions) 00001234
"""

    fields = extract_fields(text)

    assert fields["PAYER’S name"] == "Charles Schwab"


def test_1099_int_payer_name_skips_wrapped_standard_anchor_description():
    text = """Form 1099-INT
PAYER'S name, street address, city or town, state or province, country, ZIP
or foreign postal code, and telephone no.
SAMPLE BANK LLC
100 Banking Plaza
Chicago, IL 60601
PAYER'S TIN RECIPIENT'S TIN
12-3456789 987-65-4321
Account number (see instructions)
ACC-482915
"""

    fields = extract_fields(text)

    assert fields["PAYER’S name"] == "SAMPLE BANK LLC"
    assert fields["Form"] == "1099-INT"
    assert fields["Account number (see instructions)"] == "ACC-482915"
