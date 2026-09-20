# Evaluation question set — DRAFT (prep for Phase 6)

Written ahead of Phase 6 while Phase 2's embedding build ran in the background —
pure content authoring against documents already read during Phase 1, no
pipeline dependency. Not yet run through the system; "expected" answers below
are hand-authored ground truth from the source documents, for later scoring
citation accuracy / refusal rate / false-refusal rate once Phases 4-6 exist.

PRD §6.3 requires Hindi support "at minimum." The corpus is English-only, but
category E is no longer blocked by that: a Hindi question and its English twin
should retrieve the *same* source chunks, so the English ground truth below is
also the Hindi ground truth. Cross-lingual retrieval is measured that way
(2026-09-20) — see category E.

## A. Answerable — strong single-document support

1. **Q:** Can an invention that is essentially traditional knowledge be patented in India?
   **Expected:** No — refused under Section 3(p) of the Patents Act, 1970 ("an invention which, in effect, is traditional knowledge... is not patentable").
   **Source:** `patents_act_1970::sec-3`

2. **Q:** What must a patent applicant do if their invention uses biological material sourced from India?
   **Expected:** Obtain prior approval from the National Biodiversity Authority under the Biological Diversity Act, 2002 (approval may follow acceptance but must precede sealing of the patent); also file a declaration on Form-1 under the Patent Rules, 2003.
   **Source:** `ipo_tk_biological_material_guidelines_2012` (paragraphs on Form-1 declaration), corroborated by `pib_faq_patents_traditional_ayurvedic_medicine_2013::para-3`

3. **Q:** What database do patent examiners use to check for prior art in traditional Indian medicine?
   **Expected:** The Traditional Knowledge Digital Library (TKDL), plus other databases (e.g. via e-Charak portal / Tribal Digital Document Repository per the AYUSH-2025 guidelines).
   **Source:** `ipo_tk_biological_material_guidelines_2012::preamble`, `ipo_ayush_examination_guidelines_2025`

4. **Q:** As of March 2013, how many patents had been granted to Indian entities for Ayurvedic-medicine-related inventions?
   **Expected:** 93 patents (out of 523 applications filed by Indian entities); 26 patents had been granted to foreign entities (out of 86 applications).
   **Source:** `pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2`

5. **Q:** What systems of medicine does "AYUSH" cover?
   **Expected:** Ayurveda, Yoga & Naturopathy, Unani, Siddha, Sowa-Rigpa, and Homoeopathy.
   **Source:** `ipo_ayush_examination_guidelines_2025::preamble`

6. **Q:** What happens if a patent applicant wrongly discloses the geographical origin of biological material used in their invention?
   **Expected:** Grounds for refusal under Section 15, and grounds for pre-grant opposition (Section 25(1)) or post-grant opposition/revocation (Section 25(2)) of the Patents Act.
   **Source:** `patents_act_1970::sec-25-sub-1`/`sec-25-sub-2`, `ipo_ayush_examination_guidelines_2025`

7. **Q:** Is a mere discovery of a new property of a known substance patentable in India?
   **Expected:** No — excluded under Section 3(d) unless it results in enhancement of known efficacy of that substance.
   **Source:** `patents_act_1970::sec-3`

8. **Q:** What are the three phases the WIPO toolkit divides TK documentation into?
   **Expected:** Before documentation, during documentation, and after documentation.
   **Source:** `wipo_documenting_tk_toolkit`

9. **Q:** Under what section of the Biological Diversity Act, 2002 must approval be sought before filing a patent application based on Indian biological resources?
   **Expected:** Section 6(1).
   **Source:** `biological_diversity_act_2002::sec-6` (2026-09-13: now indexed directly — previously only answerable via secondhand mentions in `ipo_tk_biological_material_guidelines_2012` / `pib_faq_patents_traditional_ayurvedic_medicine_2013::para-3`, both still valid corroborating sources).

