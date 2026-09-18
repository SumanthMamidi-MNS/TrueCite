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
import time

import requests

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()


class ProviderRateLimited(Exception):
    """Raised when the configured cloud provider reports a rate-limit/quota
    condition (HTTP 429 or the provider SDK's own equivalent) — a distinct,
    temporary INFRASTRUCTURE state, never to be conflated with Layer 1/2
    deciding the corpus doesn't support an answer. See generate.py's handling
    in answer_query_streaming for why this matters: this project's whole
    design principle is "know when you don't know", and a rate limit is not
    that — it is "know when the model is temporarily unreachable" instead.
    The original provider exception's message is preserved (str(exc)) so the
    underlying cause is never lost, only reclassified.

    Ollama (the local default) has no rate-limit concept and never raises
    this — see _complete_ollama. When Ollama itself is unreachable it raises
    the separate ProviderUnreachable below instead (not this class): the two
    are deliberately kept apart rather than merged under one name, because
    "the provider said slow down" and "the provider can't be reached at all"
    are different failures with different honest descriptions, even though
    generate.py chooses to react to both the same way (see ProviderUnreachable's
    docstring for why the reaction is shared but the class is not).
    """


class ProviderUnreachable(Exception):
    """Raised when the configured provider's HTTP endpoint could not be
    reached at all (connection refused, DNS failure, or a request that timed
    out waiting for a response) — as opposed to ProviderRateLimited above,
    where the provider WAS reached and explicitly said "slow down" (HTTP 429
    or its SDK equivalent). Conflating the two under one name would hide a
    real distinction from anyone reading this code later: a rate limit often
    clears on its own in a few seconds, "Ollama isn't running" or "hung past
    its timeout" does not.

    Currently only raised by _complete_ollama. A local Ollama server being
    down/wrong-port is the case this was written for (see the 2026-09-18 bug
    report in docs/decisions.md): `requests.post` raised a bare
    `requests.exceptions.ConnectionError` that nothing caught, so it
    propagated all the way through generate.py's streaming generator to the
    SSE layer and rendered as a raw, alarming stack-trace-looking string in
    the chat UI's error box (web/app.js's generic `error` event path) —
    exactly the kind of infrastructure failure this project's design
    principle says must never be shown to the user as-is, or confused with
    "the corpus doesn't support this answer."

    `requests.exceptions.Timeout` raises this too, not because a slow
    response is the same underlying condition as connection-refused, but
    because it hits the identical downstream bug (an uncaught exception
    reaching the SSE layer as raw text) and deserves the identical honest,
    non-technical message — and because retrying a call that already used
    its full timeout budget would just make the user wait that same amount
    again for what will very likely be the same outcome.

    Deliberately NOT retried, unlike ProviderRateLimited: this failure isn't
    the kind that a 1-3 second backoff resolves, so retrying would only
    delay an identical failure rather than have a real chance of avoiding
    it. The caller gets this on the very first attempt.

    generate.py's answer_query_streaming catches this alongside
    ProviderRateLimited at every call site and emits the same
    `provider_unavailable` SSE event with the same message — from the
    user's point of view, "the model is rate-limited" and "the model can't
    be reached" both mean the same thing (try again shortly, this has
    nothing to do with the corpus), even though the code keeps the two
    conditions honestly distinct internally.
    """


# How long to wait before each retry after a rate-limited call, in seconds —
# 2 short retries (not more): a genuinely transient limit often clears within
# a few seconds, but a hard quota exhaustion (the likely case on Gemini's
# free tier, what this whole feature exists for) won't clear no matter how
# long we wait, so retrying longer or more times would only make the user
# wait longer for the same outcome.
_RATE_LIMIT_BACKOFFS_SEC = (1, 3)


def _complete_with_rate_limit_retry(call, is_rate_limited):
    """Run `call()` (a zero-arg thunk performing one provider request),
    retrying with backoff only while the raised exception is recognized as a
    rate-limit/quota condition per `is_rate_limited(exc)`. Any other
    exception propagates immediately, unchanged — this function only ever
    reclassifies rate-limit errors, nothing else. After the backoff schedule
    is exhausted, raises ProviderRateLimited with the last attempt's message.
    """
    last_exc = None
    for delay in (0,) + _RATE_LIMIT_BACKOFFS_SEC:
        if delay:
            time.sleep(delay)
        try:
            return call()
        except Exception as exc:
            if not is_rate_limited(exc):
                raise
            last_exc = exc
    raise ProviderRateLimited(str(last_exc)) from last_exc


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
    # Deliberately does NOT go through _complete_with_rate_limit_retry — a
    # local Ollama server has no rate-limit/quota concept, and an HTTP-level
    # failure (`requests.exceptions.HTTPError` from raise_for_status below)
    # is a type neither rate-limit detector above ever matches, so it can't
    # be accidentally reclassified as ProviderRateLimited; it propagates as
    # itself, unchanged.
    #
    # A connection failure or timeout is different: left uncaught, it used
    # to propagate as a raw requests exception all the way to the SSE layer
    # and render as a stack-trace-looking string in the chat UI (see
    # ProviderUnreachable's docstring). Reclassified here instead — no
    # retry, single attempt — so generate.py can react to it the same
    # honest way it already reacts to ProviderRateLimited.
    try:
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
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        raise ProviderUnreachable(str(exc)) from exc
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

    def _call():
        return client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

    # anthropic's SDK (confirmed against the installed 1.5.0: see
    # anthropic/_exceptions.py) raises a dedicated `anthropic.RateLimitError`
    # (an APIStatusError subclass, status_code == 429) for exactly this
    # condition — no status-code sniffing needed, unlike Gemini below.
    message = _complete_with_rate_limit_retry(
        _call, lambda exc: isinstance(exc, anthropic.RateLimitError)
    )
    return message.content[0].text


def _complete_gemini(prompt: str, timeout: int, temperature: float, seed: int | None) -> str:
    # Imported lazily, same reasoning as the anthropic import above — only
    # needs to actually work when this provider is selected.
    from google import genai
    from google.genai import errors as genai_errors
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

    def _call():
        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    # google-genai (confirmed against the installed 2.23.0: see
    # google/genai/errors.py) has no dedicated rate-limit exception class —
    # ANY 4xx status raises the same `genai.errors.ClientError`, with the
    # real HTTP status on `.code`. So unlike anthropic above, this must
    # check `.code == 429` specifically rather than the exception TYPE alone
    # — a bare `except ClientError` would also swallow a 400 bad-request or
    # a 403 permission error as if they were a transient rate limit.
    response = _complete_with_rate_limit_retry(
        _call,
        lambda exc: isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429,
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
