"""Unit tests for generate.py's selection/gating logic, with retrieval mocked
out (no live embedding model or Ollama server needed to run the suite).

End-to-end behavior against the real pipeline was verified manually and is
recorded in docs/decisions.md / docs/phases.md Phase 5.
"""
from unittest.mock import MagicMock, patch

import pytest

from generate import _condense_followup, _select_grounded_hits, answer_query_streaming


def _mock_response(response_json_str: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": response_json_str}
    mock.raise_for_status.return_value = None
    return mock


def _hit(chunk_id, doc_id, distance=0.5, section_number=None):
    return {
        "chunk_id": chunk_id,
        "distance": distance,
        "text": f"text of {chunk_id}",
        "metadata": {"doc_id": doc_id, "section_number": section_number or ""},
    }


def test_confidence_gate_refusal_short_circuits_before_hybrid_call():
    # Every vector hit is over threshold -> must refuse without even calling
    # hybrid retrieval (it would be wasted work on an already-refused query).
    bad_hits = [_hit("a", "patents_act_1970", distance=1.2)]
    with patch("generate.retrieve_vector", return_value=bad_hits) as mock_vec, \
         patch("generate.retrieve_hybrid") as mock_hybrid:
        result = _select_grounded_hits("irrelevant query", top_k=5)
    assert result == []
    mock_vec.assert_called_once()
    mock_hybrid.assert_not_called()


def test_authority_sort_does_not_evict_a_relevant_chunk_from_top_k():
    # Regression test for a real bug: sorting the WHOLE candidate pool by
    # authority before truncating to top_k let several lower-relevance,
    # higher-authority-tier chunks push an actually on-point chunk out
    # entirely. "informational_relevant" is the best hybrid match (rank 0)
    # but from the lowest authority tier; it must survive into the final
    # top_k even though 4 other confident, higher-authority chunks exist.
    vector_hits = [
        _hit("informational_relevant", "pib_faq_patents_traditional_ayurvedic_medicine_2013", 0.50),
        _hit("guideline_1", "ipo_ayush_examination_guidelines_2025", 0.60),
        _hit("guideline_2", "ipo_ayush_examination_guidelines_2025", 0.62),
        _hit("act_1", "patents_act_1970", 0.65),
        _hit("act_2", "patents_act_1970", 0.68),
        _hit("act_3", "patents_act_1970", 0.70),
    ]
    # hybrid ranks the truly relevant chunk first, same as vector did
    hybrid_hits = vector_hits

    with patch("generate.retrieve_vector", return_value=vector_hits), \
         patch("generate.retrieve_hybrid", return_value=hybrid_hits):
        result = _select_grounded_hits("some query", top_k=5)

    result_ids = [h["chunk_id"] for h in result]
    assert "informational_relevant" in result_ids, (
        f"the most relevant chunk was evicted by authority sorting: {result_ids}"
    )


def test_authority_ordering_still_applies_within_the_selected_top_k():
    # Within the already-selected top_k, higher-authority sources should
    # still come first (this is the actual point of Layer 3 ordering) —
    # just not at the cost of dropping a more relevant chunk entirely.
    vector_hits = [
        _hit("informational_1", "pib_faq_patents_traditional_ayurvedic_medicine_2013", 0.50),
        _hit("act_1", "patents_act_1970", 0.55),
    ]
    with patch("generate.retrieve_vector", return_value=vector_hits), \
         patch("generate.retrieve_hybrid", return_value=vector_hits):
        result = _select_grounded_hits("some query", top_k=5)

    result_ids = [h["chunk_id"] for h in result]
    assert result_ids.index("act_1") < result_ids.index("informational_1")


def test_condense_followup_rewrites_using_history():
    history = [{"q": "Can traditional knowledge be patented in India?", "a": "No, per §3(p)."}]
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"standalone_question": "Can traditional knowledge be patented in India for Unani medicine specifically?"}'
    )) as mock_post:
        result = _condense_followup("What about for Unani specifically?", history)
    assert result == "Can traditional knowledge be patented in India for Unani medicine specifically?"
    mock_post.assert_called_once()


