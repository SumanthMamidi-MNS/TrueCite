"""Layer 2 — claim-support verification (PRD §6.2).

"A separate LLM call checks: 'Does this retrieved passage actually support
this specific claim?' (yes/no + reasoning). A citation that's real but
doesn't back the claim must be rejected — this is the specific failure mode
that even production legal-AI tools still exhibit (2025 Stanford/Magesh
study). Closing this gap is the project's main technical claim."

Runs through llm_client, which defaults to a local Ollama model (Qwen 2.5
7B) rather than the Claude API the PRD specifies for this layer — a
temporary substitution while no Anthropic API key is in use (a real key
exists but is deliberately held back until deployment, to avoid burning
through its rate limits during development; see docs/decisions.md). Set
LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY to switch — no code change
needed here.
"""
import json
import os

import llm_client

# The active model's name, whichever provider llm_client is configured for —
# generate.py's GENERATION_MODEL reads the same function, so verification
# and generation can never name two different models.
MODEL = llm_client.active_model_name()

# NOT 0.0. At temperature=0 Ollama samples greedily, so all 3 verification
# calls below would return identical verdicts given identical prompts — a
# "3-vote majority" that's secretly just 1 vote repeated 3 times, silently
# collapsing the whole reason this function runs multiple calls at all (see
# its docstring: the same (claim, passage) pair genuinely split 2-1 across
# real runs). 0.3 keeps sampling spread narrow enough to still be a
# consistent, reproducible eval (paired with a distinct seed per vote below)
# without touching the prompt, the strictness instruction, the vote count,
# or the fail-closed drop below.
VERIFICATION_TEMPERATURE = float(os.environ.get("VERIFICATION_TEMPERATURE", "0.3"))

# One distinct, fixed seed per vote — reproducible across eval runs (same
# seed always lands in the same spot in the sampling distribution) while
# still being 3 genuinely different draws, not the same draw 3 times.
VERIFICATION_SEEDS = (101, 202, 303)

# The prompt verify_claim used through 2026-09-15. Kept byte-identical (not
# deleted) after the 2026-09-16 precision change below, for two reasons: the
# eval battery (src/run_verification_eval.py) needs to keep measuring it as
# the baseline every time it's re-run, not just once, and if the precise
# prompt is ever rejected by that battery's pre-committed criteria, this is
# what verify_claim falls back to (see docs/decisions.md).
VERIFICATION_PROMPT_TEMPLATE_ORIGINAL = """You are verifying whether a passage from a legal/regulatory document actually supports a specific claim. Read the ENTIRE passage first and resolve any pronouns or references (e.g. "these", "such", "the above") using earlier sentences in the SAME passage before judging — do not evaluate a later sentence in isolation from the sentence it depends on. Be strict about facts genuinely absent from the passage: a passage that is merely on the same topic, without actually stating or directly implying the claim, does NOT support it. In particular, a passage that only says something is "as prescribed" or "as may be determined" elsewhere does NOT support a claim that states a specific figure or detail.

Claim: {claim}

Passage:
\"\"\"
{passage}
\"\"\"

Respond with ONLY a JSON object in this exact format, no other text. Write "reasoning" FIRST, working through what the passage actually says step by step, and only then decide "supported" based on that reasoning — don't decide first and rationalize afterward:
{{"reasoning": "one or two sentence explanation, working through the passage's content first", "supported": true or false}}
"""

