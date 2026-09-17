"""Unit tests for enrichment.py (docs/decisions.md, 2026-09-16 cross-reference
and context-header fixes).

Two things are under test: (1) the trailer/header-building logic itself, and
(2) THE SAFETY PROPERTY — that the enriched text used for scoring never leaks
into what a hit actually returns, through either indexing.py's real Chroma
build_index() path or bm25_retrieval.py's BM25Index. The leakage tests are the
most important in this file: a passing trailer/header test with a leaking
wire-up would still be a shipped defect (a fabricated-looking citation
reaching the user), so they exercise the real production code paths rather
than just calling build_retrieval_text directly again.
"""
import json

import pytest

import enrichment
from enrichment import build_context_header, build_headings_by_section, build_retrieval_text


# --- build_retrieval_text -------------------------------------------------

def _chunk(chunk_id, doc_id, section_number, heading, text, parent_section_number=None,
           page_start=1, page_end=1):
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "heading": heading,
        "section_number": section_number,
        "parent_section_number": parent_section_number,
        "page_start": page_start,
        "page_end": page_end,
        "text": text,
    }


def test_sec55_style_text_gets_trailer_with_referenced_headings_and_true_text_prefix():
    # Mirrors the measured defect exactly (docs/decisions.md): sec-55 never
    # says "access" or "approval" itself, it only points at sections 3, 4
    # and 6 by number. Headings recovered for 3 and 6 (see module docstring
    # of enrichment.py); 4 is deliberately left OUT of this fixture's
    # headings map, to also exercise "skip references with no recovered
    # heading" using the exact same real-world reference list.
    sec55 = _chunk(
        "bda::sec-55", "bda", "55", "Penalties",
        "55. Penalties.\n(1) Whoever contravenes or attempts to contravene or abets the "
        "contravention of the provisions of section 3 or section 4 or section 6 shall be "
        "punishable with imprisonment for a term which may extend to five years.",
    )
    headings_by_section = {
        "3": "Certain persons not to undertake activities without approval",
        "6": "Application for intellectual property rights not to be made without approval",
        # "4" intentionally absent.
    }

    result = build_retrieval_text(sec55, headings_by_section)

    assert result.startswith(sec55["text"])
    trailer = result[len(sec55["text"]):]
    assert trailer.startswith("\n\n[Cross-references: ")
    assert trailer.endswith("]")
    assert "section 3 — Certain persons not to undertake activities without approval" in trailer
    assert "section 6 — Application for intellectual property rights not to be made without approval" in trailer
    # Section 4 matched the reference pattern but has no recovered heading in
    # this fixture, so it must not appear at all — neither its number as a
    # cross-reference entry nor any placeholder.
    assert "section 4 —" not in trailer


def test_cross_statute_reference_is_not_enriched_with_local_heading():
    # The exact evidence case from the task: biological_diversity_act_2002's
    # own section 3 contains "clause (30) of section 2 of the Income-tax
    # Act, 1961". Enriching this chunk with the BDA's OWN section 2 heading
    # would be factually wrong — "section 2" here names a DIFFERENT
    # statute's section entirely.
    sec3 = _chunk(
        "bda::sec-3", "bda", "3", "Certain persons not to undertake ... without approval",
        "(b) a citizen of India, who is non-resident as defined in clause (30) of "
        "section 2 of the Income-tax Act, 1961 (43 of 1961);",
    )
    headings_by_section = {
        # If this local section 2 heading leaked in, the bug would be visible.
        "2": "Definitions",
    }

    result = build_retrieval_text(sec3, headings_by_section)

    assert result == sec3["text"]


def test_sub_section_of_section_resolves_to_the_outer_section_not_the_sub_section_number():
    # "sub-section (2) of section 24" must reference section 24, never "2"
    # (which is just the BDA's own internal subsection numbering, not a
    # cross-reference at all).
    chunk = _chunk(
        "bda::sec-55b", "bda", "55", "Penalties",
        "Whoever contravenes any order made under sub-section (2) of section 24 shall "
        "be punishable.",
    )
    headings_by_section = {
        "2": "WRONG — must never be picked up",
        "24": "Power to issue directions",
    }

    result = build_retrieval_text(chunk, headings_by_section)

    assert "section 24 — Power to issue directions" in result
    assert "section 2 —" not in result


def test_self_reference_is_skipped():
    chunk = _chunk(
        "bda::sec-5", "bda", "5", "Some heading",
        "Nothing in section 5 shall apply to the following cases mentioned in section 5.",
    )
    headings_by_section = {"5": "Some heading"}

    result = build_retrieval_text(chunk, headings_by_section)

    assert result == chunk["text"]


