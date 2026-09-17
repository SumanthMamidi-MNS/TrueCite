"""Stage 5 of the pipeline — answer coverage check (advisory-only, run once
after Layer 2 verification, on the assembled answer).

NOT part of the PRD's numbered 3-layer defense. Layer 2 checks whether each
individual CLAIM is supported by its cited PASSAGE; nothing before this
stage ever checks whether the assembled ANSWER, as a whole, actually
addresses the QUESTION that was asked. A pipeline could in principle produce
a fully-verified-true answer that is nonetheless incomplete or off-topic
relative to the question, and nothing upstream would catch that.

The one rule that makes this stage safe to add: it must NEVER modify
`answer`, `claims`, or `citations` — only annotate. Rewritten text would be
text that has not passed Layer 2, reintroducing exactly the ungrounded-
assertion failure this whole project exists to close. It is also
deliberately non-blocking, same reasoning as relevance.py: this project's
own Phase 6 numbers are a 0/5 false-answer rate against a 5/11
false-refusal rate, so a stage that could refuse would attack the metric
that's already perfect and worsen the one that's already bad — especially
here, where a refusal would discard claims that each individually passed a
3-call majority-vote check, on the strength of a single unverified opinion
about responsiveness. That inverts the project's own evidentiary standard.
Fails open (no verdict, not a negative one) on any error.
"""
import json

import llm_client

COVERAGE_PROMPT_TEMPLATE = """Does the answer below fully address the question? Judge only whether it's responsive and complete relative to what was asked — do not judge whether it's correct (that's already been checked separately).

Question: {question}

Answer:
\"\"\"
{answer}
\"\"\"

Respond with ONLY a JSON object in this exact format, no other text. If it does not fully address the question, "gap" must briefly say what's missing; if it does, "gap" may be an empty string:
{{"addresses": true or false, "gap": "a short phrase, or empty if addresses is true"}}
"""


def assess_coverage(question: str, answer: str, timeout: int = 60) -> dict:
    """Returns {"addresses": bool, "gap": str}. Raises on a malformed
    response — the caller owns falling back to "not assessed" rather than
    this function guessing a default verdict.
    """
    prompt = COVERAGE_PROMPT_TEMPLATE.format(question=question, answer=answer)
    raw = llm_client.complete(prompt, timeout=timeout, temperature=0.0, seed=42)
    result = json.loads(raw)
    addresses = result.get("addresses")
    if not isinstance(addresses, bool):
        raise ValueError(f"malformed coverage response: {result!r}")
    gap = result.get("gap", "")
    if not addresses and not isinstance(gap, str):
        raise ValueError(f"malformed coverage response: {result!r}")
    return {"addresses": addresses, "gap": gap if isinstance(gap, str) else ""}
