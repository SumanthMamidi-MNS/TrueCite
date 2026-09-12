"""Layer 1 — retrieval confidence gate (PRD §6.2).

"Retrieved chunks must clear a similarity threshold. Below it -> refuse
immediately with an explicit 'not enough grounded information' response."

Threshold calibrated against real (query, distance) evidence gathered while
hand-checking Phases 2-3, not guessed:

  - Genuinely on-topic queries (even the hardest ones tested, e.g. a TRIPS/TK
    interaction question whose correct source ranked 5th, not 1st): best-hit
    distance was always <= ~0.63 across every query tested.
  - Genuinely unrelated queries (cricket rules, a cake recipe, water's boiling
    point, Delaware LLC tax): best-hit distance was always >= ~0.99.
  - A real, important middle zone exists between these: a query the corpus is
    topically related to but doesn't actually answer (e.g. asking for a
    specific patent filing fee, when the Act only says fees are "as may be
    prescribed" with no figures) scored 0.76-0.82 — clearly relevant-*looking*,
    not actually responsive. This gate is a coarse first filter and is not
    designed to catch that case; Layer 2 (claim-support verification) is.

Threshold set at 0.90: comfortably above every on-topic case observed, with
margin below the lowest genuinely-unrelated case (0.99), while still passing
through the ambiguous middle zone for Layer 2 to adjudicate rather than
silently refusing something that might be partially answerable.

This is a first calibration from a modest sample (~20 queries), not a final
number — revisit with the full Phase 6 eval set once it exists.
"""

CONFIDENCE_THRESHOLD = 0.90


def filter_confident_hits(hits: list[dict], threshold: float = CONFIDENCE_THRESHOLD) -> list[dict]:
    """Keep only hits at or under the distance threshold (lower distance = better)."""
    return [h for h in hits if h["distance"] <= threshold]


def passes_confidence_gate(hits: list[dict], threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    """True if at least one retrieved hit clears the threshold.

    False means: refuse immediately with an explicit "not enough grounded
    information" response rather than attempting to answer from weak matches.
    """
    return len(filter_confident_hits(hits, threshold)) > 0
