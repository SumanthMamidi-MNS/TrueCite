"""IP-type routing and the ABS / TK triggers (problem statement: "routing
across IP types", "an ABS-compliance helper and a TKDL / prior-art pointer").

Coverage is derived from `authority.py`, never hardcoded. A regime is "in
coverage" precisely when some indexed document declares it, so adding the
Trade Marks Act made the trademark route real and dropping a source would make
it unavailable again — without anyone remembering to update a second list.
That matters more here than elsewhere: routing a user toward a regime whose
statute is not indexed would send them down a pathway this tool cannot say
anything grounded about, which is worse than saying it does not cover it.

The triggers are keyword/phrase based rather than an LLM classification, for
the same reason the classification tree is: routing is a coarse, auditable
decision about which bodies of law are potentially in play, and a user can see
exactly why a regime was surfaced. Recall is deliberately favoured over
precision — surfacing a regime the user then dismisses costs them a moment,
while missing one they needed is the failure that matters.
"""
import re

from authority import DOC_AUTHORITY

# Regime -> the signals that put it in play. Phrases, not bare words, wherever
# a bare word would be ambiguous ("design" and "mark" both appear constantly
# in unrelated legal prose).
REGIME_TRIGGERS: dict[str, list[str]] = {
    "patent": [r"\bpatent", r"\binvention", r"\bnovel(ty)?\b", r"\bprior art\b",
               r"\binventive step\b", r"\bnon-?obvious"],
    "trademark": [r"\btrade ?marks?\b", r"\bbrand(ing|ed)?\b", r"\blogo\b",
                  r"\bbrand name\b", r"\bpassing off\b"],
    "gi": [r"\bgeographical indication", r"\bGI tag\b", r"\borigin-linked\b",
           r"\bregion(al)?[- ]specific\b", r"\bterroir\b"],
    "design": [r"\bindustrial design\b", r"\bdesign registration\b",
               r"\bshape of the (article|product)\b", r"\bornamental\b",
               r"\bpackaging design\b"],
    "copyright": [r"\bcopyright\b", r"\bliterary work\b", r"\bmanuscript\b",
                  r"\bpublication\b", r"\btranslation rights\b"],
    "plant-variety": [r"\bplant variet(y|ies)\b", r"\bcultivar\b", r"\bseed\b",
                      r"\bfarmers'? rights\b", r"\bbreeder", r"\bgermplasm\b"],
    "trade-secret": [r"\btrade secret\b", r"\bconfidential (information|formula)\b",
                     r"\bundisclosed information\b", r"\bknow-?how\b"],
    "abs": [r"\bbiological resource", r"\bgenetic resource", r"\bbenefit[- ]sharing\b",
            r"\bNational Biodiversity Authority\b", r"\bNBA\b", r"\bbioprospect",
            r"\baccess and benefit", r"\bNagoya\b", r"\bplant (extract|material)\b",
            r"\bmedicinal plant"],
    "tk": [r"\btraditional knowledge\b", r"\bTKDL\b", r"\bclassical (text|formulation)\b",
           r"\bcommunity knowledge\b", r"\bfolk(lore)?\b", r"\bcodified knowledge\b"],
    "drug-regulatory": [r"\bdrug licen[cs]e\b", r"\bmanufacturing licen[cs]e\b",
                        r"\bclinical trial\b", r"\bnew drug\b", r"\bASU\b"],
    "food-cosmetic": [r"\bnutraceutical\b", r"\bfood supplement\b", r"\bAahara\b",
                      r"\bFSSAI\b", r"\bcosmetic\b", r"\blabelling\b"],
}

# Where to go when a regime is in play. Registries, not claims about the law.
REGIME_REGISTRIES = {
    "patent": "Indian Patent Office — https://ipindia.gov.in/patents.htm",
    "trademark": "Trade Marks Registry — https://ipindia.gov.in/trade-marks.htm",
    "gi": "GI Registry, Chennai — https://ipindia.gov.in/gi.htm",
    "design": "Designs Office — https://ipindia.gov.in/designs.htm",
    "copyright": "Copyright Office — https://copyright.gov.in/",
    "plant-variety": "PPV&FR Authority — https://plantauthority.gov.in/",
    "abs": "National Biodiversity Authority — https://nbaindia.org/",
    "tk": "TKDL (access restricted to patent offices under NDA) — https://www.tkdl.res.in/",
}


def regimes_in_coverage() -> set[str]:
    """Regimes some indexed document actually declares."""
    covered: set[str] = set()
    for meta in DOC_AUTHORITY.values():
        covered.update(meta["regimes"])
    return covered


def _matched_triggers(text: str, patterns: list[str]) -> list[str]:
    found = []
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            found.append(m.group(0).strip())
    return found


def route(case_text: str) -> dict:
    """Which regimes a case puts in play, split by whether we can speak to them.

    `in_coverage` regimes have indexed sources, so the pipeline can answer
    about them with citations. `out_of_coverage` regimes are surfaced anyway —
    the user still needs to know a regime applies to their situation — but
    flagged as something this tool cannot ground, with a registry to go to
    instead. Silently dropping them would be the harmful option: the user
    would never learn the regime was relevant.
    """
    covered = regimes_in_coverage()
    in_cov, out_cov = [], []
    for regime, patterns in REGIME_TRIGGERS.items():
        hits = _matched_triggers(case_text, patterns)
        if not hits:
            continue
        entry = {
            "regime": regime,
            "matched": hits,
            "registry": REGIME_REGISTRIES.get(regime),
        }
        (in_cov if regime in covered else out_cov).append(entry)

    return {
        "in_coverage": sorted(in_cov, key=lambda e: -len(e["matched"])),
        "out_of_coverage": sorted(out_cov, key=lambda e: -len(e["matched"])),
        "abs_triggered": any(e["regime"] == "abs" for e in in_cov + out_cov),
        "tk_triggered": any(e["regime"] == "tk" for e in in_cov + out_cov),
    }


# TKDL's content is not public — access is restricted to patent offices under
# NDA (a limitation this project has carried since Phase 1). So this points AT
# the resource and never claims to have searched it. Fabricating a TKDL record
# would be the single most damaging thing this tool could do in this domain,
# because such a record looks authoritative and is trivially acted upon.
TKDL_POINTER = (
    "Traditional-knowledge prior art for Indian systems of medicine is held in the "
    "Traditional Knowledge Digital Library (TKDL). Its contents are not publicly "
    "searchable — access is granted to patent offices under non-disclosure agreement — "
    "so this tool cannot search it and does not hold its records. Approach the TKDL "
    "unit (https://www.tkdl.res.in/) or a patent attorney with TKDL access for an "
    "actual prior-art search. Any TKDL record number produced by an AI system without "
    "that access should be treated as fabricated."
)


def prior_art_pointer(case_text: str) -> dict | None:
    """A TK prior-art pointer when TK or patenting is in play, else None."""
    r = route(case_text)
    if not (r["tk_triggered"] or any(e["regime"] == "patent"
                                     for e in r["in_coverage"] + r["out_of_coverage"])):
        return None
    return {"pointer": TKDL_POINTER, "searchable_by_this_tool": False}
