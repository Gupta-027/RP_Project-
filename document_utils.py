"""
Text extraction helpers for syllabus / question-paper files.

Only two formats are supported (PDF and DOCX) because that is what our
university uses. Plain text can always be pasted directly in the app.
"""

import io

import fitz  # PyMuPDF
import docx


def extract_text_from_pdf(file_bytes):
    """Return all the text of a PDF, page by page."""
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as pdf:
        for page in pdf:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes):
    """Return the text of a DOCX file (paragraphs + tables)."""
    document = docx.Document(io.BytesIO(file_bytes))

    text_parts = [p.text for p in document.paragraphs]

    # Question papers are often written inside tables, so read those too.
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            text_parts.append(" | ".join(c for c in cells if c))

    return "\n".join(text_parts)


def extract_text(uploaded_file):
    """
    Extract text from a Streamlit uploaded file.
    Returns (text, error_message). Exactly one of them is empty.
    """
    if uploaded_file is None:
        return "", "No file provided."

    name = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()

    try:
        if name.endswith(".pdf"):
            return extract_text_from_pdf(file_bytes), ""
        if name.endswith(".docx"):
            return extract_text_from_docx(file_bytes), ""
        if name.endswith(".txt"):
            return file_bytes.decode("utf-8", errors="ignore"), ""
    except Exception as e:
        return "", f"Could not read the file: {e}"

    return "", "Unsupported file type. Please upload a PDF, DOCX or TXT file."


def clean_text(text):
    """Remove empty lines and stray spaces so chunking stays predictable."""
    lines = [line.strip() for line in text.splitlines()]
    cleaned = []
    for line in lines:
        # keep one blank line as a paragraph separator, drop the rest
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()
