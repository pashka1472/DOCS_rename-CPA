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

## Usage

Create JSON:

```bash
python document_info_extractor.py document.pdf scan.jpg --output document_info.json
```

Create plain text:

```bash
python document_info_extractor.py document.pdf --output document_info.txt --format txt
```

## Optional dependency behavior

- `pypdf` improves PDF text extraction.
- `Pillow` and `pytesseract` enable OCR for image files.

If `pypdf` is unavailable, the app still attempts a basic fallback extraction for simple text PDFs.
If image OCR dependencies are unavailable, the output file includes setup warnings and the extracted text is empty.
