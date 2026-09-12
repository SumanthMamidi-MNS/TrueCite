"""Regression tests for chunking.py, one per real bug caught during Phase 1
manual chunk-quality review (see docs/decisions.md for the incident each
one corresponds to). Synthetic inputs, not the real corpus PDFs, so these
stay fast and self-contained.
"""
from chunking import MAX_CHUNK_CHARS, MIN_SECTION_BODY_CHARS, _split_section_body, chunk_document


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
