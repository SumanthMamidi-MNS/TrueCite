import pytest

from classification import (
    AYURVEDA_AAHARA,
    CATEGORY_LABELS,
    CATEGORY_PROBES,
    CLASSICAL,
    COSMETIC,
    NEW_DRUG,
    PHYTOPHARMACEUTICAL,
    PROPRIETARY,
    classify,
    next_question,
)


def test_cosmetic_is_decided_after_one_question():
    # "Minimum clarifying questions" is the requirement, not a fixed
    # questionnaire — a cosmetic never needs the medicine-specific branch.
    answers = {"intended_use": "cosmetic"}
    assert classify(answers) == COSMETIC
    assert next_question(answers) is None


def test_food_is_decided_after_one_question():
    assert classify({"intended_use": "food"}) == AYURVEDA_AAHARA
    assert next_question({"intended_use": "food"}) is None


def test_classical_needs_exactly_two_questions():
    answers = {"intended_use": "medicine"}
    q = next_question(answers)
    assert q["key"] == "from_authoritative_text"
    answers["from_authoritative_text"] = "yes"
    assert classify(answers) == CLASSICAL
    assert next_question(answers) is None


def test_proprietary_branch():
    answers = {"intended_use": "medicine", "from_authoritative_text": "no",
               "ingredients_only_from_texts": "yes"}
    assert classify(answers) == PROPRIETARY


def test_phytopharmaceutical_and_new_drug_are_separated_by_the_last_question():
    base = {"intended_use": "medicine", "from_authoritative_text": "no",
            "ingredients_only_from_texts": "no"}
    assert classify({**base, "purified_extract": "yes"}) == PHYTOPHARMACEUTICAL
    assert classify({**base, "purified_extract": "no"}) == NEW_DRUG


def test_incomplete_answers_return_none_not_a_guess():
    # The whole point: an under-specified product gets another question, never
    # a category it might not be.
    assert classify({}) is None
    assert classify({"intended_use": "medicine"}) is None
    assert classify({"intended_use": "medicine", "from_authoritative_text": "no"}) is None


def test_question_order_skips_branches_that_do_not_apply():
    # A food must never be asked the First-Schedule question.
    answers = {"intended_use": "food"}
    assert next_question(answers) is None
    medicine = {"intended_use": "medicine"}
    assert next_question(medicine)["key"] == "from_authoritative_text"


def test_every_category_has_a_label_and_a_retrieval_probe():
    for cat in (CLASSICAL, PROPRIETARY, NEW_DRUG, PHYTOPHARMACEUTICAL,
                AYURVEDA_AAHARA, COSMETIC):
        assert CATEGORY_LABELS[cat]
        assert CATEGORY_PROBES[cat]


def test_unknown_category_raises_rather_than_guessing():
    from classification import category_guidance
    with pytest.raises(ValueError, match="unknown category"):
        category_guidance("not_a_category")


def test_every_question_exposes_its_options_without_internal_gating():
    # next_question is what the UI renders; the asked_when callable is an
    # implementation detail and must not leak into that payload.
    q = next_question({"intended_use": "medicine"})
    assert "asked_when" not in q
    assert q["options"] and q["question"]


def test_categories_whose_defining_instrument_is_absent_abstain_structurally():
    # A distance gate cannot tell a definition from a passing mention: the
    # cosmetic probe retrieved the Biological Diversity Act at 0.831, inside
    # the 0.90 gate, purely because that Act uses the word. Treating it as
    # grounded would produce a confident answer about cosmetics regulation
    # sourced from a biodiversity statute.
    from classification import UNSOURCED_CATEGORIES, category_guidance
    for cat in (NEW_DRUG, PHYTOPHARMACEUTICAL, COSMETIC):
        assert cat in UNSOURCED_CATEGORIES
        g = category_guidance(cat)
        assert g["grounded"] is False
        assert g["passages"] == []
        assert "not in the corpus" in g["abstention"]
        # names the instrument the user should go read instead
        assert "Drugs and Cosmetics" in g["abstention"]


def test_unsourced_check_runs_before_retrieval():
    # Structural, not threshold-dependent: it must hold even if retrieval
    # would have returned something inside the gate.
    from unittest.mock import patch
    from classification import category_guidance
    with patch("classification.retrieve_hybrid") as mock:
        g = category_guidance(COSMETIC)
    mock.assert_not_called()
    assert g["grounded"] is False
