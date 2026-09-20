"""Authority/date metadata for Layer 3 (temporal + authority tagging, PRD §6.2).

Hand-curated rather than regex-parsed from corpus/manifest.md's prose date
column: several of those dates are genuinely ambiguous (see notes below), and
guessing a single ISO date out of free text would be exactly the kind of
silent guess this project's core design principle says not to make. Small
enough (7 docs) that keeping this in sync with manifest.md by hand is low
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
AUTH_LEVEL_RULES = "Rules"
AUTH_LEVEL_TREATY = "Treaty"
AUTH_LEVEL_IPO_GUIDELINE = "IPO Guideline"
AUTH_LEVEL_INFORMATIONAL = "Informational"

# Rules sit below the Act they are made under but above guidance, because they
# are binding subordinate legislation. Treaties sit below both for an Indian
# question: India is dualist, so a treaty binds the state internationally but
# is not directly enforceable domestically without implementing legislation.
# For an international-jurisdiction question the treaty IS the primary text --
# which is what the `jurisdiction` facet below is for, so that ranking is
# applied within a jurisdiction rather than across one.
_RANK = {
    AUTH_LEVEL_ACT: 5,
    AUTH_LEVEL_RULES: 4,
    AUTH_LEVEL_TREATY: 3,
    AUTH_LEVEL_IPO_GUIDELINE: 2,
    AUTH_LEVEL_INFORMATIONAL: 1,
}

# Jurisdiction facet (problem statement: "an explicit jurisdiction switch so
# that answers are never conflated").
JURISDICTION_INDIA = "india"
JURISDICTION_INTERNATIONAL = "international"

# Regime facet, for routing a case to the IP types that actually apply. A
# document can belong to several -- TRIPS sets baselines across most of them.
REGIME_PATENT = "patent"
REGIME_TRADEMARK = "trademark"
REGIME_GI = "gi"
REGIME_DESIGN = "design"
REGIME_COPYRIGHT = "copyright"
REGIME_PVP = "plant-variety"
REGIME_TRADE_SECRET = "trade-secret"
REGIME_ABS = "abs"
REGIME_TK = "tk"
REGIME_DRUG_REGULATORY = "drug-regulatory"
REGIME_FOOD = "food-cosmetic"

# `amendment_currency` records how current a text is, and is REQUIRED on every
# entry. Several sourced Acts turned out to be as-originally-enacted with no
# amendments folded in -- verified by counting "Ins./Subs./Omitted by" footnotes
# in the extracted text, not assumed. The Trade Marks Act copy still describes
# the Appellate Board, abolished in 2021. Layer 3 exists to "surface the current
# authoritative version, not just the most semantically similar chunk", so a
# stale text has to announce itself rather than be cited as if current.

# doc_id -> metadata. doc_id matches the stem used throughout src/ (see
# src/run_phase1.py's ALL_DOCS), not the manifest.md "File" column's path.
DOC_AUTHORITY: dict[str, dict] = {
    "patents_act_1970": {
        "short_name": "Patents Act, 1970",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_PATENT],
        "amendment_currency": "Consolidated: IP India's text states 'incorporating all amendments till 1-08-2024'.",
        "title": "The Patents Act, 1970 (No. 39 of 1970), incorporating all amendments",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "2024-08-01",
        "date_precision": "day",
        "date_note": "IP India's consolidated text is 'incorporating all amendments till 1-08-2024' — this is the text's currency date, not the original 1970 enactment date.",
        "source_url": "https://ipindia.gov.in/frontend/pdf/patents/1_113_1_The_Patents_Act__1970___incorporating_all_amendments_till_1-08-2024.pdf",
    },
    "ipo_tk_biological_material_guidelines_2012": {
        "short_name": "IPO TK & Biological Material Guidelines (2012)",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_PATENT, REGIME_ABS, REGIME_TK],
        "amendment_currency": "Guidance document; issued 2012 and not since reissued.",
        "title": "Guidelines for Processing of Patent Applications relating to Traditional Knowledge and Biological Material",
        "authority_level": AUTH_LEVEL_IPO_GUIDELINE,
        "effective_date": "2012-11-08",
        "date_precision": "day",
        "date_note": "Issuance date reported in secondary legal-commentary sources found during corpus sourcing (Lexology); not printed on the PDF itself.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/220f0e1c-1301-4f0f-84a0-6709fa66c592.pdf",
    },
    "ipo_ayush_examination_guidelines_2025": {
        "short_name": "IPO AYUSH Examination Guidelines (2025)",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_PATENT, REGIME_TK],
        "amendment_currency": "Current guidance as sourced; no later revision found.",
        "title": "Guidelines for Examination of AYUSH-Related Inventions",
        "authority_level": AUTH_LEVEL_IPO_GUIDELINE,
        "effective_date": "2025-09-23",
        "date_precision": "day",
        "date_note": "Legal-commentary sources report release on National Ayurveda Day, 2025-09-23. IP India's own guidelines-listing page shows a 'Publish Date' of 29/04/2026 for this file, which is inconsistent (likely a site re-index/re-upload date, not the original issuance date) — flagged, not silently resolved. If this matters for a specific answer, both dates should be surfaced.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/335e2746-58c1-4b56-a1e5-cdd172a92a3c.pdf",
    },
    "wipo_documenting_tk_toolkit": {
        "short_name": "WIPO TK Documentation Toolkit",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_TK],
        "amendment_currency": "2017 publication, based on a 2012 consultation draft; not a legal instrument.",
        "title": "Documenting Traditional Knowledge and Traditional Cultural Expressions — A Toolkit",
        "authority_level": AUTH_LEVEL_INFORMATIONAL,
        "effective_date": "2017-01-01",
        "date_precision": "year",
        "date_note": "PDF's own copyright page: '© WIPO, 2017. Based on a consultation draft published in 2012.' Day/month unknown, hence year-only precision (Jan 1 is a placeholder, not a real publish date).",
        "source_url": "https://www.wipo.int/edocs/pubdocs/en/wipo_pub_1049.pdf",
    },
    "pib_faq_patents_traditional_ayurvedic_medicine_2013": {
        "short_name": "PIB Press Release (2013)",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_PATENT, REGIME_TK],
        "amendment_currency": "Point-in-time press release; its figures are as of March 2013 and are not updated.",
        "title": "\"Patents to Traditional Ayurvedic Medicine\" — Press Information Bureau release",
        "authority_level": AUTH_LEVEL_INFORMATIONAL,
        "effective_date": "2013-08-12",
        "date_precision": "day",
        "date_note": "Date printed directly on the release itself.",
        "source_url": "https://www.pib.gov.in/newsite/printrelease.aspx?relid=98021",
    },
    "biological_diversity_act_2002": {
        "short_name": "Biological Diversity Act, 2002",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_ABS],
        "amendment_currency": "As enacted 2002. The 2023 amendment Act is indexed separately as biological_diversity_amendment_act_2023 and MUST be read with it -- this text alone is stale.",
        "title": "The Biological Diversity Act, 2002 (No. 18 of 2003)",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "2003-02-05",
        "date_precision": "day",
        "date_note": "Date of Presidential assent, printed on the Act itself. Different sections actually "
        "commenced on different later dates (1 October 2003 and 1 July 2004, per secondary sources) — "
        "assent date is used here, consistent with how this project already uses a single "
        "representative date per document rather than per-section commencement dates.",
        "source_url": "https://hpbiodiversity.gov.in/BMC/BiodiverstyAct2002english.pdf",
    },
    "wipo_gratk_treaty_2024": {
        "short_name": "WIPO GRATK Treaty (2024, not yet in force)",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_PATENT, REGIME_ABS, REGIME_TK],
        "amendment_currency": "Adopted 2024-05-24, NOT yet in force (needs 15 ratifications).",
        "title": "WIPO Treaty on Intellectual Property, Genetic Resources and Associated Traditional Knowledge",
        "authority_level": AUTH_LEVEL_INFORMATIONAL,
        "effective_date": "2024-05-24",
        "date_precision": "day",
        "date_note": "This is the ADOPTION date (printed on the treaty text itself), not an in-force date — "
        "the treaty requires 15 ratifications/accessions to enter into force, which had not happened as "
        "of this corpus's sourcing. Deliberately tagged Informational rather than Act despite being a "
        "real treaty text, and the short_name says so explicitly, so it can never be cited as binding "
        "Indian law ahead of Act/Guideline sources on the same point.",
        "source_url": "https://www.wipo.int/edocs/mdocs/tk/en/gratk_dc/gratk_dc_7.pdf",
    },
    "trade_marks_act_1999": {
        "short_name": "Trade Marks Act, 1999",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_TRADEMARK],
        "amendment_currency": "AS ENACTED 1999 -- later amendments NOT incorporated. Verified: zero "
        "\"Ins./Subs./Omitted by\" amendment footnotes in the extracted text, and the text still "
        "describes the Intellectual Property Appellate Board, abolished by the Tribunals Reforms Act, "
        "2021. Treat procedural/forum statements from this document as potentially superseded.",
        "title": "The Trade Marks Act, 1999 (No. 47 of 1999)",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "1999-12-30",
        "date_precision": "day",
        "date_note": "Date of Presidential assent. The sourced PDF does not print an assent line that "
        "survived text extraction (its first page extracts empty), so this date comes from the Act's "
        "well-established enactment record rather than from the file itself -- flagged as such.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/c9e8a57e-bc94-4b93-8518-6e8729c976bf.pdf",
    },
    "geographical_indications_act_1999": {
        "short_name": "GI of Goods Act, 1999",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_GI],
        "amendment_currency": "AS ENACTED 1999 -- later amendments NOT incorporated (zero amendment "
        "footnotes in the extracted text).",
        "title": "The Geographical Indications of Goods (Registration and Protection) Act, 1999 (No. 48 of 1999)",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "1999-12-30",
        "date_precision": "day",
        "date_note": "Assent date printed on the Act itself: '[30th December, 1999]'.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/5720e089-4967-408c-bc76-031d2a7fd72c.pdf",
    },
    "designs_act_2000": {
        "short_name": "Designs Act, 2000",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_DESIGN],
        "amendment_currency": "AS ENACTED 2000 -- later amendments NOT incorporated (zero amendment "
        "footnotes in the extracted text).",
        "title": "The Designs Act, 2000 (No. 16 of 2000)",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "2000-05-25",
        "date_precision": "day",
        "date_note": "Assent date printed on the Act itself: '[25th May, 2000]'.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/b86a073f-f3f5-4484-b98c-1ca21cd846a3.pdf",
    },
    "copyright_act_1957": {
        "short_name": "Copyright Act, 1957",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_COPYRIGHT],
        "amendment_currency": "CONSOLIDATED -- amendments are folded in. Verified: 174 "
        "\"Ins./Subs./Omitted by\" footnotes present, and section 31D (inserted by the 2012 "
        "amendment) appears in the text. The only one of the sourced India Acts that is current.",
        "title": "The Copyright Act, 1957 (No. 14 of 1957), as amended",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "1957-06-04",
        "date_precision": "day",
        "date_note": "Assent date printed on the Act itself: '[4th June, 1957]'. This is the original "
        "enactment date, not the currency of the amendments folded in -- see amendment_currency.",
        "source_url": "https://ipindia.gov.in/storage/uploads/docs-operator/910cd3b9-98b0-4713-bbd8-db4d02f95d1c.pdf",
    },
    "plant_varieties_act_2001": {
        "short_name": "Plant Varieties & Farmers' Rights Act, 2001",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_PVP],
        "amendment_currency": "AS ENACTED 2001 -- later amendments NOT incorporated (zero amendment "
        "footnotes in the extracted text).",
        "title": "The Protection of Plant Varieties and Farmers' Rights Act, 2001 (No. 53 of 2001)",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "2001-10-30",
        "date_precision": "day",
        "date_note": "Assent date printed on the Act itself: '[30th October, 2001]'.",
        "source_url": "https://plantauthority.gov.in/sites/default/files/ppvfract2001.pdf",
    },
    "biological_diversity_amendment_act_2023": {
        "short_name": "Biological Diversity (Amendment) Act, 2023",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_ABS],
        "amendment_currency": "The amending Act itself, as enacted 2023. Amends the 2002 Act, which is "
        "indexed separately -- neither document states the combined current text, so answers about "
        "current ABS obligations should cite both.",
        "title": "The Biological Diversity (Amendment) Act, 2023 (No. 10 of 2023)",
        "authority_level": AUTH_LEVEL_ACT,
        "effective_date": "2023-08-03",
        "date_precision": "day",
        "date_note": "Assent date printed on the Act itself: '[3rd August, 2023.]', confirmed by its "
        "own assent line. Commencement was left to Central Government notification.",
        "source_url": "https://egazette.gov.in/WritereadData/2023/247815.pdf",
    },
    "biological_diversity_rules_2024": {
        "short_name": "Biological Diversity Rules, 2024",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_ABS],
        "amendment_currency": "As notified 2024-10-22; no later amendment found.",
        "title": "The Biological Diversity Rules, 2024 (G.S.R. 665(E))",
        "authority_level": AUTH_LEVEL_RULES,
        "effective_date": "2024-10-22",
        "date_precision": "day",
        "date_note": "Notification date printed in the gazette text itself, alongside 'G.S.R. 665(E)'.",
        "source_url": "https://www.wipo.int/wipolex/en/legislation/details/23135",
        "source_note": "Cited as the stable WIPO Lex record (WIPO Lex No. IN197). The actual PDF is "
        "served from WIPO Lex behind a signed, ~24h-expiring CloudFront URL, so the direct file link "
        "would be dead on arrival for anyone following the citation. No ministry/NBA hosting of this "
        "instrument was found. Bilingual gazette: Hindi pp.1-50, English pp.51-86; only the English "
        "pages are indexed (see run_phase1.ALL_DOCS).",
    },
    "fssai_ayurveda_aahara_regulations_2022": {
        "short_name": "FSSAI Ayurveda Aahara Regulations, 2022",
        "jurisdiction": JURISDICTION_INDIA,
        "regimes": [REGIME_FOOD],
        "amendment_currency": "As notified 2022-05-05; no later amendment found.",
        "title": "Food Safety and Standards (Ayurveda Aahara) Regulations, 2022",
        "authority_level": AUTH_LEVEL_RULES,
        "effective_date": "2022-05-05",
        "date_precision": "day",
        "date_note": "Notification date printed in the gazette text itself, in both Hindi "
        "('5 \u092e\u0908, 2022') and English ('5th May, 2022').",
        "source_url": "https://web.archive.org/web/20240526144555/https://www.fssai.gov.in/upload/notifications/2022/05/62789a20b54bdGazette_Notification_Ayurveda_Aahara_09_05_2022.pdf",
        "source_note": "Cited via a Wayback capture (2024-05-26) of FSSAI's OWN notification PDF: the "
        "live fssai.gov.in URL now redirects to the site's homepage rather than serving the file. "
        "Content originates from FSSAI, not a third party. Bilingual gazette: Hindi pp.1-14, English "
        "pp.15-27; only the English pages are indexed.",
    },
    "trips_agreement": {
        "short_name": "TRIPS Agreement (WTO)",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_PATENT, REGIME_TRADEMARK, REGIME_GI, REGIME_DESIGN,
                    REGIME_COPYRIGHT, REGIME_TRADE_SECRET],
        "amendment_currency": "Text as adopted 1994. The 2005/2017 Article 31bis amendment on "
        "compulsory licensing for export is NOT reflected in this copy.",
        "title": "Agreement on Trade-Related Aspects of Intellectual Property Rights",
        "authority_level": AUTH_LEVEL_TREATY,
        "effective_date": "1994-04-15",
        "date_precision": "day",
        "date_note": "Adoption date at Marrakesh, confirmed in the document's own text. Note that this "
        "PDF also cites 1961 (Rome) and 1989 (Washington) dates for OTHER conventions it references -- "
        "those are not TRIPS' own date and must not be read as such.",
        "source_url": "https://www.wto.org/english/docs_e/legal_e/27-trips.pdf",
    },
    "cbd_convention": {
        "short_name": "Convention on Biological Diversity",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_ABS, REGIME_TK],
        "amendment_currency": "Text as adopted 1992; the CBD itself has not been amended.",
        "title": "Convention on Biological Diversity (1992)",
        "authority_level": AUTH_LEVEL_TREATY,
        "effective_date": "1992-05-22",
        "date_precision": "day",
        "date_note": "Adoption date at Nairobi, printed in the document ('adopted 22 May 1992'). It "
        "opened for signature at Rio on 1992-06-05 and entered into force 1993-12-29; the adoption "
        "date is used here for consistency with how other instruments in this corpus are dated.",
        "source_url": "https://www.cbd.int/doc/legal/cbd-en.pdf",
    },
    "nagoya_protocol": {
        "short_name": "Nagoya Protocol (ABS)",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_ABS, REGIME_TK],
        "amendment_currency": "Text as adopted 2010; not amended.",
        "title": "Nagoya Protocol on Access to Genetic Resources and the Fair and Equitable Sharing of Benefits",
        "authority_level": AUTH_LEVEL_TREATY,
        "effective_date": "2010-10-29",
        "date_precision": "day",
        "date_note": "Adoption date printed in the document ('29 October 2010'). Entered into force "
        "2014-10-12.",
        "source_url": "https://www.cbd.int/abs/doc/protocol/nagoya-protocol-en.pdf",
    },
    "pct_treaty": {
        "short_name": "Patent Cooperation Treaty",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_PATENT],
        "amendment_currency": "PCT as modified through the sourced WIPO text; WIPO revises this "
        "periodically and the file does not state its own revision date.",
        "title": "Patent Cooperation Treaty (1970)",
        "authority_level": AUTH_LEVEL_TREATY,
        "effective_date": "1970-06-19",
        "date_precision": "day",
        "date_note": "Signature date printed in the treaty text ('Done at Washington on June 19, 1970').",
        "source_url": "https://www.wipo.int/documents/d/pct-system/docs-en-texts-pct.pdf",
    },
    "madrid_protocol": {
        "short_name": "Madrid Protocol (trade marks)",
        "jurisdiction": JURISDICTION_INTERNATIONAL,
        "regimes": [REGIME_TRADEMARK],
        "amendment_currency": "Text as adopted 1989, with WIPO's subsequent modifications as reflected "
        "in the sourced file; the file does not state its own revision date.",
        "title": "Protocol Relating to the Madrid Agreement Concerning the International Registration of Marks",
        "authority_level": AUTH_LEVEL_TREATY,
        "effective_date": "1989-06-27",
        "date_precision": "day",
        "date_note": "Adoption date printed in the text ('adopted at Madrid on June 27, 1989').",
        "source_url": "https://www.wipo.int/wipolex/en/treaties/textdetails/12603",
        "source_note": "Cited as the stable WIPO Lex record: the PDF is served behind a signed, "
        "~24h-expiring CloudFront URL, so a direct file link would not resolve for a reader.",
    },
}


def authority_rank(authority_level: str) -> int:
    return _RANK[authority_level]


def get_authority(doc_id: str) -> dict:
    return DOC_AUTHORITY[doc_id]
