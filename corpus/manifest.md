# Corpus manifest — Phase 1

Each entry: file, title, source, authority level (Act > Ministry/IPO Guideline > Informational), effective/publish date.

| File | Title | Source | Authority level | Effective / publish date |
|---|---|---|---|---|
| `raw/patents_act_1970.pdf` | The Patents Act, 1970 (No. 39 of 1970), incorporating all amendments | [IP India](https://ipindia.gov.in/frontend/pdf/patents/1_113_1_The_Patents_Act__1970___incorporating_all_amendments_till_1-08-2024.pdf) | Act (highest) | Amendments through 2024-08-01 |
| `raw/ipo_tk_biological_material_guidelines_2012.pdf` | Guidelines for Processing of Patent Applications relating to Traditional Knowledge and Biological Material | [IP India](https://ipindia.gov.in/storage/uploads/docs-operator/220f0e1c-1301-4f0f-84a0-6709fa66c592.pdf) | IPO Guideline | 2012 |
| `raw/ipo_ayush_examination_guidelines_2025.pdf` | Guidelines for Examination of AYUSH-Related Inventions | [IP India](https://ipindia.gov.in/storage/uploads/docs-operator/335e2746-58c1-4b56-a1e5-cdd172a92a3c.pdf) | IPO Guideline | 2025 (published 2026-04-29 per site) |
| `raw/wipo_documenting_tk_toolkit.pdf` | Documenting Traditional Knowledge and Traditional Cultural Expressions — A Toolkit | [WIPO](https://www.wipo.int/edocs/pubdocs/en/wipo_pub_1049.pdf) | Informational (not primary TK content — the actual TKDL database is restricted to patent offices under NDA, not public) | WIPO publication |
| `raw/pib_faq_patents_traditional_ayurvedic_medicine_2013.txt` | "Patents to Traditional Ayurvedic Medicine" — Press Information Bureau release, Ministry of Commerce & Industry | [PIB](https://www.pib.gov.in/newsite/printrelease.aspx?relid=98021) | FAQ / informational | 2013-08-12 |
| `raw/biological_diversity_act_2002.pdf` | The Biological Diversity Act, 2002 (No. 18 of 2003) | [HP State Biodiversity Board](https://hpbiodiversity.gov.in/BMC/BiodiverstyAct2002english.pdf) (central `indiacode.nic.in`/`indiacode.gov.in` links were dead at sourcing time — see below) | Act (highest) | Assented 2003-02-05 |
| `raw/wipo_gratk_treaty_2024.pdf` | WIPO Treaty on Intellectual Property, Genetic Resources and Associated Traditional Knowledge | [WIPO](https://www.wipo.int/edocs/mdocs/tk/en/gratk_dc/gratk_dc_7.pdf) (GRATK/DC/7, the diplomatic conference's own adopted-text document) | Informational — adopted 2024-05-24 but **not yet in force** (needs 15 ratifications); deliberately tagged below Act/Guideline, see `src/authority.py` | Adopted 2024-05-24 |

## Second sourcing pass (2026-09-13)

Added while reviewing corpus completeness against a real gap found during UI testing: the Biological Diversity Act's actual penalty provision (§55) had only ever been indexed secondhand, via the 2012 IPO guideline's summary of it. Also added the WIPO GRATK Treaty to cover the "international regimes" half of the PRD's own problem statement, previously unrepresented in the corpus.

**Considered and rejected**: The Patents Rules, 2003 and the Patents (Amendment) Rules, 2024 (which would have given the system real filing-fee/procedural content, and a genuine two-version authority-conflict test case). ipindia.gov.in's own hosting of these had been restructured (dead links, consistent with the dead links already logged below from Phase 1). The best available mirror found (WIPO Lex) turned out to be a scanned/OCR'd copy of the 2003 base rules with real word-level corruption ("Govemment", "MINlSTRY", "lIt;", digit/letter confusion) — unacceptable for a system whose entire premise is trustworthy citation, especially for a document whose main value would be exact fee figures. Rather than index visibly-corrupted legal text, this was dropped; flagged to the user as a gap that would need a cleaner source (ideally ipindia.gov.in's own current HTML "e-version," not found at a stable URL during this pass) before it's worth adding.

## Known limitation

The PRD's Data Plan calls for "WIPO TKDL public materials," but the TKDL database itself is not public — access is restricted to patent offices under a non-disclosure agreement. The WIPO toolkit above is the closest public substitute (describes TK documentation/classification approach) and is tagged at a lower authority level accordingly. Document this limitation in the Phase 7 README.

## Dead links encountered while sourcing (for reference, not used)

- `indiacode.nic.in/bitstream/.../A1970-39.pdf` — 404
- `www.ipindia.gov.in/writereaddata/Portal/IPOGuidelinesManuals/1_39_1_5-tk-guidelines.pdf` — 404 (old path; IP India restructured their site)
- `main.ayush.gov.in/.../faq/...` — domain/path no longer resolves (site restructured)
- `indiacode.nic.in/bitstream/123456789/2046/1/200318.pdf` and `/handle/123456789/2046` — 404/500 (2026-09-13; central India Code migrated to indiacode.gov.in, old bitstream paths broken)
- `ipindia.gov.in/writereaddata/Portal/IPORule/1_70_1_The-Patents-Rules-2003-Updated-till-23-June-2017.pdf` and `1_83_1_Patent_Amendment_Rule_2024_Gazette_Copy.pdf` — 404 (2026-09-13; same IP India restructuring pattern as the Phase 1 dead links above)
- WIPO Lex mirror of the Patents Rules, 2003 (`wipolex-res.wipo.int/edocs/lexdocs/laws/en/in/in016en.pdf`) — resolves, but is a scanned/OCR'd copy with real text corruption; rejected on quality grounds, see "Second sourcing pass" above