# 2026-09-16: the eval battery (src/run_verification_eval.py) found the
# original prompt above rejecting TRUE claims on two recurring patterns —
# inventing an "exclusivity" requirement the claim never asserted (e.g.
# rejecting "contravening section 6 is punishable with up to five years"
# because the passage also covers sections 3 and 4, not section 6
# exclusively), and demanding the claim's date/figure wording match the
# passage byte-for-byte (rejecting "as of March 2013" against the passage's
# own "as on 31st March, 2013"). Same root cause both times: the model was
# never told a claim should be judged only against what it actually asserts.
# This adds exactly that instruction, as a new sentence directly after the
# existing "as prescribed" sentence, and changes nothing else — see
# docs/decisions.md for the battery numbers this was measured against before
# being accepted.
#
# 2026-09-16, second amendment attempted and REJECTED: a spelling-variant
# false rejection was found ("AYUSH covers ... Homeopathy ..." rejected
# against a passage reading "...Homoeopathy..."). Extending the equivalence
# sentence to also cover spelling variants fixed that case (T7 accepted 3/3
# seed bases) and correctly still rejected an adversarial entity-substitution
# case (F10, "Chiropractic" swapped in, rejected 3/3), but caused an original
# adversarial case (F8, a claim with the date changed from March 2013 to
# March 2015) to regress to accepted at one seed base — a false accept that
# did not happen on the currently-shipped prompt. Per the pre-committed
# battery criteria, any regression of an original false case is a hard
# reject regardless of the true-accept gain, so the change was cut, not kept.
# See docs/decisions.md for the full numbers; the rejected wording is not
# reproduced here so this constant stays byte-identical to what's shipping.
VERIFICATION_PROMPT_TEMPLATE_PRECISE = """You are verifying whether a passage from a legal/regulatory document actually supports a specific claim. Read the ENTIRE passage first and resolve any pronouns or references (e.g. "these", "such", "the above") using earlier sentences in the SAME passage before judging — do not evaluate a later sentence in isolation from the sentence it depends on. Be strict about facts genuinely absent from the passage: a passage that is merely on the same topic, without actually stating or directly implying the claim, does NOT support it. In particular, a passage that only says something is "as prescribed" or "as may be determined" elsewhere does NOT support a claim that states a specific figure or detail. Judge the claim exactly as it is written — no stronger and no weaker. A claim IS supported when the passage states it or directly implies it, including when the claim concerns only one of several items or cases that the passage lists together: do not reject a claim because the passage also covers additional cases, and do not demand that the passage state something the claim itself does not assert (such as that a rule applies "only" or "exclusively" to the claim's subject). An equivalent wording of the same date, figure, or entity (for example "as on 31st March, 2013" and "as of March 2013") counts as stated. But every specific figure, date, entity, section number, and negation in the claim must match the passage exactly — a claim that changes any of them is NOT supported.

Claim: {claim}

Passage:
\"\"\"
{passage}
\"\"\"

Respond with ONLY a JSON object in this exact format, no other text. Write "reasoning" FIRST, working through what the passage actually says step by step, and only then decide "supported" based on that reasoning — don't decide first and rationalize afterward:
{{"reasoning": "one or two sentence explanation, working through the passage's content first", "supported": true or false}}
"""

# Whichever prompt verify_claim actually uses. The precision battery
# (src/run_verification_eval.py, results in
# corpus/eval_results/verification_battery_{current,precise}.json) passed
# both pre-committed criteria on the first attempt: zero false-accepts at any
# of 3 seed bases (27/27 correctly rejected, same as baseline — the "never
# accepts a false claim" property held), and true-accepts strictly improved
# (15/18 -> 18/18, the precise prompt's whole point). See docs/decisions.md
# for the full numbers. src/run_verification_eval.py can still point this at
# either named constant above for a re-run without changing which one ships.
VERIFICATION_PROMPT_TEMPLATE = VERIFICATION_PROMPT_TEMPLATE_PRECISE


def _verify_claim_once(claim: str, passage: str, timeout: int, seed: int) -> dict:
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(claim=claim, passage=passage)
    raw = llm_client.complete(
        prompt, timeout=timeout, temperature=VERIFICATION_TEMPERATURE, seed=seed
    )
    result = json.loads(raw)
    if "supported" not in result or not isinstance(result["supported"], bool):
        raise ValueError(f"malformed verification response: {raw!r}")
    return result


def verify_claim(
    claim: str, passage: str, timeout: int = 120, votes: int = len(VERIFICATION_SEEDS)
) -> dict:
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
    # votes defaults to len(VERIFICATION_SEEDS) precisely so the two can't
    # drift apart — one seed per vote, taken in order, so a caller who
    # deliberately passes a smaller `votes` still gets distinct seeds rather
    # than reusing one.
    results = []
    for seed in VERIFICATION_SEEDS[:votes]:
        try:
            results.append(_verify_claim_once(claim, passage, timeout, seed))
        except (llm_client.ProviderRateLimited, llm_client.ProviderUnreachable):
            # Must NOT be swallowed by the broad tolerance below. If it
            # were, an unavailable provider would fail every vote silently,
            # this function would then raise a generic ValueError ("all N
            # votes failed"), and the caller (generate.py) would drop the
            # claim as "verification unavailable" exactly like an ordinary
            # parse failure — eventually producing the Layer 2 grounding
            # refusal when every claim is dropped that way. That is exactly
            # the confusion these exceptions exist to prevent (see
            # llm_client.ProviderRateLimited's and ProviderUnreachable's
            # docstrings), so either propagates immediately instead of being
            # retried per-vote or absorbed here.
            raise
        except Exception:
            # Broad on purpose: must tolerate a failed vote the same way
            # regardless of which provider llm_client is configured for.
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
