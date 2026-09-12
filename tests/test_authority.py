from authority import DOC_AUTHORITY, AUTH_LEVEL_ACT, authority_rank, get_authority

EXPECTED_DOC_IDS = {
    "patents_act_1970",
    "ipo_tk_biological_material_guidelines_2012",
    "pib_faq_patents_traditional_ayurvedic_medicine_2013",
    "ipo_ayush_examination_guidelines_2025",
    "wipo_documenting_tk_toolkit",
}


def test_covers_every_corpus_doc_id():
    assert set(DOC_AUTHORITY.keys()) == EXPECTED_DOC_IDS


def test_every_entry_has_a_resolvable_authority_rank():
    for doc_id, meta in DOC_AUTHORITY.items():
        assert authority_rank(meta["authority_level"]) > 0, doc_id


def test_act_outranks_guideline_outranks_informational():
    act_rank = authority_rank(get_authority("patents_act_1970")["authority_level"])
    guideline_rank = authority_rank(
        get_authority("ipo_tk_biological_material_guidelines_2012")["authority_level"]
    )
    informational_rank = authority_rank(
        get_authority("pib_faq_patents_traditional_ayurvedic_medicine_2013")["authority_level"]
    )
    assert act_rank > guideline_rank > informational_rank


def test_patents_act_is_the_act_level():
    assert get_authority("patents_act_1970")["authority_level"] == AUTH_LEVEL_ACT


def test_every_entry_has_an_effective_date_and_note():
    for doc_id, meta in DOC_AUTHORITY.items():
        assert meta["effective_date"], doc_id
        assert meta["date_note"], f"{doc_id} should document where its date came from"


def test_every_entry_has_a_short_citation_name():
    for doc_id, meta in DOC_AUTHORITY.items():
        assert meta["short_name"], doc_id
        assert len(meta["short_name"]) < 60, f"{doc_id}'s short_name should actually be short"
