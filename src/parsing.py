"""Extract per-page text from a source document (PDF or plain text)."""
from pathlib import Path

from pypdf import PdfReader


def extract_pages(path: Path) -> list[str]:
    """Return a list of page texts (1 entry per PDF page, or 1 entry total for .txt)."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return [page.extract_text() or "" for page in reader.pages]
    return [path.read_text(encoding="utf-8")]
