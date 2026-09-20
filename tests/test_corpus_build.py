"""Tests for run_phase1's corpus-build parameters.

These guard two decisions that are invisible at query time but corrupt
retrieval quietly if they regress — both were found by measurement, not by
review.
"""
from run_phase1 import ALL_DOCS, _strip_other_script_lines, _window

HINDI_HEADER = "भाग III—खण् ड 4 भारत का रािपत्र : असाधारण"


def test_devanagari_running_header_is_stripped_from_english_pages():
    # The bilingual gazettes repeat this header on every page, including the
    # English ones. A near-pure Hindi string embeds close to ANY Hindi
    # question, so these chunks surfaced for unrelated Hindi queries: Hindi
    # expected-source-in-top-5 fell from 8/10 to 6/10 when the two bilingual
    # documents were added, and the worst offender was 61% Devanagari in a
    # 44-character chunk.
    page = f"{HINDI_HEADER}\nFOOD SAFETY AND STANDARDS AUTHORITY OF INDIA\nNOTIFICATION\n"
    cleaned = _strip_other_script_lines(page)
    assert HINDI_HEADER not in cleaned
    assert "FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA" in cleaned
    assert "NOTIFICATION" in cleaned


def test_english_text_containing_a_stray_devanagari_word_survives():
    # The threshold is a ratio, not "contains any Devanagari": a real English
    # line that quotes a Hindi term must not be discarded with the headers.
    line = "The expression आहार shall have the meaning assigned to it in these regulations."
    assert line in _strip_other_script_lines(line)


def test_window_blanks_outside_pages_but_preserves_numbering():
    # Blanked, not sliced: slicing renumbers every page, so a citation would
    # report page 2 for text on page 16 of the source PDF.
    pages = [f"page {i}" for i in range(1, 6)]
    windowed = _window(pages, (3, 4))
    assert len(windowed) == len(pages), "page count must not change"
    assert windowed[0] == "" and windowed[1] == "" and windowed[4] == ""
    assert windowed[2] == "page 3" and windowed[3] == "page 4"


def test_window_without_a_span_is_a_passthrough():
    pages = ["a", "b"]
    assert _window(pages, None) == pages


def test_bilingual_docs_declare_a_page_window():
    # If either loses its window, the Hindi half silently re-enters the index.
    windowed = {d["doc_id"] for d in ALL_DOCS if d.get("pages")}
    assert "fssai_ayurveda_aahara_regulations_2022" in windowed
    assert "biological_diversity_rules_2024" in windowed


def test_every_doc_spec_has_a_doc_id_and_file():
    for spec in ALL_DOCS:
        assert spec.get("doc_id"), spec
        assert spec.get("file"), spec


def test_doc_ids_are_unique():
    ids = [d["doc_id"] for d in ALL_DOCS]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
