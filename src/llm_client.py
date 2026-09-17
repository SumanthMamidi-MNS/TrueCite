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

# qwen2.5:7b's Modelfile sets no num_ctx, so unset it defaults to Ollama's
# built-in 2048-token context — and Ollama TRUNCATES a longer prompt from the
# FRONT, silently keeping only the tail. Measured directly: a 42,467-char
# prompt came back with prompt_eval_count 2050 and a marker placed at the
# start of the prompt was invisible to the model while one at the end was
# visible. Since this pipeline's generation prompt is ordered [instructions,
# Question, passages, JSON format spec], front-truncation was destroying the
# instructions, the question, and the highest-ranked passages first — the
# real cause behind several failures previously assumed to be model-quality
# issues. 8192 was confirmed sufficient on the same prompt (prompt_eval_count
# 3980, both a start and end marker visible; latency rose 10.3s -> 13.2s).
# Left env-overridable on purpose: we need an honest A/B of 2048 vs 8192 on
# otherwise-identical code to produce a real before/after number, not just
# assert one.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))

# A rough estimate only (~4 chars/token for English), not a real tokenizer —
# good enough for an observational budget check, not for anything that needs
# to be exact.
PROMPT_BUDGET_TOKENS = OLLAMA_NUM_CTX


def estimate_tokens(text: str) -> int:
    """Rough token-count estimate (chars // 4), NOT a real tokenizer. Exists
    so callers can log/compare a prompt's size against PROMPT_BUDGET_TOKENS —
    deliberately not precise, and deliberately not used to truncate or block
    anything (see complete()'s docstring)."""
    return len(text) // 4


def _complete_ollama(prompt: str, timeout: int, temperature: float, seed: int | None) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": OLLAMA_NUM_CTX,
                "temperature": temperature,
                **({"seed": seed} if seed is not None else {}),
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["response"]


def _complete_anthropic(prompt: str, timeout: int, temperature: float, seed: int | None) -> str:
    """`seed` is accepted only for interface parity with the other two
    providers — it is NOT sent to Anthropic. The Anthropic API has no seed
    parameter, so there is no real way to honor it here; silently pretending
    otherwise would fake parity instead of disclosing a real gap. Callers
    that need reproducible sampling (see verification.py/generate.py) get it
    on Ollama and Gemini; on Anthropic, only `temperature` narrows spread.
    """
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
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _complete_gemini(prompt: str, timeout: int, temperature: float, seed: int | None) -> str:
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
    config_kwargs = {"temperature": temperature}
    if seed is not None:
        config_kwargs["seed"] = seed
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return response.text


def complete(
    prompt: str, timeout: int = 120, temperature: float = 0.0, seed: int | None = None
) -> str:
    """Run one prompt through the configured provider, returning its raw text
    response. Callers parse that text as JSON themselves (both existing
    prompts already ask for a bare JSON object) — this module only changes
    WHERE the text comes from, not how it's interpreted, so switching
    providers can't silently change validation/error-handling behavior.

    `temperature`/`seed` are threaded to whichever provider is active so call
    sites can get reproducible sampling (see generate.py/verification.py for
    why each site picks the values it does). `seed` is best-effort: Ollama
    honors it, Gemini's config accepts it, Anthropic has no such parameter
    (see _complete_anthropic) and simply ignores it.

    This function never truncates or raises based on prompt length — see
    OLLAMA_NUM_CTX/estimate_tokens above for the actual fix to the silent
    front-truncation bug; a length guard here would only be observational
    and could never be more correct than fixing num_ctx at the source.
    """
    if LLM_PROVIDER == "gemini":
        return _complete_gemini(prompt, timeout, temperature, seed)
    if LLM_PROVIDER == "anthropic":
        return _complete_anthropic(prompt, timeout, temperature, seed)
    return _complete_ollama(prompt, timeout, temperature, seed)


def active_model_name() -> str:
    """What the UI's model badge shows — see api.py's /api/config."""
    if LLM_PROVIDER == "gemini":
        return GEMINI_MODEL
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_MODEL
    return OLLAMA_MODEL
