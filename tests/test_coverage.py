"""Unit tests for coverage.py (pipeline Stage 5), LLM call mocked out.
See its module docstring for why this stage is advisory-only and fails open.
"""
from unittest.mock import MagicMock, patch

import pytest

from coverage import assess_coverage


def _mock_response(response_json_str: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": response_json_str}
    mock.raise_for_status.return_value = None
    return mock


def test_parses_addresses_true():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"addresses": true, "gap": ""}'
    )):
        result = assess_coverage("some question", "some answer")
    assert result == {"addresses": True, "gap": ""}


def test_parses_addresses_false_with_gap():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"addresses": false, "gap": "does not mention the filing deadline"}'
    )):
        result = assess_coverage("some question", "some answer")
    assert result["addresses"] is False
    assert result["gap"] == "does not mention the filing deadline"


def test_raises_on_malformed_json():
    with patch("llm_client.requests.post", return_value=_mock_response("not json at all")):
        with pytest.raises(Exception):
            assess_coverage("q", "a")


def test_raises_when_addresses_field_missing():
    with patch("llm_client.requests.post", return_value=_mock_response('{"gap": ""}')):
        with pytest.raises(ValueError):
            assess_coverage("q", "a")


def test_raises_when_addresses_field_is_not_a_bool():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"addresses": "yes", "gap": ""}'
    )):
        with pytest.raises(ValueError):
            assess_coverage("q", "a")


def test_missing_gap_defaults_to_empty_string_rather_than_raising():
    with patch("llm_client.requests.post", return_value=_mock_response('{"addresses": true}')):
        result = assess_coverage("q", "a")
    assert result["gap"] == ""
