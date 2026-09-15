"""Single seam between the pipeline (generate.py, verification.py) and
whichever LLM is actually configured.

Defaults to the local Ollama substitution this project has used throughout
(see docs/decisions.md) — nothing here changes that behavior, and it's what
someone who clones/downloads this repo and runs it locally uses, no API key
needed. Two cloud paths exist for a hosted deployment instead:

  - LLM_PROVIDER=gemini + GEMINI_API_KEY — the intended provider for an
    actual hosted deployment of this project (chosen over Anthropic for
    deployment specifically — see docs/decisions.md).
  - LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY — the Claude API the PRD
    originally specifies for this layer; built first, kept available.

Both cloud paths are reviewed, not live-tested — deliberately unexercised
against a real key during development (a real key exists for each but is
held back to avoid burning through rate limits before deployment; see
docs/decisions.md). Re-verify whichever one is actually deployed before
trusting its numbers.
"""
import os

import requests

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _complete_ollama(prompt: str, timeout: int) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["response"]


def _complete_anthropic(prompt: str, timeout: int) -> str:
    # Imported lazily so the `anthropic` package only needs to actually work
    # when this provider is selected — the default Ollama path (all local
    # development and testing so far) has no dependency on it.
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set — set it "
            "before deploying with the real API (see README's Running it section)."
        )
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _complete_gemini(prompt: str, timeout: int) -> str:
    # Imported lazily, same reasoning as the anthropic import above — only
    # needs to actually work when this provider is selected.
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set — set it "
            "before deploying with the real API (see README's Running it section)."
        )
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout * 1000))
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


def complete(prompt: str, timeout: int = 120) -> str:
    """Run one prompt through the configured provider, returning its raw text
    response. Callers parse that text as JSON themselves (both existing
    prompts already ask for a bare JSON object) — this module only changes
    WHERE the text comes from, not how it's interpreted, so switching
    providers can't silently change validation/error-handling behavior.
    """
    if LLM_PROVIDER == "gemini":
        return _complete_gemini(prompt, timeout)
    if LLM_PROVIDER == "anthropic":
        return _complete_anthropic(prompt, timeout)
    return _complete_ollama(prompt, timeout)


def active_model_name() -> str:
    """What the UI's model badge shows — see api.py's /api/config."""
    if LLM_PROVIDER == "gemini":
        return GEMINI_MODEL
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_MODEL
    return OLLAMA_MODEL
