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


# --- rate-limit / quota handling (ProviderRateLimited) ---------------------
#
# Detection confirmed directly against the installed SDKs (see
# llm_client.py's inline comments at each call site):
#   - anthropic 1.5.0: a dedicated `anthropic.RateLimitError`
#     (APIStatusError subclass, status_code == 429) — checked by type alone.
#   - google-genai 2.23.0: NO dedicated rate-limit class; any 4xx raises the
#     same `google.genai.errors.ClientError`, so detection must additionally
#     check `.code == 429` (a bare isinstance check would also catch 400/403).


def _gemini_client_error(code: int, message: str = "boom"):
    from google.genai import errors as genai_errors

    return genai_errors.ClientError(code, {"message": message, "status": "x"})


def _anthropic_rate_limit_error(message: str = "rate limited"):
    import anthropic

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers.get.return_value = None
    mock_response.request = MagicMock()
    return anthropic.RateLimitError(message, response=mock_response, body=None)


def test_gemini_rate_limit_retries_then_raises_provider_rate_limited():
    mock_client = MagicMock()
    err = _gemini_client_error(429, "quota exceeded")
    mock_client.models.generate_content.side_effect = [err, err, err]

    with patch("llm_client.LLM_PROVIDER", "gemini"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("google.genai.Client", return_value=mock_client), \
         patch("llm_client.time.sleep") as mock_sleep:
        with pytest.raises(llm_client.ProviderRateLimited, match="quota exceeded"):
            llm_client.complete("a prompt", timeout=10)

    # 1 initial call + 2 retries = 3 total attempts, backing off 1s then 3s.
    assert mock_client.models.generate_content.call_count == 3
    assert [c.args[0] for c in mock_sleep.call_args_list] == [1, 3]


def test_gemini_rate_limit_recovers_on_retry():
    mock_client = MagicMock()
    err = _gemini_client_error(429, "quota exceeded")
    ok_response = MagicMock()
    ok_response.text = "recovered"
    mock_client.models.generate_content.side_effect = [err, ok_response]

    with patch("llm_client.LLM_PROVIDER", "gemini"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("google.genai.Client", return_value=mock_client), \
         patch("llm_client.time.sleep"):
        result = llm_client.complete("a prompt", timeout=10)

    assert result == "recovered"
    assert mock_client.models.generate_content.call_count == 2


def test_gemini_non_rate_limit_client_error_propagates_unretried():
    # A 400/403/etc is a real ClientError too, but NOT a rate limit — must
    # propagate as-is, not be retried and not be reclassified.
    from google.genai import errors as genai_errors

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _gemini_client_error(400, "bad request")

    with patch("llm_client.LLM_PROVIDER", "gemini"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("google.genai.Client", return_value=mock_client), \
         patch("llm_client.time.sleep") as mock_sleep:
        with pytest.raises(genai_errors.ClientError):
            llm_client.complete("a prompt", timeout=10)

    mock_client.models.generate_content.assert_called_once()
    mock_sleep.assert_not_called()


def test_anthropic_rate_limit_retries_then_raises_provider_rate_limited():
    mock_client = MagicMock()
    err = _anthropic_rate_limit_error("rate limited, slow down")
    mock_client.messages.create.side_effect = [err, err, err]

    with patch("llm_client.LLM_PROVIDER", "anthropic"), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("anthropic.Anthropic", return_value=mock_client), \
         patch("llm_client.time.sleep") as mock_sleep:
        with pytest.raises(llm_client.ProviderRateLimited, match="rate limited"):
            llm_client.complete("a prompt", timeout=10)

    assert mock_client.messages.create.call_count == 3
    assert [c.args[0] for c in mock_sleep.call_args_list] == [1, 3]


def test_anthropic_rate_limit_recovers_on_retry():
    mock_client = MagicMock()
    err = _anthropic_rate_limit_error()
    ok_message = MagicMock()
    ok_message.content = [MagicMock(text="recovered")]
    mock_client.messages.create.side_effect = [err, ok_message]

    with patch("llm_client.LLM_PROVIDER", "anthropic"), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("anthropic.Anthropic", return_value=mock_client), \
         patch("llm_client.time.sleep"):
        result = llm_client.complete("a prompt", timeout=10)

    assert result == "recovered"
    assert mock_client.messages.create.call_count == 2


def test_anthropic_non_rate_limit_error_propagates_unretried():
    import anthropic

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.headers.get.return_value = None
    mock_response.request = MagicMock()
    bad_request_err = anthropic.BadRequestError("bad request", response=mock_response, body=None)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = bad_request_err

    with patch("llm_client.LLM_PROVIDER", "anthropic"), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("anthropic.Anthropic", return_value=mock_client), \
         patch("llm_client.time.sleep") as mock_sleep:
        with pytest.raises(anthropic.BadRequestError):
            llm_client.complete("a prompt", timeout=10)

    mock_client.messages.create.assert_called_once()
    mock_sleep.assert_not_called()


def test_ollama_error_never_raises_provider_rate_limited():
    # Ollama has no rate-limit concept — any failure (e.g. a 500 from
    # raise_for_status) must propagate as its normal requests exception,
    # never be reclassified as ProviderRateLimited.
    import requests as requests_lib

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests_lib.exceptions.HTTPError("server error")

    with patch("llm_client.requests.post", return_value=mock_response):
        with pytest.raises(requests_lib.exceptions.HTTPError):
            llm_client.complete("a prompt", timeout=10)


# --- ProviderUnreachable (2026-09-18 fix) -----------------------------------
#
# Confirmed live, from a real screenshot: with Ollama not running,
# `requests.post` raises `requests.exceptions.ConnectionError`, which was
# previously not caught anywhere and propagated as a raw Python exception
# string all the way to the chat UI's generic error box. This must instead
# be reclassified as ProviderUnreachable, with NO retry (unlike
# ProviderRateLimited above) — see llm_client.py's ProviderUnreachable
# docstring for why a connection failure isn't worth retrying the way a
# rate limit is.


def test_ollama_connection_error_raises_provider_unreachable_without_retry():
    import requests as requests_lib

    with patch(
        "llm_client.requests.post",
        side_effect=requests_lib.exceptions.ConnectionError("[WinError 10061] refused"),
    ) as mock_post, patch("llm_client.time.sleep") as mock_sleep:
        with pytest.raises(llm_client.ProviderUnreachable, match="refused"):
            llm_client.complete("a prompt", timeout=10)

    # Exactly one attempt — a connection-refused failure is not transient in
    # the way a rate limit can be, so retrying would only make the user wait
    # longer for the identical outcome.
    mock_post.assert_called_once()
    mock_sleep.assert_not_called()


def test_ollama_timeout_raises_provider_unreachable_without_retry():
    # A hung/overloaded Ollama hits the same "raw exception reaches the UI"
    # bug as connection-refused, so it gets the same treatment: reclassified,
    # not retried (see ProviderUnreachable's docstring for the reasoning).
    import requests as requests_lib

    with patch(
        "llm_client.requests.post",
        side_effect=requests_lib.exceptions.Timeout("timed out"),
    ) as mock_post, patch("llm_client.time.sleep") as mock_sleep:
        with pytest.raises(llm_client.ProviderUnreachable, match="timed out"):
            llm_client.complete("a prompt", timeout=10)

    mock_post.assert_called_once()
    mock_sleep.assert_not_called()


def test_ollama_provider_unreachable_is_distinct_from_provider_rate_limited():
    # A future reader must be able to tell the two apart by type — see
    # ProviderUnreachable's docstring for why they're kept as separate
    # classes even though generate.py reacts to both identically.
    import requests as requests_lib

    assert not issubclass(llm_client.ProviderUnreachable, llm_client.ProviderRateLimited)
    assert not issubclass(llm_client.ProviderRateLimited, llm_client.ProviderUnreachable)

    with patch(
        "llm_client.requests.post",
        side_effect=requests_lib.exceptions.ConnectionError("refused"),
    ):
        with pytest.raises(llm_client.ProviderUnreachable):
            llm_client.complete("a prompt", timeout=10)
        # And specifically not raised as ProviderRateLimited.
        with pytest.raises(llm_client.ProviderUnreachable) as exc_info:
            llm_client.complete("a prompt", timeout=10)
    assert not isinstance(exc_info.value, llm_client.ProviderRateLimited)
