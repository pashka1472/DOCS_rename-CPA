from cpa_doc_renamer import classify_document, sanitize_filename_part


def test_1099_int_broker_and_last4():
    result = classify_document("Form 1099-INT Interest Income Fidelity account ending in 3718")
    assert result.filename_stem == "1099_int_fidelity_3718"


def test_1099_dividends():
    result = classify_document("1099-DIV Dividends Charles Schwab account number ****3218")
    assert result.filename_stem == "1099_dividends_charles_schwab_3218"


def test_consolidated_1099():
    result = classify_document("Consolidated Form 1099 Robinhood Account No. XXXXXX3718")
    assert result.filename_stem == "1099_consolidated_robinhood_3718"


def test_1099_nec_uses_payer_name():
    text = "Form 1099-NEC Nonemployee Compensation\nPAYER'S name\nApex Marketing Solutions, Inc."
    result = classify_document(text)
    assert result.filename_stem == "1099_NEC_Apex Marketing Solutions, Inc"


def test_1099_misc_uses_payer_name():
    text = "Form 1099-MISC Miscellaneous Information\nPayer's name: Apex Marketing Solutions, Inc."
    result = classify_document(text)
    assert result.filename_stem == "1099_misc_Apex Marketing Solutions, Inc"


def test_w2_uses_employer_name():
    text = "Form W-2 Wage and Tax Statement\nEmployer's name: Apex Marketing Solutions, Inc."
    result = classify_document(text)
    assert result.filename_stem == "W2_Apex Marketing Solutions, Inc"


def test_k1_uses_issuer_name():
    text = "Schedule K-1\nIssuer's name: Apex Marketing Solutions, Inc."
    result = classify_document(text)
    assert result.filename_stem == "K1_Apex Marketing Solutions, Inc"


def test_1098_uses_lender_name():
    text = "Form 1098 Mortgage Interest Statement\nLender's name: Chase Bank"
    result = classify_document(text)
    assert result.filename_stem == "1098_chase_bank"


def test_filename_sanitizer_removes_forbidden_characters():
    assert sanitize_filename_part('Apex: Marketing / Solutions? Inc.') == "Apex Marketing Solutions Inc"