def test_condense_followup_raises_on_malformed_response_instead_of_defaulting():
    # The caller (answer_query_streaming) is responsible for failing open to
    # the original query — this function itself must not silently invent a
    # fallback, for the same fail-closed reason verification.py raises.
    history = [{"q": "earlier question", "a": "earlier answer"}]
    with patch("llm_client.requests.post", return_value=_mock_response("not json at all")):
        with pytest.raises(Exception):
            _condense_followup("a follow-up", history)


def test_streaming_falls_back_to_original_query_when_condense_fails():
    # A broken condense call must not sink the whole answer — it should fall
    # back to treating the question as standalone rather than erroring out.
    history = [{"q": "earlier question", "a": "earlier answer"}]
    bad_hits = [_hit("a", "patents_act_1970", distance=1.2)]
    from generate import answer_query_streaming

    with patch("llm_client.requests.post", return_value=_mock_response("not json at all")), \
         patch("generate.retrieve_vector", return_value=bad_hits) as mock_vec:
        events = list(answer_query_streaming("a follow-up question", history=history))

    condense_done = next(e for e in events if e.get("stage") == "condense" and e["status"] == "done")
    assert condense_done["meta"]["standalone_question"] == "a follow-up question"
    assert condense_done["meta"]["rewritten"] is False
    mock_vec.assert_called_once_with("a follow-up question", top_k=40)


def _verified_verdict():
    return {"supported": True, "reasoning": "supported", "votes": [True, True, True]}


# ───────── Stage 3 (relevance filter) wiring ─────────

def test_relevance_filter_reindexes_correctly_for_downstream_claim_lookup():
    # The real bug risk this stage introduces: if the passage numbers
    # generation sees don't match the filtered `hits` list exactly, a claim
    # citing "source: 1" would resolve to the wrong chunk after filtering.
    hits = [
        _hit("a", "patents_act_1970"),
        _hit("b", "patents_act_1970"),
        _hit("c", "patents_act_1970"),
        _hit("d", "patents_act_1970"),
    ]
    relevance_verdicts = [
        {"index": 1, "relevant": False, "reason": "off topic"},
        {"index": 2, "relevant": True, "reason": ""},
        {"index": 3, "relevant": True, "reason": ""},
        {"index": 4, "relevant": True, "reason": ""},
    ]
    draft_claims = [{"text": "a claim", "source": 1}]  # post-filter passage 1 == original "b"

    with patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", return_value=relevance_verdicts), \
         patch("generate._generate_draft_claims", return_value=draft_claims), \
         patch("generate.verify_claim", return_value=_verified_verdict()):
        result = next(
            e["result"] for e in answer_query_streaming("q", relevance_filter=True, coverage_check=False)
            if e["type"] == "complete"
        )
    assert len(result["claims"]) == 1
    assert result["claims"][0]["chunk_id"] == "b"


def test_relevance_done_event_precedes_sources_event():
    hits = [_hit(str(i), "patents_act_1970") for i in range(1, 5)]
    verdicts = [{"index": i, "relevant": True, "reason": ""} for i in range(1, 5)]
    with patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", return_value=verdicts), \
         patch("generate._generate_draft_claims", return_value=[]):
        events = list(answer_query_streaming("q", relevance_filter=True, coverage_check=False))
    relevance_done_idx = next(
        i for i, e in enumerate(events) if e.get("stage") == "relevance" and e["status"] == "done"
    )
    sources_idx = next(i for i, e in enumerate(events) if e["type"] == "sources")
    assert relevance_done_idx < sources_idx


def test_relevance_failure_fails_open_keeping_all_hits():
    hits = [_hit(str(i), "patents_act_1970") for i in range(1, 5)]
    with patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", side_effect=ValueError("boom")), \
         patch("generate._generate_draft_claims", return_value=[]) as mock_draft:
        events = list(answer_query_streaming("q", relevance_filter=True, coverage_check=False))
    relevance_done = next(e for e in events if e.get("stage") == "relevance" and e["status"] == "done")
    assert relevance_done["meta"]["failed_open"] is True
    assert relevance_done["meta"]["kept"] == 4
    passed_hits = mock_draft.call_args.args[1]
    assert len(passed_hits) == 4


