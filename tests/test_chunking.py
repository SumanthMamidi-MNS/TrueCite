"""Regression tests for chunking.py, one per real bug caught during Phase 1
manual chunk-quality review (see docs/decisions.md for the incident each
one corresponds to). Synthetic inputs, not the real corpus PDFs, so these
stay fast and self-contained.
"""
from types import SimpleNamespace

import pytest

from chunking import (
    MAX_CHUNK_CHARS,
    MIN_SECTION_BODY_CHARS,
    SUBSECTION_RE,
    _split_section_body,
    chunk_document,
)


def test_footnote_text_does_not_create_spurious_section_or_swallow_real_one():
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act and extends to the "
        "whole of India for all purposes described in this section at length.\n"
        "2. Definitions.—(1) In this Act, unless context otherwise requires, this is "
        "a long definitions clause with enough text to count as a real section body here.\n"
        "\n"
        "1. Ins. by Act 1 of 2000, s. 2 (w.e.f. 1-1-2000).\n"
        "\n"
        "3. What are not inventions.—The following are not inventions: (a) frivolous "
        "inventions; (p) an invention which, in effect, is traditional knowledge.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    section_numbers = [c.section_number for c in chunks if c.section_number]
    assert "3" in section_numbers, f"section 3 missing entirely: {section_numbers}"
    sec3 = next(c for c in chunks if c.section_number == "3")
    assert "traditional knowledge" in sec3.text
    # the footnote's own leading "1." must not appear as a second, spurious section 1
    assert section_numbers.count("1") == 1


def test_bracket_fused_section_number_is_still_detected():
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act and extends to the "
        "whole of India for all purposes described in this section at some length.\n"
        "2[11A. Publication of applications.—(1) Save as otherwise provided, no "
        "application for patent shall ordinarily be opened to the public for such "
        "period as may be prescribed under the rules made under this Act.\n"
        "(2) The applicant may request early publication in the prescribed manner at "
        "any time before the expiry of the prescribed period set out above.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    section_numbers = [c.section_number for c in chunks if c.section_number]
    assert any(s and s.startswith("11A") for s in section_numbers), section_numbers


def test_leading_whitespace_before_section_number_is_tolerated():
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act and extends to the "
        "whole of India for all purposes described in this section at some length.\n"
        " 41. Finality of orders.—All orders made under this Chapter shall be final "
        "and shall not be questioned in any court by way of appeal or otherwise.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    section_numbers = [c.section_number for c in chunks if c.section_number]
    assert "41" in section_numbers, section_numbers


def test_unnumbered_preamble_text_is_not_silently_dropped():
    page = (
        "Some intro paragraph that is long enough to exceed the minimum body "
        "length threshold for being kept as a preamble chunk in its own right, "
        "with a bit of extra padding text included here.\n"
        "\n"
        "1. First point.—Some content that is long enough to count as a real "
        "body for this synthetic first section used in the test.\n"
        "2. Second point.—More content that is long enough to count as a real "
        "body for this synthetic second section used in the test.\n"
    )
    chunks = chunk_document("test_doc", [page])
    assert any("Some intro paragraph" in c.text for c in chunks), [c.text[:50] for c in chunks]


def test_oversized_section_without_numeric_subsections_falls_back_to_paragraphs():
    padding_paragraph = "Paragraph text repeated to pad the section length out. " * 5
    big_body = "\n\n".join([padding_paragraph] * 20)  # no "(1)"-style tokens in here
    assert len(big_body) > MAX_CHUNK_CHARS
    page = (
        "BE it enacted by Parliament as follows:\n"
        f"1. Big section.—{big_body}\n"
        "2. Small section.—A short section that follows the oversized one, long "
        "enough to clear the minimum section-body threshold on its own.\n"
    )
    chunks = chunk_document("test_doc", [page], body_start_anchor="BE it enacted")
    part_chunks = [c for c in chunks if c.parent_section_number == "1"]
    assert len(part_chunks) >= 2, "expected the oversized section to split into multiple parts"
    for c in part_chunks:
        assert c.char_count <= MAX_CHUNK_CHARS


