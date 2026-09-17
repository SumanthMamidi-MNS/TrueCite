"""Unit tests for run_verification_eval.py's aggregation/decision logic, with
llm_client.complete mocked out — no real Ollama calls, and no dependence on
the model's actual (non-deterministic) verdicts. What each case's expected
label *should* be was checked against real chunk text separately (see the
module docstring in src/run_verification_eval.py); these tests only check
that run_battery/decide count correctly given known verdicts.
"""
import json
from unittest.mock import patch

from run_verification_eval import CASES, SEED_BASES, decide, run_battery


def _claim_for(label: str) -> str:
    return next(claim for lbl, _expected, claim, _chunk_id in CASES if lbl == label)


def test_totals_arithmetic_when_everything_is_supported():
    # Every case, every seed base, "supported": true — true_accepts and
    # false_accepts should both hit their totals (7 true cases / 10 false
    # cases as of the 2026-09-16 spelling-variant amendment — T7, F10 — times
    # 3 seed bases each).
    with patch(
        "llm_client.complete",
        return_value=json.dumps({"reasoning": "mocked", "supported": True}),
    ):
        summary = run_battery("current")

    assert summary["true_total"] == 21
    assert summary["false_total"] == 30
    assert summary["true_accepts"] == 21
    assert summary["false_accepts"] == 30


def test_totals_arithmetic_when_nothing_is_supported():
    with patch(
        "llm_client.complete",
        return_value=json.dumps({"reasoning": "mocked", "supported": False}),
    ):
        summary = run_battery("current")

    assert summary["true_accepts"] == 0
    assert summary["false_accepts"] == 0


def test_false_accept_counting_isolates_the_offending_case():
    # Only F1's claim text triggers "supported": true; every other case
    # (true and false alike) is rejected. false_accepts must count only F1's
    # 3 occurrences (one per seed base), and false_accept_cases must name
    # exactly F1 — not F1's count bleeding into true_accepts or vice versa.
    f1_claim = _claim_for("F1")

    def fake_complete(prompt, **kwargs):
        supported = f1_claim in prompt
        return json.dumps({"reasoning": "mocked", "supported": supported})

    with patch("llm_client.complete", side_effect=fake_complete):
        summary = run_battery("current")

    assert summary["false_accepts"] == 3
    assert summary["false_accept_cases"] == ["F1"]
    assert summary["true_accepts"] == 0


def test_true_accepts_total_sums_across_all_seed_bases_not_just_one():
    # T1 is only ever "supported": true when the vote's seed belongs to the
    # FIRST seed base — confirms run_battery sums across all three seed
    # bases (must land on 1, not 3 or 0), not just the last one run.
    t1_claim = _claim_for("T1")
    first_base_seeds = set(SEED_BASES[0])

    def fake_complete(prompt, seed=None, **kwargs):
        supported = (t1_claim in prompt) and (seed in first_base_seeds)
        return json.dumps({"reasoning": "mocked", "supported": supported})

    with patch("llm_client.complete", side_effect=fake_complete):
        summary = run_battery("current")

    assert summary["true_accepts"] == 1
    assert summary["false_accepts"] == 0


def test_a_single_false_accept_at_one_seed_base_triggers_hard_reject():
    baseline = {"true_accepts": 10}
    candidate = {
        "true_accepts": 15,
        "false_accepts": 1,
        "false_accept_cases": ["F3"],
    }
    result = decide(baseline, candidate)

    assert result["hard_reject"] is True
    assert result["accept"] is False  # even though true_accepts strictly improved


def test_accept_requires_no_false_accepts_and_strict_true_accept_improvement():
    baseline = {"true_accepts": 10}
    candidate_ok = {"true_accepts": 12, "false_accepts": 0, "false_accept_cases": []}
    candidate_tied = {"true_accepts": 10, "false_accepts": 0, "false_accept_cases": []}

    assert decide(baseline, candidate_ok)["accept"] is True
    assert decide(baseline, candidate_tied)["accept"] is False  # not strictly greater
