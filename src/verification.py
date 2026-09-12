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

VERIFICATION_PROMPT_TEMPLATE = """You are verifying whether a passage from a legal/regulatory document actually supports a specific claim. Be strict: a passage that is merely on the same topic, without actually stating or directly implying the claim, does NOT support it. In particular, a passage that only says something is "as prescribed" or "as may be determined" elsewhere does NOT support a claim that states a specific figure or detail.

Claim: {claim}

Passage:
\"\"\"
{passage}
\"\"\"

Respond with ONLY a JSON object in this exact format, no other text:
{{"supported": true or false, "reasoning": "one or two sentence explanation"}}
"""


def verify_claim(claim: str, passage: str, model: str = MODEL, timeout: int = 120) -> dict:
    """Returns {"supported": bool, "reasoning": str}.

    Raises on malformed model output rather than silently defaulting to
    either verdict — a verification layer that fails open on a parse error
    defeats its own purpose (an unparseable "maybe" must not become "yes").
    """
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