def test_no_duplicate_chunk_ids_across_a_multi_section_document():
    page = (
        "BE it enacted by Parliament as follows:\n"
        + "".join(
            f"{n}. Section {n}.—Body text for section number {n}, long enough to "
            f"clear the minimum section-body length threshold used by the chunker.\n"
            for n in range(1, 15)
        )
    )
    chunks = chunk_document("test_doc", [page], body_start_anchor="BE it enacted")
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), f"duplicate chunk_ids: {[i for i in ids if ids.count(i) > 1]}"


def test_body_start_anchor_not_found_raises_instead_of_silently_degrading():
    page = "BE it enacted by Parliament as follows:\n1. Short title.—Some text.\n"
    try:
        chunk_document("test_doc", [page], body_start_anchor="text that does not appear anywhere")
        assert False, "expected ValueError for a missing anchor"
    except ValueError:
        pass


def test_min_section_body_threshold_drops_trivially_short_matches():
    # sanity check the constant is still what the other tests assume
    assert MIN_SECTION_BODY_CHARS < 100


def test_lettered_clause_list_splits_per_clause_with_intro_context():
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act and extends to the "
        "whole of India for all purposes described in this section at some length.\n"
        "3. What are not inventions.—The following are not inventions within the "
        "meaning of this Act,—\n"
        "(a) an invention which is frivolous or which claims anything obviously "
        "contrary to well established natural laws;\n"
        "(b) the mere discovery of a scientific principle;\n"
        "(c) a method of agriculture or horticulture;\n"
        "(p) an invention which, in effect, is traditional knowledge or which is "
        "an aggregation or duplication of known properties of traditionally "
        "known component or components.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    clause_p = next((c for c in chunks if c.section_number == "3(p)"), None)
    assert clause_p is not None, [c.section_number for c in chunks]
    assert "traditional knowledge" in clause_p.text
    assert "not inventions" in clause_p.text, "clause should keep the section's intro framing"


def test_inline_subsection_1_is_not_lost_when_section_has_numeric_subsections():
    # "(1)" inline with the heading (no line break before it) is the normal
    # pattern in this corpus's Acts — it must not be silently dropped just
    # because it doesn't start its own line the way "(2)" onward do. Unit-
    # tested directly against _split_section_body (rather than through the
    # full pipeline) so the test doesn't depend on padding the body out past
    # MAX_CHUNK_CHARS just to reach this code path.
    body = (
        "19. Powers of Controller.—(1) If, in consequence of investigations, "
        "it appears to the Controller that an invention cannot be performed.\n"
        "(2) Where a reference has been inserted in a specification, the "
        "patentee may apply to the Controller in the prescribed manner.\n"
    )
    chunks = _split_section_body(
        "test_act", "19", "Powers of Controller", body, body_start_offset=0, offsets=[0]
    )
    sub1 = next((c for c in chunks if c.section_number == "19(1)"), None)
    assert sub1 is not None, [c.section_number for c in chunks]
    assert "consequence of investigations" in sub1.text
    sub2 = next((c for c in chunks if c.section_number == "19(2)"), None)
    assert sub2 is not None
    assert "prescribed manner" in sub2.text


def test_line_wrapped_calendar_year_is_not_mistaken_for_a_section_number():
    # Real bug found live: "...published in November \n2012. Mr. Ruiz
    # contributed..." — a PDF line-wrap puts "2012." at line start, which
    # SECTION_RE would otherwise read as section "2012", swallowing
    # everything after it into one oversized chunk.
    page = (
        "BE it enacted by Parliament as follows:\n"
        "3. Getting started.—A consultation draft was published in November\n"
        "2012. Mr. Ruiz contributed significantly to that draft, long enough "
        "to be real content that must not become its own section here.\n"
        "4. Next real section.—Some content long enough to count as a real "
        "section body for this synthetic test case used here.\n"
    )
    chunks = chunk_document("test_doc", [page], body_start_anchor="BE it enacted")
    section_numbers = [c.section_number for c in chunks if c.section_number]
    assert "2012" not in section_numbers, section_numbers
    sec3 = next(c for c in chunks if c.section_number == "3")
    assert "Mr. Ruiz contributed" in sec3.text
    assert "4" in section_numbers, section_numbers


