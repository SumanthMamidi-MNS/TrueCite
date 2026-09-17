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


# --- W2: seeded sampling, one distinct seed per vote ---------------------


def test_issues_exactly_len_verification_seeds_calls_with_distinct_seeds():
    from verification import VERIFICATION_SEEDS

    responses = [
        _mock_response('{"reasoning": "ok", "supported": true}')
        for _ in VERIFICATION_SEEDS
    ]
    with patch("llm_client.requests.post", side_effect=responses) as mock_post:
        verify_claim("some claim", "some passage")

    assert mock_post.call_count == len(VERIFICATION_SEEDS)
    seeds_used = [call.kwargs["json"]["options"]["seed"] for call in mock_post.call_args_list]
    assert seeds_used == list(VERIFICATION_SEEDS)
    assert len(set(seeds_used)) == len(VERIFICATION_SEEDS)


def test_votes_use_verification_temperature_not_zero():
    # Not 0.0 — see verification.py's VERIFICATION_TEMPERATURE comment: a
    # greedy (temperature=0) vote would make all 3 calls identical, silently
    # collapsing the majority vote this function exists to run.
    from verification import VERIFICATION_TEMPERATURE

    responses = [_mock_response('{"reasoning": "ok", "supported": true}') for _ in range(3)]
    with patch("llm_client.requests.post", side_effect=responses) as mock_post:
        verify_claim("some claim", "some passage")

    for call in mock_post.call_args_list:
        assert call.kwargs["json"]["options"]["temperature"] == VERIFICATION_TEMPERATURE


def test_majority_logic_unchanged_true_false_true_is_supported():
    responses = [
        _mock_response('{"reasoning": "a", "supported": true}'),
        _mock_response('{"reasoning": "b", "supported": false}'),
        _mock_response('{"reasoning": "c", "supported": true}'),
    ]
    with patch("llm_client.requests.post", side_effect=responses):
        result = verify_claim("some claim", "some passage")
    assert result["supported"] is True
    assert result["votes"] == [True, False, True]


def test_majority_logic_unchanged_false_true_false_is_not_supported():
    responses = [
        _mock_response('{"reasoning": "a", "supported": false}'),
        _mock_response('{"reasoning": "b", "supported": true}'),
        _mock_response('{"reasoning": "c", "supported": false}'),
    ]
    with patch("llm_client.requests.post", side_effect=responses):
        result = verify_claim("some claim", "some passage")
    assert result["supported"] is False
    assert result["votes"] == [False, True, False]


# --- prompt strictness sentences must survive whichever prompt ships ------


def test_active_prompt_retains_original_strictness_sentences():
    # Whichever prompt verify_claim is actually pointed at (the original, or
    # the 2026-09-16 precision revision — see verification.py and
    # docs/decisions.md for which one won the eval battery), it must still
    # contain the two sentences this project's core safety property rests
    # on: strictness about facts genuinely absent, and the "as prescribed"
    # guard against a passage that only gestures at a figure without stating
    # it. The precision change was additive (inserted a new sentence after
    # the "as prescribed" one) and must never have removed either.
    from verification import VERIFICATION_PROMPT_TEMPLATE

    assert "Be strict about facts genuinely absent" in VERIFICATION_PROMPT_TEMPLATE
    assert (
        'a passage that only says something is "as prescribed" or "as may be determined" elsewhere does NOT support a claim that states a specific figure or detail'
        in VERIFICATION_PROMPT_TEMPLATE
    )


def test_a_failing_vote_is_skipped_not_counted():
    responses = [
        _mock_response('{"reasoning": "a", "supported": true}'),
        _mock_response("not json at all"),  # skipped, not counted as a vote
        _mock_response('{"reasoning": "c", "supported": true}'),
    ]
    with patch("llm_client.requests.post", side_effect=responses) as mock_post:
        result = verify_claim("some claim", "some passage")
    assert mock_post.call_count == 3
    assert result["supported"] is True
    assert result["votes"] == [True, True]


# --- ProviderRateLimited must propagate, never be swallowed per-vote -------
#
# Contrast with test_raises_when_every_vote_fails/test_a_failing_vote_is_
# skipped_not_counted above: an ordinary parse failure on a vote is
# tolerated (skipped, or falls back to "all votes failed" -> ValueError,
# fail-closed). A rate-limited provider must NOT go through that same broad
# tolerance — if it did, every vote would fail silently, verify_claim would
# raise a generic ValueError, and generate.py's caller would drop the claim
# as ordinary "verification unavailable", eventually producing the Layer 2
# grounding refusal once every claim was dropped that way. That's exactly
# the infra-vs-grounding confusion ProviderRateLimited exists to prevent, so
# it must propagate out of verify_claim immediately, not be retried per-vote
# or absorbed into the "all votes failed" path.


def test_provider_rate_limited_propagates_and_stops_voting_immediately():
    from llm_client import ProviderRateLimited

    with patch(
        "verification._verify_claim_once",
        side_effect=[{"reasoning": "ok", "supported": True}, ProviderRateLimited("quota exceeded")],
    ) as mock_once:
        with pytest.raises(ProviderRateLimited):
            verify_claim("some claim", "some passage", votes=3)
    # Stopped after the 2nd vote raised — the 3rd vote was never attempted.
    assert mock_once.call_count == 2


def test_provider_rate_limited_is_not_downgraded_to_all_votes_failed():
    from llm_client import ProviderRateLimited

    with patch("verification._verify_claim_once", side_effect=ProviderRateLimited("quota exceeded")):
        with pytest.raises(ProviderRateLimited):
            verify_claim("some claim", "some passage", votes=3)
