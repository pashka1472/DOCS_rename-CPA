#!/usr/bin/env python3
"""Small Windows-friendly GUI for copying tax documents as renamed PDFs."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from document_info_extractor import (
    FIELD_LABELS,
    OCR_SETUP_HELP,
    copy_as_pdf_with_suggested_name,
    extract_document_info,
    write_output,
)


class TaxDocumentRenamerApp(tk.Tk):
    """Tkinter app that extracts document info and copies the input as a named PDF."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Tax Document PDF Renamer")
        self.geometry("760x560")
        self.minsize(680, 500)

        self.selected_file = tk.StringVar()
        self.output_folder = tk.StringVar(value=str(Path.cwd() / "renamed_documents"))
        self.status = tk.StringVar(value="Select a PDF or image tax document to begin.")
        self.suggested_name = tk.StringVar(value="")
        self.current_info = None

        self._build_ui()

    def _build_ui(self) -> None:
        padding = {"padx": 12, "pady": 6}
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(main, text="Input file").grid(row=0, column=0, sticky="w", **padding)
        ttk.Entry(main, textvariable=self.selected_file).grid(row=0, column=1, sticky="ew", **padding)
        ttk.Button(main, text="Select file...", command=self.select_file).grid(row=0, column=2, **padding)

        ttk.Label(main, text="Output folder").grid(row=1, column=0, sticky="w", **padding)
        ttk.Entry(main, textvariable=self.output_folder).grid(row=1, column=1, sticky="ew", **padding)
        ttk.Button(main, text="Choose folder...", command=self.select_output_folder).grid(row=1, column=2, **padding)

        ttk.Label(main, text="Output PDF name").grid(row=2, column=0, sticky="w", **padding)
        ttk.Entry(main, textvariable=self.suggested_name, state="readonly").grid(row=2, column=1, columnspan=2, sticky="ew", **padding)

        buttons = ttk.Frame(main)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", **padding)
        ttk.Button(buttons, text="Extract preview", command=self.extract_preview).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Copy as renamed PDF", command=self.copy_as_pdf).pack(side=tk.LEFT)

        ttk.Label(main, textvariable=self.status, foreground="#264653").grid(row=4, column=0, columnspan=3, sticky="w", **padding)

        self.details = tk.Text(main, height=18, wrap="word")
        self.details.grid(row=5, column=0, columnspan=3, sticky="nsew", **padding)
        self.details.insert("1.0", "Tesseract setup: install Tesseract separately and make sure tesseract.exe is on PATH.\n" + OCR_SETUP_HELP)
        self.details.configure(state="disabled")

        main.columnconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)

    def select_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select tax document",
            filetypes=[
                ("Supported documents", "*.pdf *.png *.jpg *.jpeg *.img"),
                ("PDF files", "*.pdf"),
                ("Image files", "*.png *.jpg *.jpeg *.img"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.selected_file.set(filename)
            self.current_info = None
            self.suggested_name.set("")
            self.status.set("File selected. Click Extract preview or Copy as renamed PDF.")

    def select_output_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_folder.set(folder)

    def extract_preview(self) -> None:
        self._run_in_background(copy_after_extract=False)

    def copy_as_pdf(self) -> None:
        self._run_in_background(copy_after_extract=True)

    def _run_in_background(self, copy_after_extract: bool) -> None:
        if not self.selected_file.get():
            messagebox.showwarning("No file selected", "Please select a document first.")
            return
        self.status.set("Working... OCR can take a little time for scanned images.")
        threading.Thread(target=self._process_document, args=(copy_after_extract,), daemon=True).start()

    def _process_document(self, copy_after_extract: bool) -> None:
        try:
            info = self.current_info or extract_document_info(Path(self.selected_file.get()))
            self.current_info = info
            if copy_after_extract:
                info = copy_as_pdf_with_suggested_name(info, Path(self.output_folder.get()))
                self.current_info = info
                write_output([info], Path(self.output_folder.get()) / "document_info.json", "json")
            self.after(0, self._show_info, info, copy_after_extract)
        except Exception as exc:  # noqa: BLE001 - GUI must display unexpected errors to the user.
            self.after(0, self._show_error, exc)

    def _show_info(self, info, copied: bool) -> None:
        self.suggested_name.set(info.suggested_file_name or "No suggested name found")
        fields = info.extracted_fields
        lines = [
            f"Source: {info.source_path}",
            f"Output PDF: {info.renamed_path or ''}",
            f"Suggested name: {info.suggested_file_name or ''}",
            "",
            "Detected fields:",
            f"- Form: {fields.get(FIELD_LABELS['form']) or ''}",
            f"- Payer: {fields.get(FIELD_LABELS['payer_name']) or ''}",
            f"- Lender: {fields.get(FIELD_LABELS['lender_name']) or ''}",
            f"- Partnership: {fields.get(FIELD_LABELS['partnership_name']) or ''}",
            f"- Account: {fields.get(FIELD_LABELS['account_number']) or ''}",
            f"- Partnership EIN: {fields.get(FIELD_LABELS['partnership_ein']) or ''}",
            "",
            "Warnings:",
            *(f"- {warning}" for warning in info.warnings),
        ]
        if not info.warnings:
            lines.append("- None")
        self.details.configure(state="normal")
        self.details.delete("1.0", tk.END)
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")
        self.status.set("Copied renamed PDF." if copied else "Preview ready.")

    def _show_error(self, exc: Exception) -> None:
        self.status.set("Error.")
        messagebox.showerror("Processing failed", str(exc))


def main() -> None:
    TaxDocumentRenamerApp().mainloop()


if __name__ == "__main__":
    main()
