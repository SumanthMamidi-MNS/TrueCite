from confidence_gate import CONFIDENCE_THRESHOLD
from escalation import (
    ESCALATION_GUIDANCE,
    HIGH,
    LOW,
    MODERATE,
    STANDING_DISCLAIMER,
    assess,
    confidence_label,
)


def test_confidence_label_tracks_the_gate_the_pipeline_already_uses():
    assert confidence_label(0.40) == HIGH
    assert confidence_label(0.80) == MODERATE
    assert confidence_label(CONFIDENCE_THRESHOLD + 0.01) == LOW


def test_no_evidence_is_low_confidence_not_an_error():
    assert confidence_label(None) == LOW


def test_refusal_always_offers_a_human():
    r = assess(refused=True, best_distance=None)
    assert r["escalate"]
    assert any("could not support" in x for x in r["reasons"])
    assert r["guidance"] is ESCALATION_GUIDANCE


def test_rejected_claims_trigger_escalation_and_are_counted_honestly():
    r = assess(best_distance=0.5, rejected_claims=2)
    assert r["escalate"]
    assert any("2 drafted claims failed verification" in x for x in r["reasons"])
    one = assess(best_distance=0.5, rejected_claims=1)
    assert any("1 drafted claim failed verification" in x for x in one["reasons"])


def test_conflicting_authority_triggers_escalation():
    r = assess(best_distance=0.5, conflicting_authority=True)
    assert r["escalate"]
    assert any("disagree" in x for x in r["reasons"])


def test_out_of_coverage_regime_triggers_escalation_and_names_the_regime():
    r = assess(best_distance=0.5, out_of_coverage_regimes=["drug-regulatory"])
    assert r["escalate"]
    assert any("drug-regulatory" in x for x in r["reasons"])


def test_unsourced_category_triggers_escalation():
    r = assess(best_distance=0.5, unsourced_category=True)
    assert r["escalate"]


def test_a_clean_high_confidence_answer_does_not_nag():
    # Offering a human on every answer would make the offer meaningless.
    r = assess(best_distance=0.40)
    assert not r["escalate"]
    assert r["reasons"] == []
    assert r["guidance"] is None
    assert r["confidence"] == HIGH


def test_moderate_confidence_alone_is_enough_to_offer_a_human():
    # Deliberately generous: this tool's measured failure mode is
    # over-refusal, so a needless offer costs a moment and a missing one can
    # cost a user acting on a partial answer.
    r = assess(best_distance=0.80)
    assert r["escalate"]
    assert r["confidence"] == MODERATE


def test_escalation_guidance_names_real_bodies_with_destinations():
    for c in ESCALATION_GUIDANCE["contacts"]:
        assert c["who"] and c["when"] and c["where"]
        assert c["where"].startswith("http")


def test_standing_disclaimer_says_information_not_advice():
    assert "not legal advice" in STANDING_DISCLAIMER
    assert "Verify" in STANDING_DISCLAIMER
