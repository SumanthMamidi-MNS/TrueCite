"""Tests for run_phase6.py's multi-run machinery: seed propagation, the
per-question scoring formula, and the min/median/max aggregate.

None of this touches a real model. `_reseed` correctness is checked against
generate._generate_draft_claims and verification.verify_claim directly, with
llm_client.complete mocked to capture the seed(s) actually sent. `main`/
`run_many` correctness is checked with generate.answer_query mocked (patched
on run_phase6, where it's imported), so these stay fast and deterministic.
"""
from unittest.mock import patch

import generate
import run_phase6 as rp6
import verification


def test_reseed_generation_seed_is_read_at_call_time_not_captured_once():
    """generate.GENERATION_SEED is a bare module global read inside
    _generate_draft_claims (and _condense_followup) at call time, not
    snapshotted as a default argument value or at import time. If it were
    captured once, reassigning generate.GENERATION_SEED between runs (what
    _reseed does) would silently have no effect and every 'reseeded' run
    would send the same seed — making the multi-run numbers fake."""
    sent_seeds = []

    def fake_complete(prompt, timeout=120, temperature=0.0, seed=None):
        sent_seeds.append(seed)
        return '{"claims": []}'

    with patch("llm_client.complete", side_effect=fake_complete):
        generate.GENERATION_SEED = 111
        generate._generate_draft_claims("some query", [])
        generate.GENERATION_SEED = 222
        generate._generate_draft_claims("some query", [])

    assert sent_seeds == [111, 222]


def test_reseed_condense_followup_seed_is_read_at_call_time():
    sent_seeds = []

    def fake_complete(prompt, timeout=60, temperature=0.0, seed=None):
        sent_seeds.append(seed)
        return '{"standalone_question": "rewritten?"}'

    history = [{"q": "earlier question", "a": "earlier answer"}]
    with patch("llm_client.complete", side_effect=fake_complete):
        generate.GENERATION_SEED = 333
        generate._condense_followup("follow up", history)
        generate.GENERATION_SEED = 444
        generate._condense_followup("follow up", history)

    assert sent_seeds == [333, 444]


def test_reseed_verification_seeds_are_read_at_call_time_across_reseeds():
    """verify_claim's `votes` parameter defaults to len(VERIFICATION_SEEDS)
    evaluated once at function-definition time. That default value staying
    fixed at 3 is harmless (_reseed always produces a 3-tuple), but the loop
    body `VERIFICATION_SEEDS[:votes]` must still read the module global at
    CALL time so a reseed changes which seeds are actually sent — confirmed
    here across two differently-reseeded calls."""
    sent_seeds = []

    def fake_complete(prompt, timeout=120, temperature=0.3, seed=None):
        sent_seeds.append(seed)
        return '{"supported": true, "reasoning": "matches"}'

    with patch("llm_client.complete", side_effect=fake_complete):
        verification.VERIFICATION_SEEDS = (1, 2, 3)
        verification.verify_claim("some claim", "some passage")
        verification.VERIFICATION_SEEDS = (4, 5, 6)
        verification.verify_claim("some claim", "some passage")

    assert sent_seeds == [1, 2, 3, 4, 5, 6]


