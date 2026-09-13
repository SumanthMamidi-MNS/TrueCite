"""Phase 1 gate: parse + structurally chunk all corpus documents and show the output.

Run: .venv/Scripts/python.exe src/run_phase1.py
"""
import json
from dataclasses import asdict
from pathlib import Path

from chunking import chunk_document
from parsing import extract_pages

CORPUS_RAW = Path(__file__).resolve().parent.parent / "corpus" / "raw"
CORPUS_PROCESSED = Path(__file__).resolve().parent.parent / "corpus" / "processed"

# (doc_id, filename, body_start_anchor) — anchor marks where TOC/front matter ends
# and the real structured body begins, so the TOC's own section numbers aren't
# mistaken for the document's structure.
ALL_DOCS = [
    ("patents_act_1970", "patents_act_1970.pdf", "BE it enacted by Parliament"),
    ("ipo_tk_biological_material_guidelines_2012", "ipo_tk_biological_material_guidelines_2012.pdf", None),
    ("pib_faq_patents_traditional_ayurvedic_medicine_2013", "pib_faq_patents_traditional_ayurvedic_medicine_2013.txt", None),
    (
        "ipo_ayush_examination_guidelines_2025",
        "ipo_ayush_examination_guidelines_2025.pdf",
        "Ayush is traditional and non -conventional",  # PDF extraction inserts a stray space here
    ),
    (
        "wipo_documenting_tk_toolkit",
        "wipo_documenting_tk_toolkit.pdf",
        "Documenting traditional knowledge (TK) is now widely",  # cut before a mid-sentence line wrap
    ),
    ("biological_diversity_act_2002", "biological_diversity_act_2002.pdf", "BE it enacted by parliament"),
    ("wipo_gratk_treaty_2024", "wipo_gratk_treaty_2024.pdf", None),
]


def main():
    CORPUS_PROCESSED.mkdir(parents=True, exist_ok=True)
    for doc_id, filename, anchor in ALL_DOCS:
        path = CORPUS_RAW / filename
        pages = extract_pages(path)
        chunks = chunk_document(doc_id, pages, body_start_anchor=anchor)

        out_path = CORPUS_PROCESSED / f"{doc_id}.json"
        out_path.write_text(
            json.dumps([asdict(c) for c in chunks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\n{'=' * 70}")
        print(f"{doc_id}  ({len(pages)} pages -> {len(chunks)} chunks)")
        print(f"written to {out_path.relative_to(out_path.parent.parent.parent)}")
        print("-" * 70)
        for c in chunks[:6]:
            preview = c.text[:160].replace("\n", " ")
            # Windows console encoding (cp1252) can't print every PDF glyph
            # (e.g. private-use-area bullet chars); replace rather than crash.
            safe_preview = preview.encode("ascii", errors="replace").decode("ascii")
            print(f"[{c.chunk_id}] p{c.page_start}-{c.page_end} ({c.char_count} chars)")
            print(f"  heading: {c.heading!r}")
            print(f"  text:    {safe_preview}...")
        if len(chunks) > 6:
            print(f"  ... ({len(chunks) - 6} more chunks)")


if __name__ == "__main__":
    main()
