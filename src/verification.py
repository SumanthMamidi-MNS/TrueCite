"""Layer 2 — claim-support verification (PRD §6.2).

"A separate LLM call checks: 'Does this retrieved passage actually support
this specific claim?' (yes/no + reasoning). A citation that's real but
doesn't back the claim must be rejected — this is the specific failure mode
that even production legal-AI tools still exhibit (2025 Stanford/Magesh
study). Closing this gap is the project's main technical claim."

Uses a local Ollama model (Qwen 2.5 7B), not the Claude API the PRD
specifies for this layer — temporary substitution, no Anthropic API key is
configured yet. See docs/decisions.md. Revisit once one exists.
"""
import json

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

VERIFICATION_PROMPT_TEMPLATE = """You are verifying whether a passage from a legal/regulatory document actually supports a specific claim. Read the ENTIRE passage first and resolve any pronouns or references (e.g. "these", "such", "the above") using earlier sentences in the SAME passage before judging — do not evaluate a later sentence in isolation from the sentence it depends on. Be strict about facts genuinely absent from the passage: a passage that is merely on the same topic, without actually stating or directly implying the claim, does NOT support it. In particular, a passage that only says something is "as prescribed" or "as may be determined" elsewhere does NOT support a claim that states a specific figure or detail.

Claim: {claim}

Passage:
\"\"\"
{passage}
\"\"\"

Respond with ONLY a JSON object in this exact format, no other text. Write "reasoning" FIRST, working through what the passage actually says step by step, and only then decide "supported" based on that reasoning — don't decide first and rationalize afterward:
{{"reasoning": "one or two sentence explanation, working through the passage's content first", "supported": true or false}}
"""


def _verify_claim_once(claim: str, passage: str, model: str, timeout: int) -> dict:
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(claim=claim, passage=passage)
    response = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    raw = response.json()["response"]
    result = json.loads(raw)
    if "supported" not in result or not isinstance(result["supported"], bool):
        raise ValueError(f"malformed verification response: {raw!r}")
    return result


def verify_claim(claim: str, passage: str, model: str = MODEL, timeout: int = 120, votes: int = 3) -> dict:
    """Returns {"supported": bool, "reasoning": str, "votes": list[bool]}.

    Runs the verification call `votes` times and takes the majority verdict,
    rather than trusting a single call — observed directly (see
    docs/decisions.md) that this local 7B model is genuinely non-deterministic
    on borderline-coreference cases: the same (claim, passage) pair, same
    prompt, produced 2 "supported" and 1 "not supported" verdicts across 3
    runs on a claim that WAS correctly supported. A single unlucky call would
    have silently produced a false refusal. Raises (rather than defaulting a
    verdict) if every call fails to parse, for the same fail-closed reason
    a single call raises on malformed output.
    """
    results = []
    for _ in range(votes):
        try:
            results.append(_verify_claim_once(claim, passage, model, timeout))
        except (ValueError, requests.RequestException):
            continue
    if not results:
        raise ValueError(f"all {votes} verification calls failed to produce a parseable response")

    supported_votes = [r["supported"] for r in results]
    majority_supported = sum(supported_votes) > len(supported_votes) / 2
    # Use the reasoning from a result that agrees with the majority verdict.
    agreeing_reasoning = next(
        r["reasoning"] for r in results if r["supported"] == majority_supported
    )
    return {"supported": majority_supported, "reasoning": agreeing_reasoning, "votes": supported_votes}