def _fake_answer_query(correct_queries, refused_queries=frozenset()):
    """A stand-in for generate.answer_query, deterministic in `query` alone.

    - refused_queries -> refused=True, no claims.
    - correct_queries (answerable) -> one claim citing the question's own
      first expected doc_id, sorted for determinism.
    - anything else answerable -> one claim citing a doc_id that is
      deliberately NOT in the expected set (wrong-citation case).
    """
    expected_by_query = dict(rp6.ANSWERABLE)

    def fake(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        if query in refused_queries:
            return {"refused": True, "answer": "I don't know.", "citations": [], "claims": []}
        expected = expected_by_query.get(query)
        if expected and query in correct_queries:
            doc_id = sorted(expected)[0]
        else:
            doc_id = "not-an-expected-doc-id"
        return {
            "refused": False,
            "answer": "some answer",
            "citations": ["[1]"],
            "claims": [{"doc_id": doc_id, "text": "x", "citation": "[x]"}],
        }

    return fake


def test_main_per_question_matches_its_own_got_it_right_definition(tmp_path):
    """run_many's aggregate reuses main()'s 'per_question' dict verbatim, so
    that dict must match main's own got_it_right = (not refused) AND (cited
    doc_ids intersect expected doc_ids) exactly — including when
    expected_doc_ids round-trips through the sorted list stored in results."""
    all_queries = [q for q, _ in rp6.ANSWERABLE]
    correct = set(all_queries[::2])
    refused = {all_queries[1]}
    fake = _fake_answer_query(correct, refused)

    with patch("run_phase6.answer_query", side_effect=fake):
        summary = rp6.main(results_path=tmp_path / "results.json")

    expected_by_query = dict(rp6.ANSWERABLE)
    for q in all_queries:
        r = fake(q)
        independently_computed = (not r["refused"]) and bool(
            {c["doc_id"] for c in r["claims"]} & expected_by_query[q]
        )
        assert summary["per_question"][q] == independently_computed, q

    # Sanity: the ones we deliberately made correct/refused/wrong all landed
    # where expected, so the assertion above isn't vacuously true.
    assert summary["per_question"][all_queries[0]] is True  # correct
    assert summary["per_question"][all_queries[1]] is False  # refused
    assert summary["per_question"][all_queries[3]] is False  # wrong citation (odd index -> not in `correct`)


def test_summarize_even_run_count_reports_true_median_not_upper_middle():
    # Old behavior: ordered[len//2] on [0, 12] -> index 1 -> 12 (the max,
    # mislabeled "median"). True median of two values is their average.
    assert rp6._summarize([12, 0])["median"] == 6
    assert rp6._summarize([0, 12])["median"] == 6


def test_summarize_odd_run_count_unchanged():
    assert rp6._summarize([3, 1, 2])["median"] == 2


def test_summarize_min_max_and_runs_preserved():
    s = rp6._summarize([5, 1, 3])
    assert s["min"] == 1
    assert s["max"] == 5
    assert s["runs"] == [5, 1, 3]


def test_cli_bare_invocation_defaults_relevance_filter_off():
    """The shipped pipeline (generate.answer_query) defaults relevance_filter
    to False. A bare `python run_phase6.py` must match that, or the eval
    silently measures a configuration nobody ships."""
    args = rp6._parse_args([])
    assert args.relevance_filter is False


def test_cli_relevance_filter_flag_opts_in():
    args = rp6._parse_args(["--relevance-filter"])
    assert args.relevance_filter is True


def test_cli_no_relevance_filter_flag_is_noop_alias_still_off():
    """--no-relevance-filter is accepted (old commands/docs still run) but
    does not itself turn anything on — the default is already off."""
    args = rp6._parse_args(["--no-relevance-filter"])
    assert args.relevance_filter is False


def test_cli_suffix_default_run_is_unsuffixed():
    assert rp6._suffix_for(False) == ""


def test_cli_suffix_opted_in_run_is_marked():
    assert rp6._suffix_for(True) == "_with_relevance_filter"


def test_main_default_relevance_filter_is_false_and_forwarded_to_answer_query(tmp_path):
    """main()'s own `relevance_filter` parameter must default False, matching
    generate.answer_query's default, and that value must actually reach
    answer_query — not just exist as a default nobody forwards."""
    seen = []

    def fake(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        seen.append(relevance_filter)
        return {"refused": True, "answer": "I don't know.", "citations": [], "claims": []}

    with patch("run_phase6.answer_query", side_effect=fake):
        rp6.main(results_path=tmp_path / "results.json")

    assert seen  # answer_query was actually called
    assert all(v is False for v in seen)


def test_main_relevance_filter_true_is_forwarded_to_answer_query(tmp_path):
    seen = []

    def fake(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        seen.append(relevance_filter)
        return {"refused": True, "answer": "I don't know.", "citations": [], "claims": []}

    with patch("run_phase6.answer_query", side_effect=fake):
        rp6.main(relevance_filter=True, results_path=tmp_path / "results.json")

    assert seen
    assert all(v is True for v in seen)


def test_run_many_aggregate_reports_true_median_across_two_runs(tmp_path, monkeypatch):
    """End-to-end through run_many with two runs whose citation_accuracy
    differ (12 vs 0), mocked at generate.answer_query so no model is called.
    Confirms _summarize's fix is actually wired into run_many's output, and
    that per-question stability counts runs passed, not something else."""
    monkeypatch.setattr(rp6, "RESULTS_PATH", tmp_path / "phase6_results.json")

    all_answerable = [q for q, _ in rp6.ANSWERABLE]
    n_per_run = len(rp6.ANSWERABLE) + len(rp6.UNANSWERABLE)
    calls = {"n": 0}

    def fake(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        run_idx = calls["n"] // n_per_run
        calls["n"] += 1
        if query in rp6.UNANSWERABLE:
            return {"refused": True, "answer": "I don't know.", "citations": [], "claims": []}
        expected = dict(rp6.ANSWERABLE)[query]
        # Run 0: every answerable question correct. Run 1: every one wrong.
        doc_id = sorted(expected)[0] if run_idx == 0 else "not-an-expected-doc-id"
        return {
            "refused": False,
            "answer": "some answer",
            "citations": ["[1]"],
            "claims": [{"doc_id": doc_id, "text": "x", "citation": "[x]"}],
        }

    with patch("run_phase6.answer_query", side_effect=fake):
        summary = rp6.run_many(runs=2, seed_base=1, relevance_filter=True, suffix="_unittest")

    n_answerable = len(rp6.ANSWERABLE)
    acc = summary["aggregate"]["citation_accuracy"]
    assert acc["runs"] == [n_answerable, 0]
    assert acc["min"] == 0
    assert acc["max"] == n_answerable
    assert acc["median"] == n_answerable / 2

    # Every answerable question passed exactly run 0, never run 1.
    for q in all_answerable:
        assert summary["per_question_stability"][q] == 1

    # Unanswerable questions were correctly refused both runs.
    correct_refusals = summary["aggregate"]["correct_refusals"]
    assert correct_refusals["runs"] == [len(rp6.UNANSWERABLE), len(rp6.UNANSWERABLE)]
