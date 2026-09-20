"""Confidence reporting and escalation to a human (problem statement:
"mandatory source citations with a confidence indicator and a path to escalate
to a human IP facilitator").

The confidence label is derived from the retrieval distance the pipeline
already computes, not from a second model asked "how sure are you?". A model's
self-reported confidence is uncalibrated and tends to be high exactly when it
is wrong, which would undo the point of having a measured gate at all.

Escalation triggers on conditions the pipeline can actually observe. It is
deliberately generous: this tool's own evaluation shows over-refusal rather
than hallucination is its dominant failure mode, so the cost of offering a
human when one was not strictly needed is low, while the cost of not offering
one on a conflicting-authority question is a user acting on a partial answer.
"""
from confidence_gate import CONFIDENCE_THRESHOLD

HIGH = "high"
MODERATE = "moderate"
LOW = "low"

# Below this the best passage is a strong lexical/semantic match. Set at the
# distance where this corpus's hand-checked questions reliably return the
# right statute (the Phase 10 regime gate's passing cases sit well under it),
# rather than at a round number.
HIGH_CONFIDENCE_DISTANCE = 0.65


def confidence_label(best_distance: float | None) -> str:
    """high / moderate / low, from the same distance Layer 1 gates on.

    `None` (nothing retrieved at all) is LOW, not an error: no evidence is the
    least confident state there is.
    """
    if best_distance is None:
        return LOW
    if best_distance <= HIGH_CONFIDENCE_DISTANCE:
        return HIGH
    if best_distance <= CONFIDENCE_THRESHOLD:
        return MODERATE
    return LOW


CONFIDENCE_EXPLANATIONS = {
    HIGH: "The cited passages closely match the question.",
    MODERATE: "The cited passages match, but less closely — read them before relying on this.",
    LOW: "Nothing in the corpus matched well enough to answer from.",
}


def assess(
    *,
    refused: bool = False,
    best_distance: float | None = None,
    rejected_claims: int = 0,
    conflicting_authority: bool = False,
    out_of_coverage_regimes: list[str] | None = None,
    unsourced_category: bool = False,
) -> dict:
    """Whether to offer a human, and the honest reason why.

    Each trigger corresponds to something the pipeline observed, so the reason
    shown to the user is never invented after the fact.
    """
    out_of_coverage_regimes = out_of_coverage_regimes or []
    reasons: list[str] = []

    if refused:
        reasons.append("the corpus could not support an answer to this question")
    if rejected_claims:
        reasons.append(
            f"{rejected_claims} drafted claim{'s' if rejected_claims != 1 else ''} "
            f"failed verification against the cited passage and {'were' if rejected_claims != 1 else 'was'} dropped"
        )
    if conflicting_authority:
        reasons.append("sources of different authority disagree on this point")
    if out_of_coverage_regimes:
        reasons.append(
            "this case involves "
            + ", ".join(sorted(out_of_coverage_regimes))
            + " law, which is not in this tool's corpus"
        )
    if unsourced_category:
        reasons.append(
            "the product category here is defined by an instrument not in this tool's corpus"
        )
    if not reasons and confidence_label(best_distance) == MODERATE:
        reasons.append("the supporting passages are a weaker match than usual")

    return {
        "escalate": bool(reasons),
        "reasons": reasons,
        "confidence": confidence_label(best_distance),
        "guidance": ESCALATION_GUIDANCE if reasons else None,
    }


ESCALATION_GUIDANCE = {
    "summary": "This question is worth putting to a person.",
    "contacts": [
        {
            "who": "A registered Indian patent agent or IP attorney",
            "when": "Filing decisions, freedom-to-operate, drafting, or anything with a deadline.",
            "where": "https://ipindia.gov.in/register-of-patent-agents.htm",
        },
        {
            "who": "National Biodiversity Authority",
            "when": "Access to biological resources, benefit-sharing, or Form-1 disclosure duties.",
            "where": "https://nbaindia.org/",
        },
        {
            "who": "Ministry of Ayush / State Licensing Authority",
            "when": "Manufacturing licences, classical vs proprietary classification, ASU drug rules.",
            "where": "https://ayush.gov.in/",
        },
        {
            "who": "TKDL unit (via a patent office or attorney with access)",
            "when": "An actual traditional-knowledge prior-art search is needed.",
            "where": "https://www.tkdl.res.in/",
        },
    ],
}

# Shown on every answer, including refusals — the problem statement requires a
# standing "information, not legal advice" disclaimer, and a disclaimer that
# only appears on confident answers is worth less than none.
STANDING_DISCLAIMER = (
    "This is information, not legal advice. Verify every citation against the primary "
    "source before acting on it."
)
