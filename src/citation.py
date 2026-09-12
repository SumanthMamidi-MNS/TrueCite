"""Layer 3 — citation formatting + authority resolution (PRD §6.2, §6.4).

"Every generated claim must reference its source with document name, section,
and effective date, e.g. [Source: Patents Act §3(p), effective 2023]."

"If multiple versions of a rule exist, the system must surface the current
authoritative one, not just the most semantically similar chunk."

Authority *detection* (recognizing that two retrieved chunks discuss the same
underlying rule) isn't attempted here as a standalone algorithm — this
corpus's actual documents don't have a genuine conflicting-rule pair to
detect (the 2012 and 2025 guidelines complement rather than supersede each
other; see docs/decisions.md), so a heuristic built without a real case to
validate against would be guessing. Instead, `resolve_authority` provides
the well-defined, testable half — given a set of candidate sources already
established as relevant to the same question, rank them by authority first
and recency second, so generation naturally leads with the most authoritative
one rather than whichever happened to score best by similarity.
"""
from authority import authority_rank, get_authority


def format_citation(doc_id: str, section_number: str | None) -> str:
    meta = get_authority(doc_id)
    if section_number:
        return f"[Source: {meta['short_name']}, §{section_number}, effective {meta['effective_date']}]"
    return f"[Source: {meta['short_name']}, effective {meta['effective_date']}]"


def resolve_authority(doc_ids: list[str]) -> list[str]:
    """Sort doc_ids by authority (Act > Guideline > Informational), then by
    more recent effective_date within the same authority level.

    Order-preserving among exact ties (same level and date) — no doc_id in
    this corpus is at that level of tie, but the guarantee matters for
    caller predictability regardless.
    """
    def sort_key(doc_id: str) -> tuple[int, str]:
        meta = get_authority(doc_id)
        return (-authority_rank(meta["authority_level"]), _invert_date(meta["effective_date"]))

    return sorted(doc_ids, key=sort_key)


def _invert_date(iso_date: str) -> str:
    """A string that sorts in reverse (most-recent-first) via plain ascending sort."""
    return "".join(chr(57 - (ord(c) - 48)) if c.isdigit() else c for c in iso_date)
