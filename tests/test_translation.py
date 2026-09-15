"""Unit tests for translation.py, with the LLM call mocked out (no live
model server needed). See its module docstring for why translation runs on
an already-verified English answer rather than native Hindi generation.
"""
from unittest.mock import MagicMock, patch

import pytest

from translation import translate_answer


def _mock_response(response_json_str: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": response_json_str}
    mock.raise_for_status.return_value = None
    return mock


def test_translates_and_returns_the_translated_text():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"translated": "यह हिंदी पाठ है"}'
    )):
        result = translate_answer("this is English text", language="Hindi")
    assert result == "यह हिंदी पाठ है"


def test_raises_on_malformed_response_instead_of_returning_original():
    # Fail closed — a broken translation must not silently fall back to
    # showing the English text as if it were the requested language.
    with patch("llm_client.requests.post", return_value=_mock_response("not json at all")):
        with pytest.raises(Exception):
            translate_answer("some text")


def test_raises_when_translated_field_missing():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"reasoning": "forgot the field"}'
    )):
        with pytest.raises(ValueError):
            translate_answer("some text")


def test_defaults_to_hindi():
    with patch("llm_client.requests.post", return_value=_mock_response(
        '{"translated": "translated text"}'
    )) as mock_post:
        translate_answer("some text")
    prompt_sent = mock_post.call_args.kwargs["json"]["prompt"]
    assert "Hindi" in prompt_sent
