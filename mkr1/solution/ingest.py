"""Читання документів: pdf, docx, pptx, txt, md. Повертає текст по сторінках/слайдах."""
import io
import re
from pathlib import Path

ALLOWED = {".txt", ".md", ".pdf", ".docx", ".pptx"}
MIN_TEXT_CHARS = 50

Pages = list[tuple[int | None, str]]


def extract_pages(filename: str, data: bytes) -> Pages:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError(f"Непідтримуваний формат: {filename}. Підтримуються: pdf, docx, pptx, txt, md. Файл .doc збережіть у Word як .docx")

    if ext == ".pdf":
        pages = _pdf(data)
    elif ext == ".docx":
        pages = _docx(data)
    elif ext == ".pptx":
        pages = _pptx(data)
    else:
        pages = [(None, _decode(data))]

    pages = [(number, clean_text(text)) for number, text in pages]
    pages = [(number, text) for number, text in pages if text]
    if sum(len(text) for _, text in pages) < MIN_TEXT_CHARS:
        raise ValueError(f"У файлі {filename} немає тексту (можливо, це скан або порожній документ)")
    return pages


def _pdf(data: bytes) -> Pages:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return [(index, page.extract_text() or "") for index, page in enumerate(reader.pages, start=1)]


def _docx(data: bytes) -> Pages:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    parts = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            parts.append(Paragraph(child, doc).text)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, doc).rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return [(None, "\n\n".join(parts))]


def _pptx(data: bytes) -> Pages:
    from pptx import Presentation

    pages = []
    for number, slide in enumerate(Presentation(io.BytesIO(data)).slides, start=1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        if slide.has_notes_slide:
            parts.append(slide.notes_slide.notes_text_frame.text)
        pages.append((number, "\n\n".join(parts)))
    return pages


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"[ ]*\n[ ]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