def test_more_than_five_references_capped_at_five():
    numbers = list(range(1, 9))  # 8 candidate references
    text = "This section refers to " + ", ".join(f"section {n}" for n in numbers) + "."
    chunk = _chunk("doc::sec-99", "doc", "99", "Heading", text)
    headings_by_section = {str(n): f"Heading {n}" for n in numbers}

    result = build_retrieval_text(chunk, headings_by_section)
    trailer = result[len(chunk["text"]):]

    included = sum(1 for n in numbers if f"section {n} —" in trailer)
    assert included == 5


def test_trailer_length_is_capped_around_400_chars():
    long_heading = "A " * 250  # a single, unrealistically long heading
    chunk = _chunk(
        "doc::sec-1", "doc", "1", "Heading",
        "See section 2 for details.",
    )
    headings_by_section = {"2": long_heading}

    result = build_retrieval_text(chunk, headings_by_section)
    trailer = result[len(chunk["text"]):]

    assert len(trailer) <= 450  # "~400", with slack for the truncation ellipsis/wrapper
    assert trailer  # a reference did qualify, so *some* trailer must still appear


def test_unchanged_when_no_qualifying_references():
    chunk = _chunk(
        "doc::sec-1", "doc", "1", "Heading",
        "This section has no references to any other section at all.",
    )
    assert build_retrieval_text(chunk, {}) == chunk["text"]

    # Also unchanged when a reference exists in the text but no heading was
    # ever recovered for it.
    chunk2 = _chunk("doc::sec-1", "doc", "1", "Heading", "See section 9 for details.")
    assert build_retrieval_text(chunk2, {}) == chunk2["text"]


# --- build_headings_by_section --------------------------------------------

def test_build_headings_by_section_uses_parent_section_number_for_split_chunks():
    chunks = [
        _chunk("doc::sec-3-sub-1", "doc", "3(1)", "Real Heading", "text one",
               parent_section_number="3"),
        _chunk("doc::sec-3-sub-2", "doc", "3(2)", "Real Heading", "text two",
               parent_section_number="3"),
    ]
    headings = build_headings_by_section(chunks)
    assert headings == {"3": "Real Heading"}


def test_build_headings_by_section_skips_generic_and_missing_headings():
    chunks = [
        _chunk("doc::para-7", "doc", "7", "Paragraph 7", "unstructured body"),
        _chunk("doc::preamble", "doc", None, "Preamble", "preamble text"),
        _chunk("doc::front", "doc", None, "Front matter / table of contents", "toc"),
        _chunk("doc::unstructured", "doc", None, "(unstructured)", "body"),
        _chunk("doc::sec-9", "doc", "9", "Penalties", "real section text"),
    ]
    headings = build_headings_by_section(chunks)
    assert headings == {"9": "Penalties"}


# --- build_context_header --------------------------------------------------
# Uses real doc_ids from authority.py (patents_act_1970, wipo_gratk_treaty_2024,
# biological_diversity_act_2002) rather than fictional ones, so a test
# failure here would also catch a mismatch against the real authority.py data
# (e.g. a renamed short_name) rather than only a self-consistent fixture.

def test_article_17_style_chunk_gets_header_with_treaty_name_and_article_and_heading():
    chunk = _chunk(
        "wipo_gratk_treaty_2024::article-17", "wipo_gratk_treaty_2024", "Article 17",
        "ENTRY INTO FORCE",
        "ARTICLE 17 \nENTRY INTO FORCE \nThis Treaty shall enter into force three months "
        "after 15 eligible parties referred to in Article 12 have deposited their "
        "instruments of ratification or accession.",
    )
    header = build_context_header(chunk)
    assert header.startswith("[") and header.endswith("]")
    assert "WIPO GRATK Treaty" in header
    assert "Article 17" in header
    assert "ENTRY INTO FORCE" in header


def test_sec_3i_clause_chunk_gets_patents_act_title_and_section_3i_label():
    chunk = _chunk(
        "patents_act_1970::sec-3-clause-i", "patents_act_1970", "3(i)",
        "What are not inventions",
        "3. What are not inventions.\n(i) any process for the medicinal ... treatment "
        "of human beings",
        parent_section_number="3",
    )
    header = build_context_header(chunk)
    assert "Patents Act" in header
    assert "§3(i)" in header
    assert "What are not inventions" in header


def test_sec_3j_clause_chunk_gets_patents_act_title_and_section_3j_label():
    chunk = _chunk(
        "patents_act_1970::sec-3-clause-j", "patents_act_1970", "3(j)",
        "What are not inventions",
        "(j) plants and animals in whole or any part thereof other than micro-organisms",
        parent_section_number="3",
    )
    header = build_context_header(chunk)
    assert "Patents Act" in header
    assert "§3(j)" in header


