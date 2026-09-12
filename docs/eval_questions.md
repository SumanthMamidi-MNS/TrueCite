# Evaluation question set — DRAFT (prep for Phase 6)

Written ahead of Phase 6 while Phase 2's embedding build ran in the background —
pure content authoring against documents already read during Phase 1, no
pipeline dependency. Not yet run through the system; "expected" answers below
are hand-authored ground truth from the source documents, for later scoring
citation accuracy / refusal rate / false-refusal rate once Phases 4-6 exist.

Known gap: PRD §6.3 requires Hindi support "at minimum," but the corpus is
currently English-only (see docs/decisions.md corpus-scope note) — so the
multilingual questions below are placeholders, not yet answerable by this
corpus. Flagging rather than faking results for them.

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
   **Source:** `ipo_tk_biological_material_guidelines_2012`, `pib_faq_patents_traditional_ayurvedic_medicine_2013::para-3`

10. **Q:** What is the penalty under the Biological Diversity Act, 2002 for contravening its access provisions?
    **Expected:** Imprisonment up to 5 years, or a fine up to ten lakh rupees (higher if damage caused exceeds ten lakh rupees), per Section 55(1).
    **Source:** `ipo_tk_biological_material_guidelines_2012`

## B. Answerable — requires synthesizing across 2+ documents

11. **Q:** If a company wants to patent an Ayurvedic herbal formulation, what two separate legal regimes must they satisfy?
    **Expected:** (a) Patents Act, 1970 novelty/inventive-step/non-TK requirements (esp. §3(p)), and (b) Biological Diversity Act, 2002 prior-approval requirements from the National Biodiversity Authority.
    **Source:** `patents_act_1970::sec-3`, `ipo_tk_biological_material_guidelines_2012`, `ipo_ayush_examination_guidelines_2025`

12. **Q:** How does India's approach to protecting traditional knowledge in patent law interact with its TRIPS obligations?
    **Expected:** TRIPS requires national treatment (no less favorable treatment of foreign applicants), so India cannot restrict Ayurvedic-medicine patents to Indian companies only — but non-patentability grounds like §3(p) apply equally regardless of applicant nationality.
    **Source:** `pib_faq_patents_traditional_ayurvedic_medicine_2013::para-3`

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

    *Note:* We don't yet have a genuine two-version conflict (e.g., an actually superseded rule with two different documents stating different rules). Need to construct one explicitly before Phase 5, or accept this category is thin given current corpus scope — flag to user rather than force a contrived example.

## E. Multilingual — BLOCKED, corpus is English-only

20. **Q (Hindi):** क्या पारंपरिक ज्ञान पर भारत में पेटेंट लिया जा सकता है? (Can traditional knowledge be patented in India?)
    **Status:** Cannot be meaningfully evaluated — no Hindi source documents in the corpus yet. bge-m3 is multilingual and may retrieve *something* via cross-lingual embedding similarity, but there is no Hindi ground truth to verify against.

21-24. *(Reserved — add once Hindi-language source documents are added to the corpus, per PRD §6.3's requirement to verify retrieval quality per language independently.)*

---

**Count so far: 19 concrete + 5 reserved = 24, within PRD's 20-30 target.**
**Still needed before Phase 6 can actually run:** Hindi corpus documents (category E), and a decision on whether to construct a synthetic version-conflict pair for category D or accept the corpus doesn't currently exercise that failure mode.
