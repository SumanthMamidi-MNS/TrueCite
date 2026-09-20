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

## Third sourcing pass (2026-09-20) — Phase 10 domain corpus

Sourced against the full problem statement (`docs/PRD.md`), which names the GI,
Trade Marks, Designs, Copyright and Plant-Variety regimes, the amended
biodiversity framework, the food/advertising regimes, and a list of
international instruments — none of which the phases 1-9 corpus covered.
Thirteen documents added, taking the corpus from 7 documents / 491 chunks to
20 documents / 1,968 chunks.

Every entry below was verified before indexing: downloads a real PDF (not an
HTML error page), extracts text (not a scan), shows no OCR-corruption
signatures, and is the document it claims to be.

| File | Title | Source | Authority | Date | Amendment currency |
|---|---|---|---|---|---|
| `raw/trade_marks_act_1999.pdf` | Trade Marks Act, 1999 (No. 47 of 1999) | [IP India](https://ipindia.gov.in/storage/uploads/docs-operator/c9e8a57e-bc94-4b93-8518-6e8729c976bf.pdf) | Act | 1999-12-30 | **As enacted — amendments NOT folded in** |
| `raw/geographical_indications_act_1999.pdf` | GI of Goods (Registration and Protection) Act, 1999 | [IP India](https://ipindia.gov.in/storage/uploads/docs-operator/5720e089-4967-408c-bc76-031d2a7fd72c.pdf) | Act | 1999-12-30 | **As enacted** |
| `raw/designs_act_2000.pdf` | Designs Act, 2000 (No. 16 of 2000) | [IP India](https://ipindia.gov.in/storage/uploads/docs-operator/b86a073f-f3f5-4484-b98c-1ca21cd846a3.pdf) | Act | 2000-05-25 | **As enacted** |
| `raw/copyright_act_1957.pdf` | Copyright Act, 1957, as amended | [IP India](https://ipindia.gov.in/storage/uploads/docs-operator/910cd3b9-98b0-4713-bbd8-db4d02f95d1c.pdf) | Act | 1957-06-04 | Consolidated (s.31D present; 174 amendment footnotes) |
| `raw/plant_varieties_act_2001.pdf` | Protection of Plant Varieties and Farmers' Rights Act, 2001 | [PPV&FR Authority](https://plantauthority.gov.in/sites/default/files/ppvfract2001.pdf) | Act | 2001-10-30 | **As enacted** |
| `raw/biological_diversity_amendment_act_2023.pdf` | Biological Diversity (Amendment) Act, 2023 | [eGazette](https://egazette.gov.in/WritereadData/2023/247815.pdf) | Act | 2023-08-03 | The amending Act itself |
| `raw/biological_diversity_rules_2024.pdf` | Biological Diversity Rules, 2024 (G.S.R. 665(E)) | [WIPO Lex IN197](https://www.wipo.int/wipolex/en/legislation/details/23135) | Rules | 2024-10-22 | As notified |
| `raw/fssai_ayurveda_aahara_regulations_2022.pdf` | FSS (Ayurveda Aahara) Regulations, 2022 | [Wayback capture of FSSAI's own notification](https://web.archive.org/web/20240526144555/https://www.fssai.gov.in/upload/notifications/2022/05/62789a20b54bdGazette_Notification_Ayurveda_Aahara_09_05_2022.pdf) | Rules | 2022-05-05 | As notified |
| `raw/trips_agreement.pdf` | WTO TRIPS Agreement | [WTO](https://www.wto.org/english/docs_e/legal_e/27-trips.pdf) | Treaty | 1994-04-15 | 1994 text; Art. 31bis amendment not reflected |
| `raw/cbd_convention.pdf` | Convention on Biological Diversity | [CBD](https://www.cbd.int/doc/legal/cbd-en.pdf) | Treaty | 1992-05-22 | Not amended |
| `raw/nagoya_protocol.pdf` | Nagoya Protocol on ABS | [CBD](https://www.cbd.int/abs/doc/protocol/nagoya-protocol-en.pdf) | Treaty | 2010-10-29 | Not amended |
| `raw/pct_treaty.pdf` | Patent Cooperation Treaty | [WIPO](https://www.wipo.int/documents/d/pct-system/docs-en-texts-pct.pdf) | Treaty | 1970-06-19 | File does not state its revision date |
| `raw/madrid_protocol.pdf` | Madrid Protocol (international marks) | [WIPO Lex](https://www.wipo.int/wipolex/en/treaties/textdetails/12603) | Treaty | 1989-06-27 | File does not state its revision date |

### Amendment currency — a real, disclosed limitation

Four of the five India Acts sourced from ipindia.gov.in are the
**as-originally-enacted** text with no amendments folded in. This was verified,
not assumed: their extracted text contains **zero** `Ins./Subs./Omitted by`
amendment footnotes, whereas the Copyright Act — the one genuinely
consolidated file — contains 174 and includes section 31D, inserted by the 2012
amendment.

The practical consequence is concrete: the Trade Marks Act copy still describes
the **Intellectual Property Appellate Board**, abolished by the Tribunals
Reforms Act, 2021, whose functions moved to the High Courts. Any procedural or
forum statement drawn from that document may be superseded.

This is recorded per-document in `src/authority.py`'s `amendment_currency`
field rather than hidden, because Layer 3's stated job is to "surface the
current authoritative version, not just the most semantically similar chunk".
A consolidated replacement for these four is the single highest-value corpus
improvement outstanding.

### Bilingual gazette handling

`biological_diversity_rules_2024` (Hindi pp.1-50, English pp.51-86) and
`fssai_ayurveda_aahara_regulations_2022` (Hindi pp.1-14, English pp.15-27) are
bilingual. Only the English pages are indexed. Pages outside the window are
**blanked rather than sliced**, so page numbers in citations still match the
source PDF — slicing would renumber every page and make a citation to "page 3"
point at page 53 of the original. The Hindi halves are retained in the source
files and are a candidate native-Hindi corpus for the multilingual phase.

### Considered and rejected in this pass

- **The Patents Rules, 2003 as amended by the Patents (Amendment) Rules, 2024.**
  Rejected again, for a different reason than in the second pass: no official
  consolidated text incorporating the 2024 amendments appears to exist.
  ipindia.gov.in offers a base text current to 21-09-2021 plus separate,
  unmerged amendment notifications (March 2024 and a later second amendment).
  Merging them ourselves would mean publishing a consolidation no authority has
  endorsed, and then citing it as law. The three component PDFs are retained
  outside the corpus for a human to judge.
- **The Drugs and Magic Remedies (Objectionable Advertisements) Act, 1954.**
  Downloaded cleanly and would have passed a text-quality check, but it is not
  the Act: the only reachable copy was a state drug-control department's
  extract with no Act number, no assent date and no enacting formula, beginning
  mid-definition, with the disease Schedule printed twice in two differing
  versions. Citing a departmental compilation as primary law is precisely the
  misrepresentation this project exists to prevent. `indiacode.nic.in` was
  returning 404 for every path tried during this pass, so no authentic copy was
  reachable. **This leaves the advertising regime named in the problem
  statement uncovered — an open gap, not a silent omission.**
- **Hague Agreement and Budapest Treaty.** Sourced and verified clean, but
  deferred rather than indexed: both print a full table of contents whose last
  entry swallows the document body, and neither yielded a usable body anchor
  within a reasonable effort. They are also the least relevant instruments here
  (international design registration; microorganism deposit), so the effort was
  better spent elsewhere. Files retained outside the corpus.

### Dead/unusable links found in this pass

- `indiacode.nic.in` — **every** handle and bitstream path tried returned the
  site's generic 404, across repeated retries. This appears to be a site-wide
  outage rather than the per-document link rot logged in earlier passes, and it
  is why the India Acts were sourced from administering-ministry sites instead.
- `legislative.gov.in/sites/default/files/A1954-21.pdf` — 404
- `fssai.gov.in/upload/notifications/2022/05/...Ayurveda_Aahara...pdf` — returns
  the site's HTML homepage rather than the PDF; the file is genuinely
  unreachable live, hence the Wayback capture of FSSAI's own file.
- WIPO Lex PDFs are served behind **signed, ~24h-expiring** CloudFront URLs.
  The direct file link would be dead for anyone following the citation, so
  `authority.py` cites the stable WIPO Lex record page instead and says why.