10. **Q:** What is the penalty under the Biological Diversity Act, 2002 for contravening its access provisions?
    **Expected:** Imprisonment up to 5 years, or a fine up to ten lakh rupees (higher if damage caused exceeds ten lakh rupees), per Section 55(1).
    **Source:** `biological_diversity_act_2002::sec-55` (2026-09-13: this is the real gap found live during UI testing — the system had only ever been able to cite the 2012 guideline's *summary* of this penalty, not the Act itself; now it can cite the primary source directly, and Layer 3 should prefer it over the guideline when both are retrieved).

10a. **Q:** What does the new WIPO treaty on genetic resources and traditional knowledge require a patent applicant to disclose?
    **Expected:** Where a claimed invention is based on genetic resources (and/or associated traditional knowledge), the applicant must disclose the country of origin (or source) of the genetic resources / the Indigenous Peoples or local community providing the associated TK — per Article 3 of the WIPO Treaty on IP, Genetic Resources and Associated Traditional Knowledge (2024). A correct answer should also flag that this treaty is **adopted but not yet in force** (needs 15 ratifications) — treating it as binding Indian law today would be a real overstatement error, exactly the kind of thing Layer 3's authority tagging exists to prevent (tagged Informational, not Act, for this reason — see `src/authority.py`).
    **Source:** `wipo_gratk_treaty_2024::article-3`
    **Observed (2026-09-13, live-tested):** Currently refuses across every phrasing tried, including one naming "Article 3" directly. Article 3 is correctly retrieved every time, but the local model repeatedly drafts a claim describing the *other* WIPO document in this corpus (the TK documentation toolkit) instead, and Layer 2 correctly rejects the resulting mismatch. Zero false answers observed — the honest failure mode here is over-refusal, not fabrication — but this question should not be expected to cleanly succeed until a stronger generation model is available. See `docs/decisions.md`.

## B. Answerable — requires synthesizing across 2+ documents

11. **Q:** If a company wants to patent an Ayurvedic herbal formulation, what two separate legal regimes must they satisfy?
    **Expected:** (a) Patents Act, 1970 novelty/inventive-step/non-TK requirements (esp. §3(p)), and (b) Biological Diversity Act, 2002 prior-approval requirements from the National Biodiversity Authority.
    **Source:** `patents_act_1970::sec-3`, `ipo_tk_biological_material_guidelines_2012`, `ipo_ayush_examination_guidelines_2025`

12. **Q:** How does India's approach to protecting traditional knowledge in patent law interact with its TRIPS obligations?
    **Expected:** TRIPS requires national treatment (no less favorable treatment of foreign applicants), so India cannot restrict Ayurvedic-medicine patents to Indian companies only — but non-patentability grounds like §3(p) apply equally regardless of applicant nationality.
    **Source:** `pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2` (2026-09-16: corrected from `::para-3` — a transcription error; `::para-3` discusses Biological Diversity Act §6 approval and never mentions TRIPS at all, while the actual TRIPS/national-treatment discussion is in `::para-2`. Found while building `src/run_retrieval_eval.py`'s gold table and verified by reading both chunks directly.)

## C. Deliberately unanswerable (must refuse, not guess)

13. **Q:** What is the current government filing fee for a patent application in India?
    **Expected:** Refuse — no fee schedule document is in this corpus.

14. **Q:** How does the European Patent Office treat traditional-knowledge-based patent applications?
    **Expected:** Refuse — corpus is India-focused; no EPO material included.

15. **Q:** What was the outcome of the Neem patent case (EPO opposition)?
    **Expected:** Refuse — no case-law documents in this corpus.

16. **Q:** What is the process for appealing a Controller's decision to the High Court?
    **Expected:** Partially answerable at best (Chapter XIX of the Act covers appeals generally) but specific procedural detail may exceed what's chunked/retrievable — good boundary case for testing over-confident vs. appropriately-hedged answers.

17. **Q:** Can a company patent a yoga asana (posture) sequence in the United States?
    **Expected:** Refuse — corpus has no US patent law material.

## D. Authority / temporal-conflict candidates (Phase 5 Layer 3 test cases)

18. **Q:** Which document governs the examination of AYUSH-related patent applications — the 2012 TK/Biological Material guidelines or the 2025 AYUSH Examination guidelines?
    **Expected:** Both remain relevant — the 2025 guidelines explicitly complement (not replace) the 2012 guidelines. A correct answer should cite both, tagged with their respective dates, not silently pick one. Good test of "surface the current authoritative version" logic when the true answer is "both, layered" rather than a clean supersession.
    **Source:** `ipo_ayush_examination_guidelines_2025`, `ipo_tk_biological_material_guidelines_2012`

19. **Q:** What amendments have been made to Section 3 of the Patents Act, and when?
    **Expected:** Tests whether the system surfaces the current (amended) text as authoritative rather than confusing itself with the amendment-footnote apparatus stripped out during chunking (see `docs/decisions.md` — footnote text was deliberately removed from chunk bodies).
    **Source:** `patents_act_1970::sec-3`

    *Note:* We don't yet have a genuine two-version conflict (e.g., an actually superseded rule with two different documents stating different rules). Still true as of the 2026-09-13 corpus expansion — a real candidate pair existed (the Patents Rules, 2003 base text and the Patents (Amendment) Rules, 2024) but the only available mirror of the 2003 base text was a corrupted OCR scan and was rejected on quality grounds (see `corpus/manifest.md`). Need a clean source for one of these before this category stops being thin — flag to user rather than force a contrived example.

## E. Multilingual — cross-lingual retrieval, measured 2026-09-20

Method: each question is asked in Hindi and in English, and both are expected to
retrieve the same source document. The English ground truth in section A serves
as the Hindi ground truth, so no Hindi corpus is required to measure this. What
is measured is whether a Hindi speaker reaches the same sources an English
speaker does — which is what PRD §6.3's "verify retrieval quality per language
independently" actually asks.

Result over the ten section-A pairs (`top_k=5`, hybrid retrieval):

| | Expected source in top-5 | Mean EN/HI top-5 chunk overlap |
|---|---|---|
| English (control) | 9/10 | — |
| Hindi | 8/10 | 3.1/5 |

Found and fixed while measuring this: BM25 returned `top_k` arbitrary chunks in
corpus order for any query matching nothing, and hybrid fusion weights by rank
rather than score, so those chunks entered every Hindi result at full weight.
Hindi went 7/10 → 8/10 and overlap 2.3/5 → 3.1/5 once BM25 was made to abstain
instead (see docs/decisions.md). English was unchanged at 9/10, as expected —
English queries always had real BM25 matches.

20. **Q (Hindi):** क्या ऐसा आविष्कार जो मूलतः पारंपरिक ज्ञान है, भारत में पेटेंट कराया जा सकता है?
    **Expected:** Same as A1 — `patents_act_1970::sec-3`.
    **Status:** MISS in both languages. A pre-existing English retrieval weakness
    (A1 also misses), not a cross-lingual one — worth separating from the Hindi result.

21. **Q (Hindi):** यदि पेटेंट आवेदक अपने आविष्कार में प्रयुक्त जैविक सामग्री के भौगोलिक स्रोत का गलत खुलासा करता है, तो क्या होगा?
    **Expected:** Same as A6 — `patents_act_1970::sec-25-sub-1`/`sec-25-sub-2`.
    **Status:** HIT in English, MISS in Hindi. The one genuine cross-lingual
    degradation left; cross-lingual embeddings capture topic but lose the
    section-level specificity BM25 supplies for English.

22-24. *(Reserved — for native Hindi source documents, which would test something
this method cannot: retrieval quality *within* Hindi rather than across languages.)*


---

**Count so far: 20 concrete + 5 reserved = 25, within PRD's 20-30 target.**
**Still needed:** a decision on whether to construct a synthetic version-conflict pair for category D or accept the corpus doesn't currently exercise that failure mode. (Category E's blocker is resolved — see above.)

## F. Domain regimes — end-to-end, Phase 18 (2026-09-20)

Twelve questions, one per regime added in Phase 10, plus two controls that MUST
refuse. Unlike categories A-E this measures the FULL pipeline, not retrieval:
the Phase 10 gate already established the right statute is reachable, so what
was unknown is whether the pipeline then answers from it, cites it, or refuses.

The controls are not decoration. A suite where everything is answerable cannot
detect a system that has stopped refusing, which is the failure this project
cares about most.

| | Result |
|---|---|
| Answerable questions | 12 |
| Answered | 9 |
| Cited the expected document | 9 of 9 answered |
| Controls that must refuse | 2 |
| Correct refusals | 2/2 |
| **False answers** | **0** |

The three declined (trade marks, designs, Ayurveda Aahara) all refused at Layer
2 verification rather than the Layer 1 gate — retrieval found the right statute
and Layer 2 rejected every drafted claim. Same over-strictness measured since
Phase 9, now reproduced on regimes the system had never seen. Full per-question
records: `corpus/eval_results/phase18_results.json`.

