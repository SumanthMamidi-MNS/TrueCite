from citation import format_citation, resolve_authority


def test_format_citation_includes_section_name_and_date():
    result = format_citation("patents_act_1970", "3(p)")
    assert "Patents Act, 1970" in result
    assert "3(p)" in result
    assert "2024-08-01" in result
    assert result.startswith("[Source:")


def test_format_citation_without_section():
    result = format_citation("wipo_documenting_tk_toolkit", None)
    assert "WIPO TK Documentation Toolkit" in result
    assert "2017-01-01" in result


def test_resolve_authority_puts_act_first():
    ordered = resolve_authority([
        "pib_faq_patents_traditional_ayurvedic_medicine_2013",
        "patents_act_1970",
        "ipo_tk_biological_material_guidelines_2012",
    ])
    assert ordered[0] == "patents_act_1970"


def test_resolve_authority_orders_guidelines_by_recency_within_same_rank():
    ordered = resolve_authority([
        "ipo_tk_biological_material_guidelines_2012",  # 2012
        "ipo_ayush_examination_guidelines_2025",  # 2025, same authority level
    ])
    assert ordered == ["ipo_ayush_examination_guidelines_2025", "ipo_tk_biological_material_guidelines_2012"]


def test_resolve_authority_never_lets_informational_outrank_a_guideline_despite_date():
    # WIPO toolkit (2017, Informational) vs TK Guidelines (2012, IPO Guideline) —
    # the guideline is older but must still outrank the informational source.
    ordered = resolve_authority([
        "wipo_documenting_tk_toolkit",
        "ipo_tk_biological_material_guidelines_2012",
    ])
    assert ordered == ["ipo_tk_biological_material_guidelines_2012", "wipo_documenting_tk_toolkit"]


def test_resolve_authority_full_ranking_is_stable_and_complete():
    all_docs = [
        "wipo_documenting_tk_toolkit",
        "ipo_ayush_examination_guidelines_2025",
        "pib_faq_patents_traditional_ayurvedic_medicine_2013",
        "patents_act_1970",
        "ipo_tk_biological_material_guidelines_2012",
    ]
    ordered = resolve_authority(all_docs)
    assert set(ordered) == set(all_docs)
    assert ordered[0] == "patents_act_1970"
    assert ordered[-1] in (
        "pib_faq_patents_traditional_ayurvedic_medicine_2013",
        "wipo_documenting_tk_toolkit",
    )
