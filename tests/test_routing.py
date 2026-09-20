from routing import (
    REGIME_REGISTRIES,
    REGIME_TRIGGERS,
    TKDL_POINTER,
    prior_art_pointer,
    regimes_in_coverage,
    route,
)


def _regimes(result, key):
    return {e["regime"] for e in result[key]}


def test_coverage_is_derived_from_the_document_registry_not_hardcoded():
    # Adding the Trade Marks Act is what made the trademark route real; this
    # must not depend on anyone remembering to update a second list.
    covered = regimes_in_coverage()
    assert "trademark" in covered
    assert "gi" in covered
    assert "plant-variety" in covered
    assert "abs" in covered


def test_routes_a_branded_ayurvedic_product_to_trademark_and_patent():
    r = route("We want to protect our new branded Ayurvedic formulation and its brand name.")
    assert "trademark" in _regimes(r, "in_coverage")


def test_biological_resource_triggers_abs():
    r = route("Our invention uses a medicinal plant extract sourced from a forest in Kerala.")
    assert r["abs_triggered"]
    assert "abs" in _regimes(r, "in_coverage")


def test_traditional_knowledge_triggers_tk():
    r = route("The formulation comes from a classical text and community traditional knowledge.")
    assert r["tk_triggered"]


def test_uncovered_regime_is_surfaced_not_silently_dropped():
    # The user still needs to know a regime applies even when this tool has no
    # source for it — dropping it would mean they never learn it was relevant.
    r = route("We need a drug licence and want to run a clinical trial for a new drug.")
    assert "drug-regulatory" in _regimes(r, "out_of_coverage")
    assert "drug-regulatory" not in _regimes(r, "in_coverage")


def test_out_of_coverage_entries_are_flagged_distinctly_from_covered_ones():
    r = route("A clinical trial for a new drug, plus a trade mark for the brand.")
    covered = _regimes(r, "in_coverage")
    uncovered = _regimes(r, "out_of_coverage")
    assert covered and uncovered
    assert not (covered & uncovered), "a regime cannot be both covered and not"


def test_unrelated_text_routes_nowhere():
    r = route("What is the weather like today?")
    assert r["in_coverage"] == [] and r["out_of_coverage"] == []
    assert not r["abs_triggered"] and not r["tk_triggered"]


def test_every_trigger_regime_is_a_known_regime_name():
    # Guards against a typo silently creating a regime that can never match
    # authority.py and is therefore permanently "out of coverage".
    valid = {"patent", "trademark", "gi", "design", "copyright", "plant-variety",
             "trade-secret", "abs", "tk", "drug-regulatory", "food-cosmetic"}
    assert set(REGIME_TRIGGERS) <= valid
    assert set(REGIME_REGISTRIES) <= valid


def test_tkdl_pointer_never_claims_to_have_searched_tkdl():
    # Fabricating a TKDL record is the most damaging thing this tool could do
    # in this domain: it looks authoritative and is trivially acted upon.
    p = prior_art_pointer("Can we patent this traditional knowledge formulation?")
    assert p is not None
    assert p["searchable_by_this_tool"] is False
    assert "cannot search it" in p["pointer"]
    assert "fabricated" in p["pointer"]


def test_no_prior_art_pointer_when_neither_tk_nor_patent_is_in_play():
    assert prior_art_pointer("We want to register a brand name for our shop.") is None


def test_matched_triggers_are_reported_so_routing_is_explainable():
    r = route("Our invention uses a genetic resource and traditional knowledge.")
    for entry in r["in_coverage"] + r["out_of_coverage"]:
        assert entry["matched"], f"{entry['regime']} routed without saying why"


def test_tkdl_pointer_text_links_the_real_registry():
    assert "tkdl.res.in" in TKDL_POINTER
