"""Phase 1 gate: parse + structurally chunk all corpus documents and show the output.

Run: .venv/Scripts/python.exe src/run_phase1.py
"""
import json
import re
from dataclasses import asdict
from pathlib import Path

from chunking import chunk_document, validate_chunks
from parsing import extract_pages

CORPUS_RAW = Path(__file__).resolve().parent.parent / "corpus" / "raw"
CORPUS_PROCESSED = Path(__file__).resolve().parent.parent / "corpus" / "processed"

# Per-document chunking parameters. Every key beyond doc_id/file is optional and
# exists because some real document in this corpus needed it — none are
# speculative:
#
#   anchor       where the TOC/front matter ends and the structured body begins,
#                so a TOC's own section numbers aren't read as structure.
#   occurrence   which occurrence of that anchor (0-based). Treaties printing a
#                full TOC repeat every natural anchor, so the first hit is
#                inside the TOC and the body is never reached.
#   end_anchor   where a Schedule/annex begins. Schedules number their own
#                contents (the Drugs and Magic Remedies Act's lists 54
#                diseases) and those numbers climb, so the monotonic section
#                filter cannot tell them from real sections. Still indexed,
#                just as paragraphs rather than as fake sections.
#   style        "wide" for treaties whose articles use the title-case or
#                "Article N: Title" layouts (TRIPS, CBD) rather than the
#                uppercase "ARTICLE N" the GRATK treaty uses.
#   pages        (first, last) 1-indexed inclusive. Bilingual gazette texts run
#                Hindi first, then English; pages outside the window are blanked
#                rather than sliced away, so page numbers in citations stay true
#                to the source PDF.
ALL_DOCS = [
    # ---- original corpus (phases 1-9) ----
    {"doc_id": "patents_act_1970", "file": "patents_act_1970.pdf",
     "anchor": "BE it enacted by Parliament"},
    {"doc_id": "ipo_tk_biological_material_guidelines_2012",
     "file": "ipo_tk_biological_material_guidelines_2012.pdf"},
    {"doc_id": "pib_faq_patents_traditional_ayurvedic_medicine_2013",
     "file": "pib_faq_patents_traditional_ayurvedic_medicine_2013.txt"},
    {"doc_id": "ipo_ayush_examination_guidelines_2025",
     "file": "ipo_ayush_examination_guidelines_2025.pdf",
     # PDF extraction inserts a stray space here
     "anchor": "Ayush is traditional and non -conventional"},
    {"doc_id": "wipo_documenting_tk_toolkit", "file": "wipo_documenting_tk_toolkit.pdf",
     # cut before a mid-sentence line wrap
     "anchor": "Documenting traditional knowledge (TK) is now widely"},
    {"doc_id": "biological_diversity_act_2002", "file": "biological_diversity_act_2002.pdf",
     "anchor": "BE it enacted by parliament"},
    {"doc_id": "wipo_gratk_treaty_2024", "file": "wipo_gratk_treaty_2024.pdf"},

    # ---- phase 10: national IP regimes ----
    {"doc_id": "trade_marks_act_1999", "file": "trade_marks_act_1999.pdf"},
    {"doc_id": "geographical_indications_act_1999", "file": "geographical_indications_act_1999.pdf"},
    {"doc_id": "designs_act_2000", "file": "designs_act_2000.pdf"},
    {"doc_id": "copyright_act_1957", "file": "copyright_act_1957.pdf"},
    {"doc_id": "plant_varieties_act_2001", "file": "plant_varieties_act_2001.pdf"},

    # ---- phase 10: ABS ----
    {"doc_id": "biological_diversity_amendment_act_2023",
     "file": "biological_diversity_amendment_act_2023.pdf"},
    {"doc_id": "biological_diversity_rules_2024", "file": "biological_diversity_rules_2024.pdf",
     "pages": (51, 86), "end_anchor": "SCHEDULE"},

    # ---- phase 10: drug / advertising / food regimes ----
    # The Drugs and Magic Remedies (Objectionable Advertisements) Act, 1954 is
    # NOT here on purpose: the only copy sourced was a state drug-control
    # department's extract (no Act number, no assent date, no enacting formula,
    # the disease Schedule printed twice in two different versions), and
    # indiacode.nic.in is down. Citing a departmental compilation as primary
    # law is exactly the misrepresentation this project exists to prevent.
    # Recorded as an open gap in corpus/manifest.md.
    {"doc_id": "fssai_ayurveda_aahara_regulations_2022",
     "file": "fssai_ayurveda_aahara_regulations_2022.pdf",
     "pages": (15, 27), "anchor": "FOOD SAFETY AND STANDARDS AUTHORITY"},

    # ---- phase 10: international instruments ----
    {"doc_id": "trips_agreement", "file": "trips_agreement.pdf", "style": "wide"},
    {"doc_id": "cbd_convention", "file": "cbd_convention.pdf", "style": "wide"},
    {"doc_id": "nagoya_protocol", "file": "nagoya_protocol.pdf"},
    {"doc_id": "pct_treaty", "file": "pct_treaty.pdf"},
    {"doc_id": "madrid_protocol", "file": "madrid_protocol.pdf"},
]


