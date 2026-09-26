"""Legal knowledge graph over the corpus (problem statement: "a relational
knowledge graph ... deepen[s] multi-step reasoning").

Two kinds of edge, both deterministic:

1. **Instrument relations** — which Act amends, is made under, implements or
   is explained by which other instrument. These are editorial facts about the
   law, curated by hand exactly as `authority.py`'s dates and authority levels
   are, because none of them can be read reliably out of the text: the
   Biological Diversity Rules 2024 do not say "I am made under the 2002 Act" in
   any form a pattern could trust.

2. **Section references** — "section 3 or section 4" inside a provision,
   resolved to the same instrument's own sections. Extracted with the same
   regexes `enrichment.py` already uses for retrieval scoring (including its
   exclusion of references to *other* statutes), so the two can never disagree
   about what a provision refers to.

The graph never changes what is retrieved, ranked or verified — it only adds
navigation to an answer: the amendment a stale Act is superseded by, the Rules
made under it, the treaty it implements, and the sections a cited provision
points at. Keeping it out of ranking means every measured evaluation number
still holds.
"""
import json
from functools import lru_cache
from pathlib import Path

from authority import DOC_AUTHORITY
from enrichment import (
    _CROSS_STATUTE_LOOKAHEAD_CHARS,
    _CROSS_STATUTE_RE,
    _NUMBER_RE,
    _SECTION_LIST_RE,
    _base_section_number,
    build_headings_by_section,
)

PROCESSED = Path(__file__).resolve().parent.parent / "corpus" / "processed"

# (source, relation, target, note). Directed: source <relation> target.
INSTRUMENT_RELATIONS: list[tuple[str, str, str, str]] = [
    ("biological_diversity_amendment_act_2023", "amends", "biological_diversity_act_2002",
     "Read the 2002 Act together with this amendment for the current law."),
    ("biological_diversity_rules_2024", "made_under", "biological_diversity_act_2002", ""),
    ("biological_diversity_act_2002", "implements", "cbd_convention", ""),
    ("nagoya_protocol", "supplements", "cbd_convention", ""),
    ("ipo_tk_biological_material_guidelines_2012", "guidance_on", "patents_act_1970", ""),
    ("ipo_ayush_examination_guidelines_2025", "guidance_on", "patents_act_1970", ""),
    ("pib_faq_patents_traditional_ayurvedic_medicine_2013", "explains", "patents_act_1970", ""),
    ("patents_act_1970", "implements", "trips_agreement", "Amended in 1999, 2002 and 2005 to meet TRIPS."),
    ("patents_act_1970", "implements", "pct_treaty", "India joined the PCT in 1998."),
    ("trade_marks_act_1999", "implements", "trips_agreement", ""),
    ("trade_marks_act_1999", "implements", "madrid_protocol",
     "Through the 2010 amendment, which the as-enacted copy in this corpus does not contain."),
    ("geographical_indications_act_1999", "implements", "trips_agreement", "TRIPS Articles 22–24."),
    ("designs_act_2000", "implements", "trips_agreement", ""),
    ("copyright_act_1957", "implements", "trips_agreement", "Amended in 1994 and 1999 for TRIPS."),
    ("plant_varieties_act_2001", "implements", "trips_agreement", "The sui generis system under TRIPS Article 27.3(b)."),
    ("wipo_gratk_treaty_2024", "parallels", "patents_act_1970",
     "Both require disclosure of the origin of biological material or knowledge in a patent application."),
]

# How each relation reads from either end, for display.
RELATION_PHRASES = {
    "amends": ("amends", "is amended by"),
    "made_under": ("is made under", "has rules made under it"),
    "implements": ("implements", "is implemented in India by"),
    "supplements": ("supplements", "is supplemented by"),
    "guidance_on": ("gives examination guidance on", "has examination guidance in"),
    "explains": ("explains", "is explained by"),
    "parallels": ("parallels", "is paralleled by"),
}


def related_instruments(doc_ids, jurisdiction: str | None = None) -> list[dict]:
    """Every instrument linked to any of `doc_ids`, in both directions.

    Instruments already among `doc_ids` are skipped — the answer cites them
    already. With a jurisdiction set, only instruments on that side are
    returned: the jurisdiction switch must keep the answer-sets apart, and a
    "related law" list that crossed it would quietly conflate them.
    """
    cited = set(doc_ids)
    out, seen = [], set()
    for src, rel, dst, note in INSTRUMENT_RELATIONS:
        for here, there, phrase in ((src, dst, RELATION_PHRASES[rel][0]),
                                    (dst, src, RELATION_PHRASES[rel][1])):
            if here not in cited or there in cited:
                continue
            meta = DOC_AUTHORITY.get(there)
            if meta is None:
                continue
            if jurisdiction and meta["jurisdiction"] != jurisdiction:
                continue
            key = (here, phrase, there)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "from": here,
                "from_name": DOC_AUTHORITY[here]["short_name"],
                "relation": phrase,
                "doc_id": there,
                "name": meta["short_name"],
                "jurisdiction": meta["jurisdiction"],
                "note": note,
            })
    return out


# An amending Act's section numbers refer to the Act it amends ("in section 55
# of the principal Act", or a substituted section quoting the principal Act's
# own numbering), not to its own clauses. Resolving them against the amending
# Act's own headings produced references like "§3 — In section 2 of the
# principal Act", which say nothing to a reader.
AMENDS = {src: dst for src, rel, dst, _ in INSTRUMENT_RELATIONS if rel == "amends"}


@lru_cache(maxsize=1)
def _section_graph() -> dict[str, list[dict]]:
    """chunk_id -> sections that the chunk refers to, resolved in the right instrument."""
    by_doc: dict[str, list[dict]] = {}
    for path in sorted(PROCESSED.glob("*.json")):
        by_doc[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    headings = {doc: build_headings_by_section(chunks) for doc, chunks in by_doc.items()}

    graph: dict[str, list[dict]] = {}
    for doc, chunks in by_doc.items():
        target = AMENDS.get(doc, doc)
        if target not in headings:
            continue
        name = DOC_AUTHORITY.get(target, {}).get("short_name", target)
        for chunk in chunks:
            # An amending Act's own number is never the thing it points at.
            refs = _references(chunk, headings[target], skip_own=(target == doc))
            if refs:
                graph[chunk["chunk_id"]] = [{**r, "doc_id": target, "name": name} for r in refs]
    return graph


def _references(chunk: dict, headings: dict[str, str], skip_own: bool = True) -> list[dict]:
    text = chunk["text"]
    own = _base_section_number(chunk) if skip_own else None
    found: dict[str, str] = {}
    for list_match in _SECTION_LIST_RE.finditer(text):
        for num in _NUMBER_RE.finditer(list_match.group()):
            number = num.group(0)
            if number in found or number == own:
                continue
            end = list_match.start() + num.end()
            if _CROSS_STATUTE_RE.match(text[end:end + _CROSS_STATUTE_LOOKAHEAD_CHARS]):
                continue  # a section of a DIFFERENT Act, not this one
            heading = headings.get(number)
            if heading:
                found[number] = heading
    return [{"section": n, "heading": h} for n, h in found.items()]


def section_references(chunk_id: str) -> list[dict]:
    return _section_graph().get(chunk_id, [])


def graph_stats() -> dict:
    sections = _section_graph()
    return {
        "instruments": len(DOC_AUTHORITY),
        "instrument_relations": len(INSTRUMENT_RELATIONS),
        "provisions_with_references": len(sections),
        "section_references": sum(len(v) for v in sections.values()),
    }
