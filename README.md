# CPA document renamer

Small CLI utility for CPA intake documents. It converts a photo/scan/PDF into a PDF file and renames it using tax-form content.

## Supported naming rules

- `1099_int_<broker>_<last4>` for Form 1099-INT interest income.
- `1099_dividends_<broker>_<last4>` for Form 1099-DIV dividend income.
- `1099_consolidated_<broker>_<last4>` for consolidated brokerage 1099 packages.
- `1099_NEC_<payer name>` for Form 1099-NEC nonemployee compensation.
- `1099_misc_<payer name>` for Form 1099-MISC miscellaneous income.
- `W2_<employer name>` for W-2 wage statements.
- `K1_<issuer name>` for Schedule K-1 documents.
- `1098_<lender>` for Form 1098 mortgage interest statements.

## Usage

```bash
python cpa_doc_renamer.py input.pdf --output-dir renamed
python cpa_doc_renamer.py scan.jpg --output-dir renamed
```

For development or when OCR text is already available, pass text directly:

```bash
python cpa_doc_renamer.py input.pdf --text "Form 1099-INT Fidelity account ending in 3718 Interest Income" --dry-run
```

## Optional dependencies

- `pypdf` extracts text from PDFs.
- `pillow` converts image files to PDF.
- `pytesseract` performs OCR for images when Tesseract is installed on the machine.

## Sample filled forms

Generate fake filled PDF samples for every supported form type:

```bash
python scripts/generate_sample_forms.py
```

The generated source PDFs are written to `samples/source_forms/`. They contain
training data only and must not be filed.
