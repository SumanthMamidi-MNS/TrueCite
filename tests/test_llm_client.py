"""Unit tests for llm_client.py's provider dispatch (PRD §7's Ollama-vs-Claude
substitution, see its own module docstring and docs/decisions.md). No real
network calls — Ollama's HTTP call and the anthropic SDK are both mocked.
"""
import importlib
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


def test_complete_routes_to_gemini_when_configured():
    mock_response = MagicMock()
    mock_response.text = "hello from gemini"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("llm_client.LLM_PROVIDER", "gemini"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("google.genai.Client", return_value=mock_client) as mock_genai_cls, \
         patch("llm_client.requests.post") as mock_post:
        result = llm_client.complete("a prompt", timeout=10)

    assert result == "hello from gemini"
    mock_genai_cls.assert_called_once()
    assert mock_genai_cls.call_args.kwargs["api_key"] == "test-key"
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == llm_client.GEMINI_MODEL
    assert call_kwargs["contents"] == "a prompt"
    # W1: temperature/seed now travel via a GenerateContentConfig (default
    # temperature=0.0, no seed passed here so none is set) — see the
    # dedicated test_gemini_receives_temperature_and_seed_via_config below
    # for the case where they're actually threaded through.
    assert call_kwargs["config"].temperature == 0.0
    assert call_kwargs["config"].seed is None
    mock_post.assert_not_called()


def test_gemini_provider_without_api_key_raises_clear_error():
    with patch("llm_client.LLM_PROVIDER", "gemini"), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            llm_client.complete("a prompt")


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
    with patch("llm_client.LLM_PROVIDER", "gemini"):
        assert llm_client.active_model_name() == llm_client.GEMINI_MODEL


# --- W1: num_ctx + sampling controls (the front-truncation fix) ---------


def test_ollama_options_include_num_ctx():
    # The actual bug fix: qwen2.5:7b silently truncated any prompt past
    # Ollama's built-in 2048-token default because no num_ctx was ever sent.
    # See llm_client.py's OLLAMA_NUM_CTX comment for the measured proof.
    with patch("llm_client.requests.post", return_value=_mock_ollama_response("hi")) as mock_post:
        llm_client.complete("a prompt", timeout=10)
    options = mock_post.call_args.kwargs["json"]["options"]
    assert options["num_ctx"] == llm_client.OLLAMA_NUM_CTX


def test_ollama_options_include_temperature_and_seed_when_passed():
    with patch("llm_client.requests.post", return_value=_mock_ollama_response("hi")) as mock_post:
        llm_client.complete("a prompt", timeout=10, temperature=0.3, seed=101)
    options = mock_post.call_args.kwargs["json"]["options"]
    assert options["temperature"] == 0.3
    assert options["seed"] == 101


def test_ollama_options_omit_seed_when_none():
    with patch("llm_client.requests.post", return_value=_mock_ollama_response("hi")) as mock_post:
        llm_client.complete("a prompt", timeout=10, temperature=0.0, seed=None)
    options = mock_post.call_args.kwargs["json"]["options"]
    assert "seed" not in options


def test_ollama_format_and_stream_flags_unchanged():
    # Guards against the options addition accidentally displacing these.
    with patch("llm_client.requests.post", return_value=_mock_ollama_response("hi")) as mock_post:
        llm_client.complete("a prompt", timeout=10)
    body = mock_post.call_args.kwargs["json"]
    assert body["format"] == "json"
    assert body["stream"] is False


def test_ollama_num_ctx_env_override_is_honored():
    # OLLAMA_NUM_CTX is read at import time, so the override only takes
    # effect through a reload — restore the module to its normal state
    # afterward so later tests in this session see the real default again.
    try:
        with patch.dict(os.environ, {"OLLAMA_NUM_CTX": "4096"}):
            importlib.reload(llm_client)
            assert llm_client.OLLAMA_NUM_CTX == 4096
            with patch(
                "llm_client.requests.post", return_value=_mock_ollama_response("hi")
            ) as mock_post:
                llm_client.complete("a prompt", timeout=10)
            options = mock_post.call_args.kwargs["json"]["options"]
            assert options["num_ctx"] == 4096
    finally:
        importlib.reload(llm_client)


def test_anthropic_receives_temperature_and_does_not_crash_with_seed():
    # Anthropic has no seed parameter (see _complete_anthropic's docstring
    # comment) — passing one must be silently ignored, not raise.
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="hello from claude")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("llm_client.LLM_PROVIDER", "anthropic"), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = llm_client.complete("a prompt", timeout=10, temperature=0.3, seed=101)

    assert result == "hello from claude"
    assert mock_client.messages.create.call_args.kwargs["temperature"] == 0.3
    assert "seed" not in mock_client.messages.create.call_args.kwargs


def test_gemini_receives_temperature_and_seed_via_config():
    mock_response = MagicMock()
    mock_response.text = "hello from gemini"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("llm_client.LLM_PROVIDER", "gemini"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("google.genai.Client", return_value=mock_client):
        result = llm_client.complete("a prompt", timeout=10, temperature=0.3, seed=101)

    assert result == "hello from gemini"
    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.temperature == 0.3
    assert config.seed == 101


def test_estimate_tokens_is_a_rough_char_based_estimate():
    assert llm_client.estimate_tokens("a" * 400) == 100