def test_treaty_article_headings_are_chunked_when_no_numeric_sections_exist():
    # A second numbering convention alongside "N. Title.—": international
    # treaty text numbers "ARTICLE N" with the title on the next line. Only
    # reached when the numeric SECTION_RE finds nothing at all — this test's
    # page has zero "N. " style sections, so it must fall into this path
    # rather than plain unstructured paragraph chunking.
    page = (
        "Have agreed as follows:\n"
        "ARTICLE 1\n"
        "OBJECTIVES\n"
        "The objectives of this Treaty are to enhance the efficacy of the "
        "patent system with regard to genetic resources, long enough to count.\n"
        "ARTICLE 2\n"
        "LIST OF TERMS\n"
        "For the purposes of this Treaty, 'Applicant' means the person who "
        "applies for the grant of a patent, long enough to count as real body text.\n"
    )
    chunks = chunk_document("test_treaty", [page])
    article1 = next((c for c in chunks if c.section_number == "Article 1"), None)
    assert article1 is not None, [c.section_number for c in chunks]
    assert article1.heading == "OBJECTIVES"
    assert "genetic resources" in article1.text
    article2 = next((c for c in chunks if c.section_number == "Article 2"), None)
    assert article2 is not None
    assert article2.heading == "LIST OF TERMS"


def test_treaty_article_heading_tolerates_narrow_nbsp_after_number():
    # Confirmed directly on the real WIPO GRATK Treaty PDF's extracted text:
    # one heading used a narrow-no-break space (U+202F) instead of an ASCII
    # space after the article number, which a plain [ \t] class would miss.
    page = (
        "Have agreed as follows:\n"
        "ARTICLE 1    \n"
        "DEPOSITARY   \n"
        "The Director General is the depositary of this Treaty, long enough "
        "to count as real body text for this synthetic test case here.\n"
        "ARTICLE 2\n"
        "LANGUAGES\n"
        "This Treaty shall be signed in a single original, long enough to "
        "count as real body text for this synthetic test case as well.\n"
    )
    chunks = chunk_document("test_treaty", [page])
    section_numbers = [c.section_number for c in chunks]
    assert "Article 1" in section_numbers, section_numbers


def test_numbered_sections_still_take_priority_over_article_pattern():
    # A document with real numbered sections must never fall into the treaty
    # path even if it happens to also contain the literal word "ARTICLE"
    # somewhere in body text (e.g. a cross-reference to another instrument).
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act, referencing "
        "ARTICLE 5 of an unrelated treaty for context, long enough for the body.\n"
        "2. Definitions.—(1) In this Act, unless the context otherwise "
        "requires, this is a long enough definitions clause for the test.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    section_numbers = [c.section_number for c in chunks if c.section_number]
    assert "1" in section_numbers and "2" in section_numbers
    assert not any(s and s.startswith("Article") for s in section_numbers)


