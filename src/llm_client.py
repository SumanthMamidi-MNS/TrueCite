"""Single seam between the pipeline (generate.py, verification.py) and
whichever LLM is actually configured.

Defaults to the local Ollama substitution this project has used throughout
(see docs/decisions.md) — nothing here changes that behavior. Set
LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY to switch to the real Claude
API the PRD specifies for generation and Layer 2 verification; that's the
only change deployment needs, not a code change. Deliberately unexercised
against a real key during development — the key exists but is held back
until deployment to avoid burning through its rate limits before then (see
docs/decisions.md) — so the Anthropic path here is reviewed, not
live-tested; re-verify it once the key is actually in use.
"""
import os

import requests

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


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


def complete(prompt: str, timeout: int = 120) -> str:
    """Run one prompt through the configured provider, returning its raw text
    response. Callers parse that text as JSON themselves (both existing
    prompts already ask for a bare JSON object) — this module only changes
    WHERE the text comes from, not how it's interpreted, so switching
    providers can't silently change validation/error-handling behavior.
    """
    if LLM_PROVIDER == "anthropic":
        return _complete_anthropic(prompt, timeout)
    return _complete_ollama(prompt, timeout)


def active_model_name() -> str:
    """What the UI's model badge shows — see api.py's /api/config."""
    return ANTHROPIC_MODEL if LLM_PROVIDER == "anthropic" else OLLAMA_MODEL
