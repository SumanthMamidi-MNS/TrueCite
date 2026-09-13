"""Unit tests for llm_client.py's provider dispatch (PRD §7's Ollama-vs-Claude
substitution, see its own module docstring and docs/decisions.md). No real
network calls — Ollama's HTTP call and the anthropic SDK are both mocked.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

import llm_client


def _mock_ollama_response(response_json_str: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": response_json_str}
    mock.raise_for_status.return_value = None
    return mock


def test_defaults_to_ollama_when_provider_unset():
    assert llm_client.LLM_PROVIDER == "ollama"


def test_complete_routes_to_ollama_by_default():
    with patch("llm_client.requests.post", return_value=_mock_ollama_response("hello")) as mock_post:
        result = llm_client.complete("a prompt", timeout=10)
    assert result == "hello"
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == llm_client.OLLAMA_URL


def test_complete_routes_to_anthropic_when_configured():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="hello from claude")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("llm_client.LLM_PROVIDER", "anthropic"), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("anthropic.Anthropic", return_value=mock_client) as mock_anthropic_cls, \
         patch("llm_client.requests.post") as mock_post:
        result = llm_client.complete("a prompt", timeout=10)

    assert result == "hello from claude"
    mock_anthropic_cls.assert_called_once_with(api_key="test-key", timeout=10)
    mock_post.assert_not_called()


def test_anthropic_provider_without_api_key_raises_clear_error():
    # Fail loudly rather than silently falling back to Ollama — a deploy
    # that sets LLM_PROVIDER=anthropic but forgets the key should not
    # silently keep running on the local model instead.
    with patch("llm_client.LLM_PROVIDER", "anthropic"), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            llm_client.complete("a prompt")


def test_active_model_name_reflects_provider():
    with patch("llm_client.LLM_PROVIDER", "ollama"):
        assert llm_client.active_model_name() == llm_client.OLLAMA_MODEL
    with patch("llm_client.LLM_PROVIDER", "anthropic"):
        assert llm_client.active_model_name() == llm_client.ANTHROPIC_MODEL