def test_converter_artifact_line_is_stripped():
    page = (
        "BE it enacted by parliament as follows:\n"
        "/root/convert/apache-tomcat-6.0.20/temp/BDA, 20022408441392335261370.doc\n"
        "1. Short title, extent and commencement.\n"
        "(1) This Act may be called the Test Act, long enough for real body text.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    assert not any("apache-tomcat" in c.text for c in chunks)


def test_doc_code_running_header_is_stripped():
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act and extends to "
        "the whole of India for all purposes described at some length here.\n"
        "GRATK/DC/7\n"
        "2. Definitions.—(1) In this Act, unless the context otherwise "
        "requires, this is a long enough definitions clause for the test.\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    assert not any("GRATK/DC/7" in c.text for c in chunks)


def test_midsentence_lettered_reference_does_not_create_duplicate_clause():
    # A cross-reference like "...described in clause (b) of this section..."
    # can end up starting its own PDF-wrapped line without being a real new
    # list item — must not be mistaken for a second "(b)".
    page = (
        "BE it enacted by Parliament as follows:\n"
        "1. Short title.—(1) This may be called the Test Act and extends to the "
        "whole of India for all purposes described in this section at some length.\n"
        "2. Definitions.—(1) In this Act, unless the context otherwise requires,\n"
        "(a) 'assignee' includes an assignee of the assignee and the legal "
        "representative of a deceased assignee, long enough to be real content;\n"
        "(b) 'Controller' means the Controller General of Patents, Designs and "
        "Trade Marks referred to in section 73, long enough to be real content;\n"
        "(c) any reference in this Act to the patent office shall be construed "
        "as including a reference to any branch office as described in clause\n"
        "(b) of this section for the purposes of jurisdiction under this Act;\n"
    )
    chunks = chunk_document("test_act", [page], body_start_anchor="BE it enacted")
    clause_b_chunks = [c for c in chunks if c.section_number == "2(b)"]
    assert len(clause_b_chunks) == 1, f"expected exactly one clause (b), got {len(clause_b_chunks)}"


def test_validate_chunks_accepts_clean_output():
    from chunking import validate_chunks
    chunks = [
        SimpleNamespace(chunk_id="d::sec-1", char_count=500, page_start=1, page_end=1),
        SimpleNamespace(chunk_id="d::sec-2", char_count=900, page_start=1, page_end=2),
    ]
    validate_chunks("d", chunks)  # must not raise


def test_validate_chunks_rejects_duplicate_ids():
    # The dangerous failure: the vector store upserts by id, so duplicates
    # overwrite rather than error, and the corpus silently shrinks.
    from chunking import validate_chunks
    chunks = [
        SimpleNamespace(chunk_id="d::sec-451-sub-2", char_count=80, page_start=3, page_end=3),
        SimpleNamespace(chunk_id="d::sec-451-sub-2", char_count=59, page_start=9, page_end=9),
    ]
    with pytest.raises(ValueError, match="duplicate chunk_id"):
        validate_chunks("d", chunks)


def test_validate_chunks_rejects_oversized_chunk():
    from chunking import MAX_INDEXABLE_CHUNK_CHARS, validate_chunks
    chunks = [
        SimpleNamespace(
            chunk_id="d::sec-451-sub-6",
            char_count=MAX_INDEXABLE_CHUNK_CHARS + 1,
            page_start=203,
            page_end=264,
        )
    ]
    with pytest.raises(ValueError, match="MAX_INDEXABLE_CHUNK_CHARS"):
        validate_chunks("d", chunks)


def test_cross_reference_line_does_not_fabricate_a_duplicate_subsection():
    # Real bug (GI Act 1999, Designs Act 2000): PDF extraction wraps a
    # sentence so a cross-reference lands at line start, e.g.
    # "(2) of Section 3; (e) to the Registry...". SUBSECTION_RE anchors to
    # line start, so it matched, fabricating a second "sub-2" that collided
    # with the real one and overwrote it at index time.
    from chunking import _monotonic_subsections
    import re as _re
    body = (
        "(1) The first real subsection runs here.\n"
        "(2) The second real subsection runs here.\n"
        "(2) of Section 3; (e) to the Registry shall be construed as including\n"
        "(3) The third real subsection runs here.\n"
    )
    matches = list(SUBSECTION_RE.finditer(body))
    assert [m.group(1) for m in matches] == ["1", "2", "2", "3"]
    kept = _monotonic_subsections(matches)
    assert [m.group(1) for m in kept] == ["1", "2", "3"]


def test_lettered_subsection_still_counts_as_advancing():
    # 3A is a genuine distinct subsection in Indian drafting and must survive
    # the monotonic filter -- (3, "") < (3, "A").
    from chunking import _monotonic_subsections
    body = "(3) Third subsection text here.\n(3A) Inserted subsection text here.\n(4) Fourth subsection.\n"
    kept = _monotonic_subsections(list(SUBSECTION_RE.finditer(body)))
    assert [m.group(1) for m in kept] == ["3", "3A", "4"]


def test_rejected_marker_does_not_lose_text():
    # The filter must only decline to SPLIT, never drop content: the
    # cross-reference text has to remain inside the preceding chunk.
    from chunking import _monotonic_subsections
    body = (
        "(1) First subsection.\n"
        "(1) of section 15; (o) the rules to dispense with requirements\n"
        "(2) Second subsection.\n"
    )
    kept = _monotonic_subsections(list(SUBSECTION_RE.finditer(body)))
    spans = [body[kept[i].start(): (kept[i + 1].start() if i + 1 < len(kept) else len(body))]
             for i in range(len(kept))]
    assert "of section 15" in "".join(spans), "cross-reference text was dropped"