# A line that is predominantly Devanagari, inside a page we are keeping for
# its ENGLISH content, is the bilingual gazette's running header repeating at
# every page break — not content. Left in, it poisons cross-lingual retrieval:
# these documents contributed 32 chunks each carrying the same 27-character
# Hindi header, and the worst (fssai::front-matter, 44 chars) was 61%
# Devanagari. A near-pure Hindi string embeds close to ANY Hindi question, so
# those chunks surfaced for unrelated Hindi queries and pushed the real answer
# out of the top 5 — measured: Hindi expected-source-in-top-5 fell 8/10 to
# 6/10 when these documents were added.
_DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ]")


def _strip_other_script_lines(page: str, threshold: float = 0.3) -> str:
    kept = []
    for line in page.split("\n"):
        letters = [c for c in line if c.isalpha()]
        if letters and len(_DEVANAGARI_RUN.findall(line)) / len(letters) >= threshold:
            continue
        kept.append(line)
    return "\n".join(kept)


def _window(pages: list[str], span: tuple[int, int] | None) -> list[str]:
    """Blank pages outside a 1-indexed inclusive span, keeping page numbering.

    Blanked rather than sliced on purpose: slicing renumbers every page, so a
    citation would report page 3 for text that is on page 53 of the source PDF.
    In a system whose whole claim is traceable citation, that is not an
    acceptable shortcut.

    Kept pages also have their Devanagari running headers stripped — see
    _strip_other_script_lines. Scoped to windowed (i.e. bilingual) documents
    only, so a future natively-Hindi corpus document is untouched.
    """
    if not span:
        return pages
    first, last = span
    return [
        "" if (i + 1) < first or (i + 1) > last else _strip_other_script_lines(p)
        for i, p in enumerate(pages)
    ]


def main():
    CORPUS_PROCESSED.mkdir(parents=True, exist_ok=True)
    for spec in ALL_DOCS:
        doc_id = spec["doc_id"]
        pages = _window(extract_pages(CORPUS_RAW / spec["file"]), spec.get("pages"))
        chunks = chunk_document(
            doc_id,
            pages,
            body_start_anchor=spec.get("anchor"),
            article_style=spec.get("style", "upper"),
            body_end_anchor=spec.get("end_anchor"),
            body_start_occurrence=spec.get("occurrence", 0),
        )
        validate_chunks(doc_id, chunks)

        out_path = CORPUS_PROCESSED / f"{doc_id}.json"
        out_path.write_text(
            json.dumps([asdict(c) for c in chunks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\n{'=' * 70}")
        print(f"{doc_id}  ({len(pages)} pages -> {len(chunks)} chunks)")
        print(f"written to {out_path.relative_to(out_path.parent.parent.parent)}")
        print("-" * 70)
        for c in chunks[:4]:
            preview = c.text[:160].replace("\n", " ")
            # Windows console encoding (cp1252) can't print every PDF glyph
            # (e.g. private-use-area bullet chars); replace rather than crash.
            safe_preview = preview.encode("ascii", errors="replace").decode("ascii")
            print(f"[{c.chunk_id}] p{c.page_start}-{c.page_end} ({c.char_count} chars)")
            print(f"  heading: {c.heading!r}")
            print(f"  text:    {safe_preview}...")
        if len(chunks) > 4:
            print(f"  ... ({len(chunks) - 4} more chunks)")


if __name__ == "__main__":
    main()
