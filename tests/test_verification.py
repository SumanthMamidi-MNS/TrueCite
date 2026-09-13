"""Unit tests for verification.py's parsing/validation logic, with the Ollama
HTTP call mocked out (no live model server needed to run the suite).

Live behavior against the real model was verified manually and is recorded
in docs/decisions.md — 3/3 hand-checked cases correct, including the exact
"topically relevant but doesn't support this specific figure" case Layer 1
can't catch on its own (a claimed patent-filing-fee amount, against a
passage that only says fees are "as may be prescribed").
"""
from unittest.mock import MagicMock, patch

import pytest

from verification import verify_claim


def _mock_response(response_json_str: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": response_json_str}
    mock.raise_for_status.return_value = None
    return mock


def test_parses_supported_true():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"supported": true, "reasoning": "The passage directly states this."}'
    )):
        result = verify_claim("some claim", "some passage")
    assert result["supported"] is True
    assert "reasoning" in result


def test_parses_supported_false():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"supported": false, "reasoning": "The passage does not mention this."}'
    )):
        result = verify_claim("some claim", "some passage")
    assert result["supported"] is False


def test_raises_on_malformed_json_instead_of_defaulting():
    with patch("llm_client.requests.post", return_value=_mock_response("not json at all")):
        with pytest.raises(Exception):
            verify_claim("some claim", "some passage")


def test_raises_when_supported_field_missing_instead_of_defaulting():
    # A verification layer that fails open (assumes "supported" on a
    # malformed/incomplete response) defeats its own purpose.
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"reasoning": "forgot the verdict field"}'
    )):
        with pytest.raises(ValueError):
            verify_claim("some claim", "some passage")


def test_raises_when_supported_field_is_not_a_bool():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"supported": "yes", "reasoning": "wrong type"}'
    )):
        with pytest.raises(ValueError):
            verify_claim("some claim", "some passage")


def test_majority_vote_resolves_a_split_decision():
    # Directly reproduces what was observed live against the real model: 2
    # "supported" votes and 1 "not supported" vote on a claim that was
    # genuinely well-supported — majority must win, not the last call.
    responses = [
        _mock_response('{"reasoning": "clearly stated", "supported": true}'),
        _mock_response('{"reasoning": "clearly stated", "supported": true}'),
        _mock_response('{"reasoning": "missed the connection", "supported": false}'),
    ]
    with patch("llm_client.requests.post", side_effect=responses):
        result = verify_claim("some claim", "some passage", votes=3)
    assert result["supported"] is True
    assert result["votes"] == [True, True, False]


def test_majority_vote_reasoning_comes_from_an_agreeing_call():
    responses = [
        _mock_response('{"reasoning": "reason A", "supported": true}'),
        _mock_response('{"reasoning": "reason B", "supported": true}'),
        _mock_response('{"reasoning": "reason C", "supported": false}'),
    ]
    with patch("llm_client.requests.post", side_effect=responses):
        result = verify_claim("some claim", "some passage", votes=3)
    assert result["reasoning"] in ("reason A", "reason B")


def test_majority_vote_tolerates_one_failed_call():
    responses = [
        _mock_response('{"reasoning": "ok", "supported": true}'),
        _mock_response("not json at all"),  # this vote fails to parse
        _mock_response('{"reasoning": "ok", "supported": true}'),
    ]
    with patch("llm_client.requests.post", side_effect=responses):
        result = verify_claim("some claim", "some passage", votes=3)
    assert result["supported"] is True


def test_raises_when_every_vote_fails():
    responses = [_mock_response("not json") for _ in range(3)]
    with patch("llm_client.requests.post", side_effect=responses):
        with pytest.raises(ValueError):
            verify_claim("some claim", "some passage", votes=3)
