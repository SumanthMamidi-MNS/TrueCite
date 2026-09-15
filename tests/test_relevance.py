"""Unit tests for relevance.py (pipeline Stage 3), LLM call mocked out.
See its module docstring for why this stage is non-blocking and fails open.
"""
from unittest.mock import MagicMock, patch

import pytest

from relevance import MIN_KEEP, apply_relevance, judge_relevance


def _mock_response(response_json_str: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": response_json_str}
    mock.raise_for_status.return_value = None
    return mock


def _hit(chunk_id: str) -> dict:
    return {"chunk_id": chunk_id, "text": f"text of {chunk_id}", "metadata": {"doc_id": chunk_id}}


def test_judge_relevance_parses_well_formed_verdicts():
    hits = [_hit("a"), _hit("b")]
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"verdicts": [{"index": 1, "relevant": true, "reason": "on point"}, '
        '{"index": 2, "relevant": false, "reason": "wrong document"}]}'
    )):
        verdicts = judge_relevance("some query", hits)
    assert verdicts[0] == {"index": 1, "relevant": True, "reason": "on point"}
    assert verdicts[1]["relevant"] is False


def test_judge_relevance_raises_on_malformed_json():
    with patch("llm_client.requests.post", return_value=_mock_response("not json at all")):
        with pytest.raises(Exception):
            judge_relevance("q", [_hit("a")])


def test_judge_relevance_raises_when_verdicts_dont_cover_every_passage():
    # A truncated response must not be read as "the missing ones are
    # irrelevant" — that would silently narrow the set based on a parsing
    # gap, not a real judgment.
    hits = [_hit("a"), _hit("b")]
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"verdicts": [{"index": 1, "relevant": true, "reason": "ok"}]}'
    )):
        with pytest.raises(ValueError):
            judge_relevance("q", hits)


def test_judge_relevance_raises_when_relevant_field_is_not_a_bool():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"verdicts": [{"index": 1, "relevant": "yes", "reason": "ok"}]}'
    )):
        with pytest.raises(ValueError):
            judge_relevance("q", [_hit("a")])


def test_apply_relevance_drops_irrelevant_and_preserves_order():
    hits = [_hit("a"), _hit("b"), _hit("c"), _hit("d")]
    verdicts = [
        {"index": 1, "relevant": True, "reason": ""},
        {"index": 2, "relevant": False, "reason": "off topic"},
        {"index": 3, "relevant": True, "reason": ""},
        {"index": 4, "relevant": False, "reason": "wrong document"},
    ]
    kept, dropped = apply_relevance(hits, verdicts, min_keep=1)
    assert [h["chunk_id"] for h in kept] == ["a", "c"]
    assert [d["chunk_id"] for d in dropped] == ["b", "d"]
    assert dropped[1]["reason"] == "wrong document"


def test_apply_relevance_enforces_min_keep_floor():
    hits = [_hit("a"), _hit("b"), _hit("c")]
    verdicts = [{"index": i, "relevant": False, "reason": "no"} for i in (1, 2, 3)]
    kept, dropped = apply_relevance(hits, verdicts, min_keep=2)
    assert len(kept) == 2
    assert [h["chunk_id"] for h in kept] == ["a", "b"]
    assert len(dropped) == 1


def test_apply_relevance_default_min_keep_matches_module_constant():
    hits = [_hit(str(i)) for i in range(10)]
    verdicts = [{"index": i, "relevant": False, "reason": ""} for i in range(1, 11)]
    kept, _ = apply_relevance(hits, verdicts)
    assert len(kept) == MIN_KEEP
