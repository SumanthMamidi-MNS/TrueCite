from authority import (
    AUTH_LEVEL_ACT,
    AUTH_LEVEL_RULES,
    AUTH_LEVEL_TREATY,
    DOC_AUTHORITY,
    JURISDICTION_INDIA,
    JURISDICTION_INTERNATIONAL,
    authority_rank,
    get_authority,
)

EXPECTED_DOC_IDS = {
    # original corpus (phases 1-9)
    "patents_act_1970",
    "ipo_tk_biological_material_guidelines_2012",
    "pib_faq_patents_traditional_ayurvedic_medicine_2013",
    "ipo_ayush_examination_guidelines_2025",
    "wipo_documenting_tk_toolkit",
    "biological_diversity_act_2002",
    "wipo_gratk_treaty_2024",
    # phase 10 — national IP regimes
    "trade_marks_act_1999",
    "geographical_indications_act_1999",
    "designs_act_2000",
    "copyright_act_1957",
    "plant_varieties_act_2001",
    # phase 10 — ABS
    "biological_diversity_amendment_act_2023",
    "biological_diversity_rules_2024",
    # phase 10 — food regime
    "fssai_ayurveda_aahara_regulations_2022",
    # phase 10 — international instruments
    "trips_agreement",
    "cbd_convention",
    "nagoya_protocol",
    "pct_treaty",
    "madrid_protocol",
}

VALID_REGIMES = {
    "patent", "trademark", "gi", "design", "copyright", "plant-variety",
    "trade-secret", "abs", "tk", "drug-regulatory", "food-cosmetic",
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


def test_act_outranks_rules_outranks_treaty():
    # Rules are binding subordinate legislation, so they sit under the Act
    # they are made under. A treaty sits under both for an Indian question:
    # India is dualist, so a treaty is not directly enforceable domestically
    # without implementing legislation.
    assert authority_rank(AUTH_LEVEL_ACT) > authority_rank(AUTH_LEVEL_RULES)
    assert authority_rank(AUTH_LEVEL_RULES) > authority_rank(AUTH_LEVEL_TREATY)


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


def test_every_entry_declares_a_jurisdiction():
    # The problem statement requires India and international answers be kept
    # visibly separate; that is impossible if a document's side is unknown.
    for doc_id, meta in DOC_AUTHORITY.items():
        assert meta["jurisdiction"] in (JURISDICTION_INDIA, JURISDICTION_INTERNATIONAL), doc_id


def test_every_entry_declares_at_least_one_known_regime():
    for doc_id, meta in DOC_AUTHORITY.items():
        assert meta["regimes"], doc_id
        unknown = set(meta["regimes"]) - VALID_REGIMES
        assert not unknown, f"{doc_id} declares unknown regime(s): {unknown}"


def test_every_entry_records_its_amendment_currency():
    # Several sourced Acts are as-originally-enacted with no amendments folded
    # in. Layer 3's job is to surface the CURRENT authoritative version, so a
    # stale text must announce itself rather than be cited as if current.
    for doc_id, meta in DOC_AUTHORITY.items():
        assert meta["amendment_currency"], doc_id


def test_known_stale_acts_say_so_explicitly():
    # Guards the specific trap: this copy of the Trade Marks Act still
    # describes the Appellate Board, abolished in 2021.
    for doc_id in ("trade_marks_act_1999", "designs_act_2000",
                   "geographical_indications_act_1999", "plant_varieties_act_2001"):
        assert "AS ENACTED" in get_authority(doc_id)["amendment_currency"], doc_id
    assert "CONSOLIDATED" in get_authority("copyright_act_1957")["amendment_currency"]