def test_bda_sec55_chunk_gets_biological_diversity_act_title_and_section_55_label():
    chunk = _chunk(
        "biological_diversity_act_2002::sec-55", "biological_diversity_act_2002", "55",
        "Penalties",
        "55. Penalties.\n(1) Whoever contravenes ...",
    )
    header = build_context_header(chunk)
    assert "Biological Diversity Act" in header
    assert "§55" in header
    assert "Penalties" in header


def test_generic_paragraph_heading_is_omitted_from_header():
    # A numbered-paragraph guideline section with a real section_number but
    # only the chunker's generic "Paragraph N" placeholder heading (no real
    # title recovered) — the header must include the section label but not
    # the meaningless placeholder text.
    chunk = _chunk(
        "ipo_tk_biological_material_guidelines_2012::sec-7",
        "ipo_tk_biological_material_guidelines_2012", "7", "Paragraph 7",
        "Some guideline paragraph body text.",
    )
    header = build_context_header(chunk)
    assert "Paragraph 7" not in header
    assert "paragraph 7" in header  # the section label itself, not the heading


def test_front_matter_chunk_gets_no_section_label():
    chunk = _chunk(
        "patents_act_1970::preamble", "patents_act_1970", None, "Preamble",
        "An Act to amend and consolidate the law relating to patents.",
    )
    header = build_context_header(chunk)
    assert header == "[Patents Act, 1970]"


def test_unknown_doc_id_produces_no_header():
    chunk = _chunk("unknown::sec-1", "unknown_doc_not_in_authority", "1", "Some Heading", "text")
    assert build_context_header(chunk) == ""


def test_header_is_prepended_before_true_text_and_before_any_cross_reference_trailer():
    sec55 = _chunk(
        "biological_diversity_act_2002::sec-55", "biological_diversity_act_2002", "55",
        "Penalties",
        "55. Penalties.\n(1) Whoever contravenes the provisions of section 3 or section 4 "
        "or section 6 shall be punishable.",
    )
    headings_by_section = {
        "3": "Certain persons not to undertake activities without approval",
        "6": "Application for intellectual property rights not to be made without approval",
    }

    result = build_retrieval_text(sec55, headings_by_section)
    header = build_context_header(sec55)

    assert result.startswith(header + "\n\n")
    rest = result[len(header) + 2 :]
    assert rest.startswith(sec55["text"])
    assert rest.endswith("]")
    assert "[Cross-references: " in rest
    assert "section 3 — Certain persons not to undertake activities without approval" in rest


def test_context_header_disabled_matches_pre_header_output(monkeypatch):
    monkeypatch.setattr(enrichment, "CONTEXT_HEADER_ENABLED", False)

    sec55 = _chunk(
        "biological_diversity_act_2002::sec-55", "biological_diversity_act_2002", "55",
        "Penalties",
        "55. Penalties.\n(1) Whoever contravenes the provisions of section 3 or section 4 "
        "or section 6 shall be punishable.",
    )
    headings_by_section = {
        "3": "Certain persons not to undertake activities without approval",
        "6": "Application for intellectual property rights not to be made without approval",
    }

    result = build_retrieval_text(sec55, headings_by_section)
    assert build_context_header(sec55) == ""
    assert result == sec55["text"] + (
        "\n\n[Cross-references: section 3 — Certain persons not to undertake "
        "activities without approval; section 6 — Application for intellectual "
        "property rights not to be made without approval]"
    )

    # And a chunk with no qualifying references at all is completely untouched.
    plain = _chunk("patents_act_1970::sec-3-clause-i", "patents_act_1970", "3(i)",
                    "What are not inventions", "no references here")
    assert build_retrieval_text(plain, {}) == plain["text"]


# --- Leakage tests: the safety property, through the real wiring ---------

