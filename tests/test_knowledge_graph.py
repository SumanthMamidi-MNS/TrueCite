from authority import DOC_AUTHORITY
from knowledge_graph import (
    INSTRUMENT_RELATIONS,
    RELATION_PHRASES,
    _references,
    graph_stats,
    related_instruments,
    section_references,
)


def test_every_relation_names_real_instruments_and_a_known_relation():
    # A typo here would silently drop an edge rather than fail.
    for src, rel, dst, _ in INSTRUMENT_RELATIONS:
        assert src in DOC_AUTHORITY, src
        assert dst in DOC_AUTHORITY, dst
        assert rel in RELATION_PHRASES, rel
        assert src != dst


def test_stale_act_points_to_its_amendment():
    # The whole reason the graph earns its place: the 2002 Act is as-enacted,
    # and an answer citing it must point the reader to what amended it.
    rel = {(r["relation"], r["doc_id"]) for r in related_instruments(["biological_diversity_act_2002"])}
    assert ("is amended by", "biological_diversity_amendment_act_2023") in rel
    assert ("has rules made under it", "biological_diversity_rules_2024") in rel


def test_relations_read_correctly_from_both_ends():
    fwd = related_instruments(["biological_diversity_amendment_act_2023"])
    assert any(r["relation"] == "amends" and r["doc_id"] == "biological_diversity_act_2002" for r in fwd)


def test_jurisdiction_filter_keeps_the_answer_sets_apart():
    india = related_instruments(["biological_diversity_act_2002"], "india")
    assert india and all(r["jurisdiction"] == "india" for r in india)
    intl = related_instruments(["biological_diversity_act_2002"], "international")
    assert [r["doc_id"] for r in intl] == ["cbd_convention"]


def test_already_cited_instruments_are_not_repeated_as_related():
    both = related_instruments(["biological_diversity_act_2002", "biological_diversity_amendment_act_2023"])
    assert all(r["doc_id"] not in ("biological_diversity_act_2002",
                                   "biological_diversity_amendment_act_2023") for r in both)


def test_unknown_or_empty_input_yields_nothing():
    assert related_instruments([]) == []
    assert related_instruments(["not_a_doc"]) == []
    assert section_references("not_a_chunk") == []


def test_section_reference_to_another_statute_is_excluded():
    # Same exclusion enrichment.py applies: "section 2 of the Income-tax Act"
    # is not this Act's section 2.
    chunk = {"text": "as defined in section 2 of the Income-tax Act, 1961 and section 3 hereof",
             "section_number": "9"}
    refs = _references(chunk, {"2": "Definitions", "3": "Approval"})
    assert [r["section"] for r in refs] == ["3"]


def test_self_reference_and_unknown_sections_are_ignored():
    chunk = {"text": "subject to section 9 and section 99", "section_number": "9"}
    assert _references(chunk, {"9": "This one", "4": "Other"}) == []


def test_penalty_clause_resolves_to_the_provisions_it_enforces():
    refs = {r["section"] for r in section_references("biological_diversity_act_2002::sec-55")}
    assert {"3", "4", "6"} <= refs


def test_graph_stats_are_consistent():
    stats = graph_stats()
    assert stats["instruments"] == len(DOC_AUTHORITY)
    assert stats["instrument_relations"] == len(INSTRUMENT_RELATIONS)
    assert stats["section_references"] >= stats["provisions_with_references"] > 0


def test_amending_act_references_resolve_to_the_act_it_amends():
    # Found live: the 2023 Amendment's s.38 rewrites the 2002 Act's s.55, and
    # its "section 3 / section 7" mean the 2002 Act's sections. Resolving
    # them against the Amendment's own clauses gave "In section 2 of the
    # principal Act" as a heading.
    from knowledge_graph import _section_graph
    amending = {k: v for k, v in _section_graph().items()
                if k.startswith("biological_diversity_amendment_act_2023::")}
    assert amending, "expected the amending Act to have resolved references"
    for refs in amending.values():
        for r in refs:
            assert r["doc_id"] == "biological_diversity_act_2002"
            assert not r["heading"].lower().startswith("in section")

