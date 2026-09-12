from confidence_gate import CONFIDENCE_THRESHOLD, filter_confident_hits, passes_confidence_gate


def test_passes_when_best_hit_clears_threshold():
    hits = [{"chunk_id": "a", "distance": 0.60}, {"chunk_id": "b", "distance": 0.95}]
    assert passes_confidence_gate(hits) is True


def test_fails_when_no_hit_clears_threshold():
    hits = [{"chunk_id": "a", "distance": 0.99}, {"chunk_id": "b", "distance": 1.20}]
    assert passes_confidence_gate(hits) is False


def test_fails_on_empty_results():
    assert passes_confidence_gate([]) is False


def test_filter_keeps_only_confident_hits():
    hits = [
        {"chunk_id": "a", "distance": 0.50},
        {"chunk_id": "b", "distance": 0.89},
        {"chunk_id": "c", "distance": 0.91},
        {"chunk_id": "d", "distance": 1.10},
    ]
    kept = filter_confident_hits(hits)
    assert [h["chunk_id"] for h in kept] == ["a", "b"]


def test_threshold_is_documented_and_positive():
    assert 0 < CONFIDENCE_THRESHOLD < 2  # sanity: cosine/L2-on-unit-vectors range
