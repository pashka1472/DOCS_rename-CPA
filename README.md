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

## Usage

Create JSON:

```bash
python document_info_extractor.py document.pdf scan.jpg --output document_info.json
```

Create plain text:

```bash
python document_info_extractor.py document.pdf --output document_info.txt --format txt
```

## Optional dependencies

- `pypdf` improves PDF text extraction.
- `Pillow` and `pytesseract` enable OCR for image files.

If `pypdf` is unavailable, the app still attempts a basic fallback extraction for simple text PDFs.