def test_indexing_build_index_never_returns_enriched_text_in_a_hit(tmp_path, monkeypatch):
    """The most important test in this file.

    Runs the REAL indexing.build_index() code path (documents/embeddings
    wiring untouched) against a tiny fixture corpus on a temp Chroma dir,
    with only the embedding model swapped for a fast deterministic stub
    (loading bge-m3 here would make this test far too slow for a unit
    suite). Then asserts every chunk you can fetch back out of the
    collection has its TRUE text, byte for byte, with no cross-reference
    trailer anywhere in it.
    """
    import indexing

    # doc_id is a REAL authority.py entry (not a fictional "fixdoc") so both
    # the cross-reference trailer AND the context header actually fire —
    # otherwise this test would only ever exercise the trailer.
    fixture_doc = [
        {
            "doc_id": "patents_act_1970",
            "chunk_id": "patents_act_1970::fix-sec-3",
            "heading": "Alpha Provisions",
            "section_number": "3",
            "parent_section_number": None,
            "page_start": 1,
            "page_end": 1,
            "text": "3. Alpha Provisions.\nNo person shall do the alpha thing without approval.",
        },
        {
            "doc_id": "patents_act_1970",
            "chunk_id": "patents_act_1970::fix-sec-9",
            "heading": "Penalties",
            "section_number": "9",
            "parent_section_number": None,
            "page_start": 2,
            "page_end": 2,
            "text": "9. Penalties.\nWhoever contravenes section 3 shall be punished with a fine.",
        },
    ]
    corpus_dir = tmp_path / "processed"
    corpus_dir.mkdir()
    (corpus_dir / "fixdoc.json").write_text(json.dumps(fixture_doc), encoding="utf-8")

    monkeypatch.setattr(indexing, "CORPUS_PROCESSED", corpus_dir)
    monkeypatch.setattr(indexing, "CHROMA_DB_PATH", tmp_path / "chroma_db")

    embedded_texts = []

    def _fake_embed_texts(texts):
        # Real embeddings wiring stays real (embed_texts is still called with
        # the actual enriched strings and its return actually gets passed to
        # collection.add) — only the model itself is swapped for something
        # that doesn't require loading bge-m3 in a unit test. Captured so the
        # test can also confirm enrichment (trailer AND header) actually
        # fired on the embedded text, not just that it didn't leak.
        embedded_texts.extend(texts)
        return [[float(len(t) % 13), 1.0, 0.5] for t in texts]

    monkeypatch.setattr(indexing, "embed_texts", _fake_embed_texts)

    collection = indexing.build_index(batch_size=10)

    ids = ["patents_act_1970::fix-sec-3", "patents_act_1970::fix-sec-9"]
    got = collection.get(ids=ids, include=["documents"])
    returned = dict(zip(got["ids"], got["documents"]))

    for chunk in fixture_doc:
        assert returned[chunk["chunk_id"]] == chunk["text"]
        assert "[Cross-references:" not in returned[chunk["chunk_id"]]
        # The context header's own marker ("[Patents Act, 1970 ...") must
        # never leak into a returned hit either.
        assert "[Patents Act, 1970" not in returned[chunk["chunk_id"]]

    # Confirm the enrichment (both the trailer AND the header) actually fired
    # on the text that was embedded — this test would catch a regression
    # where enrichment silently stopped being applied, not just one where it
    # leaked.
    sec9_embedded = next(t for t in embedded_texts if "§9:" in t)
    assert sec9_embedded.startswith("[Patents Act, 1970 — §9: Penalties]\n\n")
    assert fixture_doc[1]["text"] in sec9_embedded
    assert "[Cross-references: section 3 — Alpha Provisions]" in sec9_embedded


def test_bm25_index_never_returns_enriched_text_in_a_hit():
    """Mirrors the indexing.py leakage test for bm25_retrieval.BM25Index."""
    from bm25_retrieval import BM25Index

    # doc_id is a REAL authority.py entry so the context header fires too
    # (see the matching comment in the indexing.py leakage test above).
    chunks = [
        {
            "doc_id": "patents_act_1970",
            "chunk_id": "patents_act_1970::fix-sec-3",
            "heading": "Alpha Provisions",
            "section_number": "3",
            "parent_section_number": None,
            "page_start": 1,
            "page_end": 1,
            "text": "3. Alpha Provisions.\nNo person shall do the alpha thing without approval.",
        },
        {
            "doc_id": "patents_act_1970",
            "chunk_id": "patents_act_1970::fix-sec-9",
            "heading": "Penalties",
            "section_number": "9",
            "parent_section_number": None,
            "page_start": 2,
            "page_end": 2,
            "text": "9. Penalties.\nWhoever contravenes section 3 shall be punished with a fine.",
        },
    ]
    index = BM25Index(chunks)

    hits = index.retrieve("penalties contravenes section 3", top_k=5)
    assert hits, "expected at least one BM25 hit"
    by_id = {h["chunk_id"]: h["text"] for h in hits}
    for chunk in chunks:
        if chunk["chunk_id"] in by_id:
            assert by_id[chunk["chunk_id"]] == chunk["text"]
            assert "[Cross-references:" not in by_id[chunk["chunk_id"]]
            assert "[Patents Act, 1970" not in by_id[chunk["chunk_id"]]