def test_relevance_all_irrelevant_still_keeps_min_keep_floor():
    # Relevance must never be able to cause a refusal on its own — a bad
    # batch of verdicts can narrow generation's input but never starve it.
    hits = [_hit(str(i), "patents_act_1970") for i in range(1, 5)]
    verdicts = [{"index": i, "relevant": False, "reason": "off topic"} for i in range(1, 5)]
    with patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", return_value=verdicts), \
         patch("generate._generate_draft_claims", return_value=[]):
        events = list(answer_query_streaming("q", relevance_filter=True, coverage_check=False))
    sources_event = next(e for e in events if e["type"] == "sources")
    assert len(sources_event["sources"]) >= 3


# ───────── Stage 5 (coverage check) wiring ─────────

def test_coverage_failure_fails_open_answer_unchanged():
    hits = [_hit("a", "patents_act_1970")]
    draft_claims = [{"text": "a claim", "source": 1}]
    with patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", return_value=[{"index": 1, "relevant": True, "reason": ""}]), \
         patch("generate._generate_draft_claims", return_value=draft_claims), \
         patch("generate.verify_claim", return_value=_verified_verdict()), \
         patch("generate.assess_coverage", side_effect=ValueError("boom")):
        events = list(answer_query_streaming("q"))
    complete = next(e for e in events if e["type"] == "complete")
    assert complete["result"]["coverage"] is None
    assert "a claim" in complete["result"]["answer"]
    coverage_done = next(e for e in events if e.get("stage") == "coverage" and e["status"] == "done")
    assert coverage_done["meta"]["available"] is False


def test_coverage_verdict_never_changes_answer_claims_or_citations():
    hits = [_hit("a", "patents_act_1970")]
    draft_claims = [{"text": "a claim", "source": 1}]

    def run(addresses):
        with patch("generate.retrieve_vector", return_value=hits), \
             patch("generate.retrieve_hybrid", return_value=hits), \
             patch("generate.judge_relevance", return_value=[{"index": 1, "relevant": True, "reason": ""}]), \
             patch("generate._generate_draft_claims", return_value=draft_claims), \
             patch("generate.verify_claim", return_value=_verified_verdict()), \
             patch(
                 "generate.assess_coverage",
                 return_value={"addresses": addresses, "gap": "" if addresses else "missing something"},
             ):
            events = list(answer_query_streaming("q"))
        return next(e for e in events if e["type"] == "complete")["result"]

    result_true, result_false = run(True), run(False)
    assert result_true["answer"] == result_false["answer"]
    assert result_true["claims"] == result_false["claims"]
    assert result_true["citations"] == result_false["citations"]


def test_coverage_not_called_on_gate_refusal():
    bad_hits = [_hit("a", "patents_act_1970", distance=1.2)]
    with patch("generate.retrieve_vector", return_value=bad_hits), \
         patch("generate.assess_coverage") as mock_coverage:
        events = list(answer_query_streaming("q"))
    mock_coverage.assert_not_called()
    assert not any(e.get("stage") == "coverage" for e in events)


def test_coverage_not_called_on_verification_refusal():
    hits = [_hit("a", "patents_act_1970")]
    draft_claims = [{"text": "a claim", "source": 1}]
    with patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", return_value=[{"index": 1, "relevant": True, "reason": ""}]), \
         patch("generate._generate_draft_claims", return_value=draft_claims), \
         patch("generate.verify_claim", return_value={"supported": False, "reasoning": "no", "votes": [False]}), \
         patch("generate.assess_coverage") as mock_coverage:
        events = list(answer_query_streaming("q"))
    mock_coverage.assert_not_called()


def test_coverage_assessed_against_condensed_question_when_history_present():
    history = [{"q": "earlier q", "a": "earlier a"}]
    hits = [_hit("a", "patents_act_1970")]
    draft_claims = [{"text": "a claim", "source": 1}]
    with patch("generate._condense_followup", return_value="the condensed standalone question"), \
         patch("generate.retrieve_vector", return_value=hits), \
         patch("generate.retrieve_hybrid", return_value=hits), \
         patch("generate.judge_relevance", return_value=[{"index": 1, "relevant": True, "reason": ""}]), \
         patch("generate._generate_draft_claims", return_value=draft_claims), \
         patch("generate.verify_claim", return_value=_verified_verdict()), \
         patch("generate.assess_coverage", return_value={"addresses": True, "gap": ""}) as mock_coverage:
        list(answer_query_streaming("a follow-up", history=history))
    mock_coverage.assert_called_once()
    assert mock_coverage.call_args.args[0] == "the condensed standalone question"
