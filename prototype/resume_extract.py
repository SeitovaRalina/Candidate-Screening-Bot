"""Resume ingestion: text message or an uploaded file (PDF/DOCX/TXT).

OQ-1 (.assistant/open-questions.md) is still open with the client on exactly
which formats to support — PDF and DOCX cover the overwhelming majority of
real resumes, so they're built now as the working assumption. A scanned-image
PDF (no text layer) will extract empty/garbage text; this is surfaced as an
explicit error rather than silently producing a hallucinated screening on no
real input.
"""
from __future__ import annotations

import io

import docx
import pdfplumber


class ResumeExtractionError(RuntimeError):
    pass


def extract_text_from_pdf(data: bytes) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    text = "\n".join(text_parts).strip()
    if not text:
        raise ResumeExtractionError(
            "Не удалось извлечь текст из PDF — вероятно, это скан без текстового слоя. "
            "OCR пока не поддерживается (см. OQ-1)."
        )
    return text


def extract_text_from_docx(data: bytes) -> str:
    document = docx.Document(io.BytesIO(data))
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    if not text.strip():
        raise ResumeExtractionError("DOCX не содержит текста в абзацах.")
    return text


def extract_resume_text(*, file_bytes: bytes | None, file_name: str | None, plain_text: str | None) -> str:
    """Single entry point the bot calls, regardless of how the resume arrived."""
    if file_bytes is not None:
        name = (file_name or "").lower()
        if name.endswith(".pdf"):
            return extract_text_from_pdf(file_bytes)
        if name.endswith(".docx"):
            return extract_text_from_docx(file_bytes)
        if name.endswith(".txt"):
            return file_bytes.decode("utf-8", errors="replace")
        raise ResumeExtractionError(
            f"Формат файла не поддерживается: {file_name!r}. Поддерживаются PDF, DOCX, TXT."
        )
    if plain_text and plain_text.strip():
        return plain_text.strip()
    raise ResumeExtractionError("Резюме не получено ни файлом, ни текстом.")
