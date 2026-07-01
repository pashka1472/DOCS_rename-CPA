# Document information extractor

Small CLI app that extracts text from documents and creates an information file.

## Supported input formats

- PDF: `.pdf`
- Images: `.png`, `.img`, `.jpeg`, `.jpg`

## Output

The app writes one output file with information for each document:

- source path
- file name
- file extension
- parser used
- extracted text
- line count
- character count
- warnings, for example when OCR dependencies are missing
- extracted columns: `PAYER’S name`, `Form`, `Account number (see instructions)`
- `suggested_file_name` for CPA naming
- `renamed_path` when `--rename-dir` is used

## Install dependencies

Install Python packages from the repository root:

```bash
python -m pip install -r requirements.txt
```

For image OCR, also install the Tesseract OCR application and ensure the
`tesseract` command is available on PATH.

On Windows, one common setup is:

1. Install Tesseract OCR for Windows.
2. Add the Tesseract install folder, for example `C:\Program Files\Tesseract-OCR`, to `PATH`.
3. Restart VS Code so its terminal receives the updated `PATH`.

Check dependency status:

```bash
python document_info_extractor.py --check-dependencies
```


### If `--check-dependencies` says `inputs` are required

That means VS Code is running an older copy of `document_info_extractor.py`.
Update the repository or confirm the file contains `inputs` with `nargs="*"`, then rerun:

```bash
python document_info_extractor.py --check-dependencies
```

## Extracted columns and rename logic

The JSON output now includes these extracted columns when they are present in OCR/PDF text:

- `PAYER’S name`
- `Form`
- `Account number (see instructions)`

The app uses those fields to suggest CPA file names. When an account number is present, the last four account digits are appended to the end of the file name:

- `1099_int_<broker name>_<last 4 account digits>`
- `1099_dividends_<broker name>_<last 4 account digits>`
- `1099_consolidated_<broker name>_<last 4 account digits>`
- `1099_NEC_<PAYER’S name>`
- `1099_misc_<PAYER’S name>`
- `W2_<employer name>`
- `K1_<issuer or partnership name>`
- `1098_<lender name>`

For your sample `nec.png`, the output should include `suggested_file_name`: `1099_NEC_ABC Consulting LLC_0421.png`.

Use `--rename-dir` to copy files into a folder with the suggested names. Original files are not deleted or overwritten.

## Usage

Create JSON:

```bash
python document_info_extractor.py document.pdf scan.jpg --output document_info.json
```

Create plain text:

```bash
python document_info_extractor.py document.pdf --output document_info.txt --format txt
```

Create JSON and copy renamed files:

```bash
python document_info_extractor.py test_files/nec.png --output document_info.json --rename-dir renamed_documents
```

## Optional dependency behavior

- `pypdf` improves PDF text extraction.
- `Pillow` and `pytesseract` enable OCR for image files.

If `pypdf` is unavailable, the app still attempts a basic fallback extraction for simple text PDFs.
If image OCR dependencies are unavailable, the output file includes setup warnings and the extracted text is empty.
