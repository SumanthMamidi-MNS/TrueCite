"""Unit tests for generate.py's selection/gating logic, with retrieval mocked
out (no live embedding model or Ollama server needed to run the suite).

End-to-end behavior against the real pipeline was verified manually and is
recorded in docs/decisions.md / docs/phases.md Phase 5.
"""
from unittest.mock import patch

from generate import _select_grounded_hits


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
