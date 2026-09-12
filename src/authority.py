"""Authority/date metadata for Layer 3 (temporal + authority tagging, PRD §6.2).

Hand-curated rather than regex-parsed from corpus/manifest.md's prose date
column: several of those dates are genuinely ambiguous (see notes below), and
guessing a single ISO date out of free text would be exactly the kind of
silent guess this project's core design principle says not to make. Small
enough (5 docs) that keeping this in sync with manifest.md by hand is low
risk; each entry's `date_note` records the actual source of the date so the
reasoning is checkable later, not just the number.

Authority rank: higher wins when chunks conflict and must be reconciled to a
single "current" answer (PRD: "surface the current authoritative version, not
just the most semantically similar chunk"). Within equal rank, more recent
effective_date wins — but note AUTH_LEVEL_INFORMATIONAL sources (WIPO
toolkit, PIB press release) should generally never override an Act or IPO
Guideline regardless of date; rank comparison should be checked before date.
"""

AUTH_LEVEL_ACT = "Act"
AUTH_LEVEL_IPO_GUIDELINE = "IPO Guideline"
AUTH_LEVEL_INFORMATIONAL = "Informational"

_RANK = {
    AUTH_LEVEL_ACT: 3,
    AUTH_LEVEL_IPO_GUIDELINE: 2,
    AUTH_LEVEL_INFORMATIONAL: 1,
}

# doc_id -> metadata. doc_id matches the stem used throughout src/ (see
# src/run_phase1.py's ALL_DOCS), not the manifest.md "File" column's path.
DOC_AUTHORITY: dict[str, dict] = {
    "patents_act_1970": {
        "title": "The Patents Act, 1970 (No. 39 of 1970), incorporating all amendments",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "2024-08-01",
        "date_precision": "day",
        "date_note": "IP India's consolidated text is 'incorporating all amendments till 1-08-2024' — this is the text's currency date, not the original 1970 enactment date.",
        "source_url": "https://ipindia.gov.in/frontend/pdf/patents/1_113_1_The_Patents_Act__1970___incorporating_all_amendments_till_1-08-2024.pdf",
    },
    "ipo_tk_biological_material_guidelines_2012": {
        "title": "Guidelines for Processing of Patent Applications relating to Traditional Knowledge and Biological Material",
        "authority_level": AUTH_LEVEL_IPO_GUIDELINE,
        "effective_date": "2012-11-08",
        "date_precision": "day",
        "date_note": "Issuance date reported in secondary legal-commentary sources found during corpus sourcing (Lexology); not printed on the PDF itself.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/220f0e1c-1301-4f0f-84a0-6709fa66c592.pdf",
    },
    "ipo_ayush_examination_guidelines_2025": {
        "title": "Guidelines for Examination of AYUSH-Related Inventions",
        "authority_level": AUTH_LEVEL_IPO_GUIDELINE,
        "effective_date": "2025-09-23",
        "date_precision": "day",
        "date_note": "Legal-commentary sources report release on National Ayurveda Day, 2025-09-23. IP India's own guidelines-listing page shows a 'Publish Date' of 29/04/2026 for this file, which is inconsistent (likely a site re-index/re-upload date, not the original issuance date) — flagged, not silently resolved. If this matters for a specific answer, both dates should be surfaced.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/335e2746-58c1-4b56-a1e5-cdd172a92a3c.pdf",
    },
    "wipo_documenting_tk_toolkit": {
        "title": "Documenting Traditional Knowledge and Traditional Cultural Expressions — A Toolkit",
        "authority_level": AUTH_LEVEL_INFORMATIONAL,
        "effective_date": "2017-01-01",
        "date_precision": "year",
        "date_note": "PDF's own copyright page: '© WIPO, 2017. Based on a consultation draft published in 2012.' Day/month unknown, hence year-only precision (Jan 1 is a placeholder, not a real publish date).",
        "source_url": "https://www.wipo.int/edocs/pubdocs/en/wipo_pub_1049.pdf",
    },
    "pib_faq_patents_traditional_ayurvedic_medicine_2013": {
        "title": "\"Patents to Traditional Ayurvedic Medicine\" — Press Information Bureau release",
        "authority_level": AUTH_LEVEL_INFORMATIONAL,
        "effective_date": "2013-08-12",
        "date_precision": "day",
        "date_note": "Date printed directly on the release itself.",
        "source_url": "https://www.pib.gov.in/newsite/printrelease.aspx?relid=98021",
    },
}


def authority_rank(authority_level: str) -> int:
    return _RANK[authority_level]


def get_authority(doc_id: str) -> dict:
    return DOC_AUTHORITY[doc_id]
