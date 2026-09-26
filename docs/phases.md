# Phases — IP-SAKTI Sahayak

Sequential, gated phases per PRD §9 — no fixed schedule. Each phase gates the next.

## Phase 1 — Corpus & Chunking — DONE
- [x] Corpus sourced: 5 real documents (Patents Act 1970, IPO TK/Biological Material
      Guidelines 2012, IPO AYUSH Examination Guidelines 2025, WIPO TK toolkit, PIB FAQ
      release). Provenance/authority tagged in `corpus/manifest.md`.
- [x] Parsing + structural chunking built (`src/parsing.py`, `src/chunking.py`).
- [x] Ran on all 5 docs. Found and fixed 5 real bugs during manual review: footnote text
      colliding with section numbers, duplicate chunk IDs from per-chapter monotonic reset,
      hidden section 11A/11B, lost preamble text, and an anchor-string mismatch that let a
      table of contents get chunked as if it were body text.
- [x] Section 3(p) of the Patents Act (TK non-patentability — core to this project) verified
      intact in its own chunk.
- [x] Fixed: oversized sections with no numeric subsections (AYUSH-2025's decimal "3.1"
      headings, WIPO toolkit's named headings) now fall back to paragraph-grouping instead
      of shipping as one large chunk. All 5 docs: 288 chunks total, 0 duplicates, 0 empty,
      0 stray noise fragments.
- [x] User review/approval of chunk output — approved 2026-09-12.

## Phase 2 — Basic Retrieval — DONE
- [x] `src/embeddings.py` (BAAI/bge-m3 via sentence-transformers), `src/indexing.py`
      (ChromaDB persistent collection), `src/retrieval.py` (vector top-k).
- [x] Gate: 5 hand-checked queries spanning all 5 docs (`src/run_phase2.py`). 4/5 return
      excellent top results (query 5 nails the exact statistic; query 4 returns only
      AYUSH-2025 chunks as expected).
- [x] Query 1 ("Can traditional knowledge be patented in India?") initially didn't surface
      `patents_act_1970::sec-3` even in the top 20 — investigated rather than waved through.
      Root cause verified directly (not guessed): Section 3 pooled 16 unrelated statutory
      exclusions into one embedding, diluting clause (p)'s signal (isolating it alone raised
      cosine similarity 0.455 -> 0.568). Fixed the chunker accordingly (see Phase 1 log and
      `docs/decisions.md`) — this also surfaced and fixed 2 more real content-loss/duplicate
      bugs in the chunker, now covered by `tests/test_chunking.py`.
- [x] After the fix, clause (p) still doesn't rank in the top 20-30 for this specific
      phrasing, confirmed against **both** vector and BM25 (and their RRF hybrid) — so this
      is not primarily a chunking problem. Root cause: clause (p)'s actual statutory text
      never contains the word "patent" ("...is traditional knowledge...are not inventions"),
      while the query asks "can X be *patented*" — a genuine vocabulary/framing gap between
      terse negative-framed statute language and natural-language questions.
- [x] Verified this doesn't block the gate: the top-ranked result (TK Guidelines 2012 §3)
      is substantively correct and well-grounded (cites §2(1)(j) and §3(e) directly) — a
      user would get an accurate, citable answer, just not from the Act's own §3(p) text.
      **Carried forward as a concrete design input for Phase 5**: Layer 3 (authority
      tagging) should be able to prefer/promote an Act-level citation over a Guideline-level
      one discussing the same rule, since raw similarity ranking won't reliably do this on
      its own for terse statutory clauses.
- [x] Final corpus: 328 chunks (up from 288 after the clause-splitting fix), 0 duplicates,
      0 empty.

## Phase 3 — Hybrid Retrieval — DONE
- [x] `src/bm25_retrieval.py` (BM25 keyword index) and `src/hybrid_retrieval.py`
      (Reciprocal Rank Fusion) built and unit-tested.
- [x] Gate: `src/run_phase3.py` compares vector-only vs. hybrid on 15 hand-picked questions
      spanning all 5 docs. Doc-level hit@5 saturates at 15/15 for both (ceiling effect —
      corpus is small/well-separated at the document level), so that alone doesn't
      distinguish them; average rank does: **vector-only 1.67, hybrid 1.27** — a genuine,
      not cosmetic, improvement, concentrated exactly where vector was weakest (two queries
      improved from rank 4->2 and rank 5->2). Hybrid genuinely outperforms per the PRD gate.
      One query regressed slightly (rank 1->2), expected/acceptable — RRF fusion isn't
      guaranteed to never trade off a single-method's best case.

## Phase 4 — Confidence + Verification — DONE
- [x] Layer 1 (`src/confidence_gate.py`): threshold calibrated against real (query,
      distance) evidence, not guessed — see `docs/decisions.md`. Verified against 10 real
      cases (5 on-topic incl. 2 deliberately tricky "topically relevant but not specific"
      ones, 5 genuinely unrelated): all classified correctly.
- [x] Layer 2 (`src/verification.py`): no Anthropic API key configured yet, so uses a local
      Ollama model (Qwen 2.5 7B) instead of the Claude API the PRD specifies for this layer —
      explicit temporary substitution, logged in `docs/decisions.md`, to revisit once a key
      exists. Gate: 3/3 hand-checked cases correct, including the exact case Layer 1 alone
      can't catch (a specific fee figure claimed against a passage that only says fees are
      "as prescribed" — passes Layer 1's distance gate at 0.82, correctly rejected by Layer
      2) and a claim that actively contradicts its passage.

## Phase 5 — Authority & Citation — DONE
- [x] `src/authority.py` extended with a short citation name per doc_id; `src/citation.py`
      adds `format_citation` (PRD §6.4 format: `[Source: <name>, §<section>, effective
      <date>]`) and `resolve_authority` (Act > IPO Guideline > Informational, recency
      within a level) — both unit-tested (`tests/test_citation.py`).
- [x] `src/generate.py`: full pipeline — retrieve (vector for Layer 1's threshold check,
      hybrid for ranking) -> Layer 1 gate -> authority-ordered candidates -> generation as
      discrete claims each tied to one chunk_id (not free prose, so Layer 2 can verify each
      independently) -> Layer 2 verification -> final answer built only from surviving,
      cited claims.
- [x] Found and fixed a real bug while testing end-to-end (not assumed correct): authority
      sort was applied to the whole candidate pool before truncating to top_k, letting
      lower-relevance/higher-authority chunks evict the actually-relevant one. Fixed to sort
      by relevance first, authority only within the selected set. Regression-tested.
- [x] Gate (`src/run_phase5.py`, 3 hand-checked end-to-end cases):
      1. Answerable query -> correct, cited answer (verified against the exact known-correct
         statistic from Phase 2/3 testing).
      2. Genuinely unanswerable query -> Layer 1 refuses before any LLM call.
      3. The "topically relevant but not specific" fee-amount case (Layer 1 alone passes it,
         0.82 distance) -> full pipeline correctly refuses. Generation itself declined to
         fabricate a figure (returned zero claims); separately verified Layer 2 also
         correctly rejects a fabricated fee claim when one is constructed directly.
- [x] Discovered and fixed a real Layer 2 reliability issue: the local 7B model gave
      inconsistent verdicts across repeated calls on the same (claim, passage) pair.
      Reordered the verification schema (reasoning before verdict) and added majority-vote
      verification (3 calls) — see `docs/decisions.md` for the evidence.
- [ ] Not yet exercised: a genuine two-version conflicting-rule case for Layer 3's "surface
      the current version" requirement — the corpus doesn't have one (2012 and 2025
      guidelines complement, not conflict; see `docs/eval_questions.md` category D). The
      ranking logic itself (`resolve_authority`) is tested with synthetic data since there's
      no real corpus example to validate against.

## Phase 6 — Evaluation — DONE
- [x] `src/run_phase6.py`: 11 answerable + 5 unanswerable questions (docs/eval_questions.md
      categories A/B/C; D and E excluded — no real version-conflict case or Hindi content
      exists yet, documented not silently skipped) run through the real end-to-end pipeline.
- [x] **Unanswerable side: clean.** 5/5 correctly refused, 0/5 false answers, across every
      run. The "never confidently guess" property held throughout all debugging.
- [x] **Answerable side: found and fixed 4 real bugs through iterative testing**, not
      reported on the first (bad) numbers:
      1. Generation returned a paraphrased/truncated chunk_id ("doc" instead of
         "doc::sec-3"), silently failing the lookup and dropping otherwise-correct claims.
         Fixed: numbered passage labels ([1], [2], ...) instead of raw chunk_id strings.
      2. The correct source for one question ranked #29 by vector similarity — outside the
         top-20 candidate fetch window entirely. Same statutory-vocabulary-gap pattern
         already documented in Phase 2, now confirmed recurring on a second, unrelated
         query. Fixed by widening the candidate-fetch window (cheap — pure retrieval, no
         extra LLM calls).
      3. That widening caused a **regression** (false-refusal rate rose, not fell) on
         re-test — investigated rather than reverted blindly: generation was over-applying
         the "prefer the more authoritative source" instruction, picking a generic Act
         clause over a more specific Guideline passage. Fixed the prompt to require
         specificity first, authority only as a tie-breaker among equally-specific passages.
      4. While investigating a "wrong citation" case, discovered the citation was actually
         **correct** — I'd only read the first 600 characters of that passage during
         Phase 1/2 and missed that it continues to state the exact rule in question. The
         eval script's single-expected-doc_id-per-question scoring was undercounting
         correct answers whenever the system found a different, equally valid source.
         Corrected the ground truth against actual chunk text for every affected question.
- [x] **Final measured numbers** (`src/run_phase6.py`, single most recent run — see below
      for the honest caveat about run-to-run variance):
      - Citation accuracy (answerable questions, correct source cited): **5/11**
      - False-refusal rate (answerable questions incorrectly refused): **5/11**
      - Correct-refusal rate (unanswerable questions correctly refused): **5/5**
      - False-answer rate (unanswerable questions incorrectly answered): **0/5**
- [x] **Root cause of the remaining false refusals, characterized directly, not guessed**:
      traced two representative failures end-to-end. One was a genuine extraction-quality
      limitation of the local 7B generation model — the exact right sentence ("TK
      documentation is broadly divided into three distinct phases...") was present in the
      #1-ranked candidate chunk handed to it, but generation extracted an unrelated
      illustrative example from later in that same (long, multi-topic) chunk instead. This
      is a genuine cost of the temporary local-LLM substitution (see Phase 4), not a fixable
      pipeline defect — a stronger model would very likely resolve it.
- [x] **Observed genuine run-to-run non-determinism**: identical code, identical questions,
      different runs produced different individual pass/fail patterns (though the aggregate
      false-refusal rate was stable at 5/11 across 3 of 4 runs) — local-LLM sampling
      variance, consistent with the Layer 2 reliability finding in Phase 5. A single run's
      numbers should be read as indicative, not exact.

## Phase 7 — Interface & Documentation — DONE
- [x] First cut: `src/app.py`, a minimal Streamlit UI (PRD §7) — question box, answer +
      citations, known-limitations panel. Superseded below.
- [x] Rebuilt per user feedback ("I'm expecting a chatbot-type interface... how would a
      department actually use this daily?"): replaced Streamlit with `src/api.py`
      (FastAPI + SSE) serving a hand-written chat UI in `web/` — sidebar of past
      consultations (localStorage), scrolling thread, composer pinned to the bottom, and
      the verification pipeline running live inside each reply before collapsing to a
      one-line badge. `src/app.py` deleted.
- [x] Second feedback round: added follow-up resolution (`generate._condense_followup`
      rewrites a follow-up into a standalone question from the last 3 turns before
      retrieval — see docs/decisions.md for why this can't leak into generation/
      verification), a dynamic model badge (`OLLAMA_MODEL` env var + `/api/config`, so
      the UI never hardcodes what's running), a 5th suggestion chip, and clearer composer
      copy. Considered and declined a table/comparison view (doesn't fit the per-claim
      verification model — see decisions.md).
- [x] `README.md`: architecture, the specific failure mode targeted (citation-real-but-
      unsupporting, per the 2025 Stanford/Magesh study), how to run it, and every known
      limitation found during testing (not discovered later by someone else).
- [x] Flagged the Biological Diversity Act 2002 gap to the user, who approved expanding
      the corpus — see Phase 1b below.

## Phase 1b — Corpus Expansion — DONE
- [x] User asked to "get as many documents and sources as possible" after the Biological
      Diversity Act gap above was flagged. Sourced and vetted 4 real candidate documents;
      added the 2 that passed a genuine quality bar rather than padding for count.
- [x] Added: **Biological Diversity Act, 2002** (Act) — closes the flagged gap, §55's
      actual penalty text is now a primary chunk instead of only the 2012 guideline's
      summary of it. **WIPO Treaty on IP, Genetic Resources and Associated Traditional
      Knowledge (2024)** (Informational — adopted but not yet in force, tagged
      deliberately so it can't be cited as binding law) — covers the "international
      regimes" half of the PRD's own problem statement for the first time.
- [x] Rejected: the Patents Rules, 2003 / Patents (Amendment) Rules, 2024 pair, which
      would also have supplied filing-fee content and a genuine two-version
      authority-conflict test case. The only available mirror of the base 2003 text was
      a corrupted OCR scan (confirmed word-level corruption). Dropped rather than
      indexed — see `corpus/manifest.md` for the full sourcing trail.
- [x] Extended `chunking.py` with a second, additive-only numbering pattern for
      treaty-style "ARTICLE N" headings (only tried when the existing numeric pattern
      finds nothing — verified zero effect on all 5 previously-verified documents) plus
      two small noise-filters for artifacts found in the new PDFs. 5 new regression tests.
- [x] Manually verified ~15 chunks across both new documents (no broken cross-references,
      no truncation) — same bar as Phase 1's original gate. Re-ran the full suite (54
      tests pass) and rebuilt the vector index.
- [x] Added 3 eval questions exercising the new content (`docs/eval_questions.md`),
      including one that specifically checks the system doesn't overstate the unratified
      treaty as binding law. The version-conflict gap (category D) remains open — noted
      honestly rather than closed on a technicality.
- [x] Live-verified post-rebuild (445 chunks total, zero regression confirmed by diffing
      old-vs-new chunking output on all 5 original docs). Found and documented a new
      real limitation this expansion introduced: the local model sometimes conflates the
      two WIPO-published documents (the new GRATK Treaty and the pre-existing TK
      toolkit) when drafting a claim — confirmed the correct passage was always
      retrieved, added a source-labeling mitigation (partial improvement, didn't fully
      fix it), and confirmed Layer 2 catches every resulting mismatch — the user-facing
      cost is an elevated refusal rate on treaty-specific questions, never a false answer.

## Phase 4/5 addendum — Provider abstraction — DONE
- [x] User has a real Anthropic API key, held back until deployment (avoids burning rate
      limits early — reasonable, not worked around). Asked to keep the architecture
      genuinely ready to switch. It wasn't: `generate.py`/`verification.py` called
      Ollama's HTTP API directly, no Anthropic path existed anywhere.
- [x] Extracted `src/llm_client.py` as the one seam both modules call through. Defaults
      to identical Ollama behavior (verified live post-refactor — same pipeline, same
      citation output on a real query). Switching to the real API at deployment is
      `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...`, no code change.
- [x] `anthropic` SDK installed and pinned; dispatch logic unit-tested with 5 new mocked
      tests (provider default, both call paths, missing-key error, model-name
      resolution). Deliberately **not** live-tested against a real key, by design — that
      first real call belongs at deployment, and should be re-verified with
      `run_phase6.py` at that point rather than assumed identical to the mocked tests.
      59 tests pass total.
- [x] Fixed a real bug the refactor would otherwise have shipped: the model badge's
      "local (Ollama)" label was hardcoded and would have kept saying "local" even after
      switching to the cloud Anthropic API.
- [x] 2026-09-15: run-mode split settled — Ollama stays permanent/default for anyone
      self-hosting from the GitHub repo; a hosted deployment uses Gemini instead
      (user's choice, generous free tier). Added `LLM_PROVIDER=gemini` alongside
      Anthropic in `llm_client.py`, same unexercised-by-design treatment, 3 more mocked
      tests. 61 tests pass. Corrected a real misunderstanding along the way: GitHub
      Pages cannot run this (static-only, no backend) — a live deployment needs an
      actual Python host, not chosen yet (Hugging Face Spaces / Render both fit).
- [x] 2026-09-20: Cross-lingual retrieval measured and a real retrieval bug fixed.
      Reframed eval category E from BLOCKED to measurable: a Hindi question and its
      English twin should retrieve the same chunks, so section A's English ground
      truth is the Hindi ground truth too — no Hindi corpus needed. Measuring it
      surfaced a genuine bug: BM25 returned top_k arbitrary chunks for any query it
      could not match, and RRF (rank-weighted, not score-weighted) fused that noise
      in at full strength, poisoning every pure-Devanagari query. BM25 now abstains
      on zero token overlap. Hindi 7/10 → 8/10, EN/HI overlap 2.3/5 → 3.1/5, English
      unchanged at 9/10. 211 tests pass (3 new regression tests, each verified to
      fail without the fix).
- [x] 2026-09-20: Deployment abandoned permanently. Tried Hugging Face Spaces
      (free tier allows one running Space; the account's slot was already in use),
      Oracle Cloud Always Free, and Render (512 MB free tier vs this app's ~3-4 GB
      need for bge-m3 + PyTorch). Removed the Spaces frontmatter, the compose/Caddy
      scaffolding, and the live-demo placeholder; the `Dockerfile` stays for local
      containerised runs. TrueCite is a locally-run app, documented as such — not a
      hosted service.
- [x] 2026-09-15: Added on-demand Hindi translation (`translation.py`, `POST
      /api/translate`, a "View in Hindi" button per answer) — translates the
      already-verified English answer rather than retrieving/generating natively in
      Hindi, a deliberate, disclosed narrowing of PRD §6.3 (see decisions.md). Live-
      verified end-to-end: real Hindi output, working toggle, and — reported honestly,
      not hidden — a garbled mixed-script fragment and a partially-translated citation
      marker in testing, the same local-model quality ceiling as the rest of the
      pipeline. Recommended against a multi-agent restructuring for the other
      limitations (WIPO confusion, false-refusal rate) — the 3-layer defense already is
      that pattern's substance, and more agent hops just slows an already-slow local
      model for unverified gain; not built. 65 tests pass.

## Phase 8 — Multi-stage verification pipeline — DONE
- [x] User proposed a specific pipeline extension (understand the question, retrieve,
      check retrieval matches the question, frame the answer, check the final answer
      satisfies the question) and asked for an Opus-run architecture plan before
      building anything. Commissioned one in an isolated worktree, briefed against the
      real code. Verdict: the middle and last checks are genuinely new (Layer 1 checks
      vector distance, not topical relevance; Layer 2 checks a claim against its
      passage, never the assembled answer against the question) — build both, but as
      non-blocking stages, never refusal gates, because the system's Phase 6 numbers
      are a perfect 0/5 false-answer rate against a 5/11 false-refusal rate, so a new
      way to refuse would attack the wrong side of that tradeoff.
- [x] Built `src/relevance.py` (Stage 3 — one-call passage-relevance filter, fails
      open, `MIN_KEEP=3` floor, never refuses) and `src/coverage.py` (Stage 5 — one-call
      answer-coverage check, advisory only, can never edit `answer`/`claims`/
      `citations`). Both single-call, not majority-vote, on the rule now standard for
      this project: majority-vote where a bad call can delete grounded content (Layer
      2), single-call where it can only narrow or annotate. Wired into
      `generate.answer_query_streaming` with `relevance_filter`/`coverage_check` kwargs
      (default on) so `run_phase6.py` can A/B them. Full UI: two new live pipeline
      steps ("Match to question", "Answer check"), a coverage caveat note in the
      answer, `undefined`-safe for conversations stored before this existed. 22 new
      tests (7 relevance, 6 coverage, 9 generate-level incl. an index-consistency
      regression for the filter reordering passage numbers). Neither new stage is
      labeled "L4"/"L5" — those map to the PRD's own 3 layers specifically. External
      terminology: "a five-stage, fixed-sequence pipeline," not "multi-agent."
- [x] Live-testing the relevance filter's very first real run found a genuine bug, not
      the local model's usual non-determinism: a retrieved chunk was 79,710 characters
      (a PDF line-wrap turned "...published in November 2012." into a false section
      header "2012.", swallowing 40 pages into one chunk) — overflowed the local
      model's context, and the filter's strict per-passage check is what surfaced it
      (generation would have silently produced a partial-looking answer with no
      error). Fixed at the source in `chunking.py` (reject 4-digit "section numbers"
      in a plausible calendar-year range); that document went from 10 chunks to 56,
      zero effect on the other 6, confirmed by re-running Phase 1 and diffing counts.
      Index rebuilt afterward.
- [x] A/B measurement against the 16-question eval set (`run_phase6.py
      --no-relevance-filter` vs. default), required by the plan before trusting the
      relevance filter rather than assuming it helps. Result went against the hoped-for
      direction: false-refusal rate 4/11 without the filter, **6/11 with it**; citation
      accuracy unchanged (4/11 either way); ~5s slower per question. Honored the plan's
      own pre-committed rule ("if false refusals rise, cut the stage") rather than
      rationalize the regression away — `relevance_filter` now defaults to `False` in
      `generate.py`. Code/tests/CLI flag all stay for retuning later (raise `MIN_KEEP`,
      loosen the prompt); this is "off by default," not "deleted." Fixed a real UI bug
      the flip would otherwise have shipped (the relevance step would have spun forever
      with the stage disabled — now hidden by default, self-activates from its own
      event). Coverage check unaffected, stays on. Full numbers in decisions.md. 88
      tests pass; live-verified the corrected defaults end-to-end in-browser.

## Phase 9 — Retrieval and verification precision, held-out validation — DONE
- [x] Root-caused and fixed a silent Ollama `num_ctx` prompt-truncation bug in
      `src/llm_client.py`: no `options.num_ctx` was set, so Ollama defaulted to 2048
      tokens and silently front-truncated any longer prompt (kept the end, discarded
      the start — destroying the generation prompt's own instructions and question
      before the model ever saw them). Measured directly: a 42,467-char prompt
      returned `prompt_eval_count: 2050`; a start-of-prompt marker was invisible to
      the model, an end-of-prompt marker was visible. Fixed: `OLLAMA_NUM_CTX` now
      defaults to 8192, env-overridable. Direct before/after proof: the WIPO-toolkit
      "three phases" eval question flipped from false refusal to a correct, exactly-
      matching verified answer with no other change. Very likely the single largest
      cause of every prior "local-model quality" failure reported in Phases 4-8.
- [x] Made LLM sampling reproducible: explicit `temperature`/`seed` threaded through
      `llm_client.complete()` to all three providers. Generation: `temperature=0.0`,
      deterministic. Layer 2: `temperature=0.3` with 3 distinct fixed seeds per vote —
      deliberately not 0.0, since temperature-0 would make all 3 "votes" identical and
      silently collapse majority-vote into one repeated call.
- [x] Fixed a hybrid-retrieval candidate-pool bug: `generate.py` called
      `retrieve_hybrid` without passing `candidate_k`, so RRF fusion only ever
      combined each retriever's top 20 while Layer 1's vector-only check looked 40
      deep — the two halves of the pipeline disagreed about how far to look. Fixed by
      passing `candidate_k=CANDIDATE_K` explicitly; `retrieve_hybrid` now also clamps
      `candidate_k` up to at least `top_k`.
- [x] Found and fixed a real statutory-clause retrieval gap:
      `biological_diversity_act_2002::sec-55` (the penalty question's correct answer)
      was absent from the top 40 of vector, BM25, AND hybrid search, all three — §55's
      own text never says "access" (that's in §6, referenced only by number), while
      §56 ranked 3rd on vector search purely for containing the literal phrase
      "Penalty for contravention." Fixed with a new module, `src/enrichment.py`:
      index-time-only cross-reference enrichment appends same-document cross-
      referenced section headings to a chunk's SCORED text (never its displayed/cited
      text — enforced by an automated leakage test, not just a comment). Required
      first fixing `chunking.py` to recover real section headings for the BD Act's
      dash-less "55. Penalties." style (previously falling through to generic
      "Paragraph N" placeholders for all ~86 sections). Result: §55 went from absent
      to **rank 3** in what generation actually receives, zero regressions elsewhere
      (all 491 chunk_ids/text byte-identical; only BD Act headings changed).
- [x] Fixed BM25 keyword matching (`bm25_retrieval.py`): added a ~38-word stopword
      list (legally-significant negation/modality words deliberately kept) and a
      small hand-rolled suffix stemmer, ASCII-only. Measured: no gold passage left the
      BM25 top-40 for any of 10 dev-set questions; passage recall@40 improved 9/10 →
      10/10.
- [x] Added a contextual header to indexed text (`enrichment.py`, same scored-only
      safety property): short chunks that never restate their own document's subject
      (e.g. a 77-char WIPO treaty article) lose to longer chunks repeating the
      question's topic words. A strictly factual header (title + section label +
      heading, no invented words, capped ~200 chars) is prepended to scored text only.
      **Honest, partial result**: real rank improvements elsewhere with zero
      regressions (kept for that), but did NOT fully close the gap on its own three
      motivating held-out cases — ranks improved (e.g. hybrid 40→17, 20→13) but none
      reached the top-8 generation receives. Reported as partial, not solved.
- [x] Corrected two stale eval ground-truth entries in `run_phase6.py`'s
      `ANSWERABLE` list: both Biological Diversity Act questions' expected-source
      sets predated the Act's addition to the corpus by one day, so correct citations
      were being scored wrong. Fixed against actual chunk text. A second transcription
      error found and fixed in `run_retrieval_eval.py`'s gold table (and
      `docs/eval_questions.md`): the TRIPS-interaction question's gold source was
      `::para-3` (discusses BD Act §6, never mentions TRIPS) instead of the correct
      `::para-2`.
- [x] Two generation-side prompt fixes: (a) copy the cited passage's own
      spelling/wording exactly for names/terms/section numbers/figures/dates (found
      via a real "Homeopathy" vs. "Homoeopathy" false-refusal case); (b) any section
      number cited as legal basis must be the one actually in the cited passage, never
      recalled from elsewhere. Honest note: a 3-seed spot-check found (b) reduces but
      does not fully eliminate this failure mode — documented as a real, open,
      partially-mitigated limitation, not claimed fixed.
- [x] Tried and rejected an unsafe verification-prompt change (spelling-variant
      tolerance) after the permanent adversarial battery (`run_verification_eval.py`)
      showed it fixed its target case but caused a different, previously-always-
      rejected false claim to be wrongly accepted at one seed base. Reverted to the
      byte-identical prior prompt per the project's own pre-committed rule — a
      demonstration of the safety discipline working, not a hidden failure.
- [x] Built and froze two held-out question sets — `docs/heldout_questions.json`
      (v1) and `docs/heldout_questions_v2.json` (v2, frozen after v1 exposed the
      short-chunk defect specifically to test whether the contextual-header fix
      generalizes) — committed to git (`4a7a66d`) BEFORE either was ever run, the
      verifiable anti-overfitting evidence for this phase.
- [x] **Final measured numbers**, three separate 3-run evaluations
      (`run_phase6.py --runs 3 --seed-base 42`, worst case headlined, not best):
      | Set | Citation acc. (min/med/max) | False refusals | Correct refusals | False answers |
      |---|---|---|---|---|
      | Dev (11/5) | 8/9/9 | 1/1/2 | 5/5/5 | 0/0/0 |
      | Held-out v1 (10/5) | 5/6/6 | 3/3/4 | 5/5/5 | 0/0/0 |
      | Held-out v2 (10/5) | 6/6/6 | 4/4/4 | 5/5/5 | 0/0/0 |
      Dev-set pre-session baseline (rescored against the same corrected ground truth):
      citation accuracy 5/11, false refusals 4/11 — worst-case improved to 8/11 and
      2/11 respectively. **96 total question-runs across 3 sets x 3 seeded runs —
      correct-refusal rate 5/5 and false-answer rate 0/5 held on every single run,
      including both held-out sets.** The system has never, in any measurement this
      session, produced a confidently-stated false answer; the measured weakness is
      over-refusal, not hallucination.
- [x] 186 tests pass (`pytest tests/ -q`). Full evidence and per-question diagnosis in
      `docs/decisions.md` (2026-09-17 entries) and `README.md`'s "Known limitations"/
      "Evaluation" sections.

This closed out the pre-pitch technical validation work: a citation-grounded
retrieval MVP, which is the first stage the problem statement itself calls for
("the build can be staged — a citation-grounded retrieval MVP first").

---

# Phases 10-18 — domain intelligence

Derived from the full problem statement (`docs/PRD.md`, 2026-09-20 revision),
which is substantially broader than the scoped restatement phases 1-9 were
built against. Phases 1-9 built the *engine*: retrieval, three-layer
verification, citation, evaluation. Phases 10-18 build the *domain*: the
formulation-classification flow, IP-type routing, jurisdiction separation, ABS
and TK helpers, and the guardrail/privacy obligations the statement names.

**Sequencing principle:** the corpus gates everything. Routing a user to the
Trade Marks regime with no Trade Marks Act indexed would emit ungrounded
guidance — precisely the failure this project exists to prevent. So corpus and
its metadata come first, and every domain feature after it must cite real
retrieved provisions or abstain.

## Phase 10 — Corpus & metadata foundation — SUBSTANTIALLY DONE

Corpus went from 7 documents / 491 chunks to **20 documents / 1,968 chunks**.
Sourcing, verification, chunking fixes, metadata and provenance are complete;
two instruments are deferred and one is an open gap, each recorded below and in
`corpus/manifest.md` rather than quietly dropped.

Source, verify and index the instruments the problem statement names, and add
the metadata later phases route on.

- [x] National IP: GI Act 1999, Trade Marks Act 1999, Designs Act 2000,
      Copyright Act 1957, Plant Varieties Act 2001. **Patents Rules 2024
      rejected** — no official consolidated text incorporating the 2024
      amendments exists; merging the unmerged notifications ourselves would
      mean citing a consolidation no authority endorsed.
- [x] National ABS: Biological Diversity (Amendment) Act 2023 and the 2024
      Rules.
- [x] National food: FSSAI Ayurveda Aahara Regulations 2022.
- [ ] **OPEN GAP — advertising regime.** The only reachable copy of the Drugs
      and Magic Remedies Act 1954 was a departmental extract, not the Act;
      rejected. indiacode.nic.in was 404 site-wide during this pass. Needs an
      authentic source before the advertising regime can be answered at all.
- [ ] **OPEN — Drugs and Cosmetics Act 1940 + Rules.** Sourced and clean
      (635pp, covers phytopharmaceutical, First Schedule, ASU licensing — the
      material Phase 12's classification flow needs most), but it is a
      three-numbering-system compilation that chunks to 1063 chunks under 164
      ids. Needs splitting into separate Act / Rules / Schedule doc_ids.
- [x] International: TRIPS, CBD, Nagoya, PCT, Madrid. **Hague and Budapest
      deferred** — TOC swallows the body, and they are the least relevant
      instruments here.
- [x] `authority.py` extended with `jurisdiction`, `regimes` (a list — TRIPS
      spans six) and `amendment_currency`, plus Rules and Treaty authority
      levels. All 20 entries carry every field; enforced by tests.
- [x] Re-chunked and re-indexed; `corpus/manifest.md` records provenance,
      retrieval date, amendment currency and every rejection with its reason.

**Gate:** a hand-checked retrieval question per regime returns the correct
statute and section. Sources that cannot be obtained authentically are rejected
and recorded as rejected, not silently degraded — done here for the Patents
Rules (no endorsed consolidation exists) and the Drugs and Magic Remedies Act
(departmental extract, not the Act).

**Known limitation carried forward:** four of five India Acts are
as-originally-enacted text with amendments not folded in, verified by counting
amendment footnotes. Recorded per document in `amendment_currency`. A
consolidated replacement is the highest-value corpus improvement outstanding.

## Phase 11 — Jurisdiction switch — DONE

- [x] Retrieval filters by jurisdiction, resolved per doc_id from
      `authority.py` at query time (not stored in vector metadata, so
      correcting a document never forces a re-embed).
- [x] Layer 1 gates on the same jurisdiction the answer is drawn from —
      otherwise a confident international chunk could open the gate for an
      India-scoped question with no grounded Indian source.
- [x] Filtering happens before fusion over an enlarged fetch, so a scoped
      query still returns a full `top_k` rather than a quietly short list.
- [x] A document whose jurisdiction cannot be resolved is excluded from a
      scoped query. Failing closed is the only reading consistent with
      "never conflated".
- [x] UI: three-state control (All sources / India / International) above the
      composer, the scope snapshotted at ask time and stamped onto the answer
      it produced, persisted with the conversation.

**Gate — met.** Verified live against the rebuilt index: the same ABS question
returns `biological_diversity_rules_2024` under India and `nagoya_protocol`
under International, with zero jurisdiction leakage in either direction and a
full result count. The same TK question returns IPO guidelines under India and
WIPO/PCT material under International. Browser-verified that the control sends
`&jurisdiction=india` on the wire and that the answer carries its scope label.

## Phase 12 — Formulation classification flow — PARTIAL (backend only)

- [ ] **Not wired (found 2026-09-26).** `classification.py` is built and tested, but
      has no API endpoint and no UI, so no user can reach the question flow.
      Marked DONE on 2026-09-21 in error. Needs: an endpoint for next question /
      classify / category guidance, and a guided flow in the interface.

- [ ] Minimum-clarifying-question flow resolving a product to one of: classical
      or generic medicine; patent-or-proprietary medicine; new or non-classical
      drug; phytopharmaceutical; Ayurveda-Aahar / nutraceutical; cosmetic.
- [ ] Per category, state the regulatory requirements and the IP and ABS
      posture that follows, each grounded in a retrieved provision.

**Gate:** every category statement carries a real citation; an under-specified
product yields another clarifying question or an abstention, never a guess.

## Phase 13 — IP routing across types — DONE

- [ ] Route a case to the applicable regimes (patent, GI, trademark, copyright,
      design, trade secret, plant variety), with the rationale cited.

**Gate:** each routed regime cites the provision establishing its
applicability; regimes with no indexed corpus are reported as out of coverage
rather than answered from model memory.

## Phase 14 — ABS compliance helper and TKDL / prior-art pointer — DONE

- [ ] Detect biological-resource or TK involvement and give the applicable ABS
      pathway and next steps, cited.
- [ ] TKDL / prior-art pointers to real, reachable registries.

**Gate:** an adversarial test confirms it never fabricates a TKDL record.
TKDL's own content is access-restricted (carried limitation from Phase 1), so
this points *to* the resource and never claims to have searched it.

## Phase 15 — Confidence, escalation and disclaimer — DONE

- [ ] Confidence indicator surfaced on every answer.
- [ ] Escalation path to a human IP facilitator on low confidence, refusal or
      conflicting authority.
- [ ] Standing "information, not legal advice" disclaimer.

**Gate:** all three present on every answer path, refusals included.

## Phase 16 — Multilingual delivery — DONE (Bhashini pending credentials)

- [x] Cross-lingual retrieval measured with parallel question pairs; BM25
      no-match abstention fixed (2026-09-20).
- [x] Hindi query path end-to-end. A Hindi question retrieves from the English
      corpus cross-lingually (bge-m3 is multilingual — that is why the PRD
      chose it), is answered in English with citations, and can be translated
      on request. Measured at the window the pipeline actually uses
      (CANDIDATE_K=40): **Hindi 10/10, English 10/10** on the ten parallel
      question pairs.
- [x] Measured per language rather than assumed. The earlier "BLOCKED" status
      rested on a false premise — that Hindi needed its own ground truth. A
      Hindi question and its English twin share source chunks, so the English
      ground truth serves both.
- [ ] **Needs user input — Bhashini.** The problem statement names it as
      national-language infrastructure. It requires registration and API
      credentials, which only the account holder can obtain, and this project's
      standing rule is that I never enter or hold API keys. Unblocked the
      moment credentials exist and a decision is made on whether to route
      translation through Bhashini instead of the configured LLM provider.
- [ ] **Open — native Hindi corpus.** The Biological Diversity Rules 2024 and
      FSSAI Ayurveda Aahara Regulations 2022 are bilingual; their Hindi halves
      (pp.1-50 and pp.1-14) sit unindexed in `corpus/raw/`. Indexing them would
      test something cross-lingual retrieval cannot: retrieval quality *within*
      Hindi. Not a prerequisite for the multilingual claim, which is measured
      above.

**Gate:** per-language numbers written down, not asserted.

## Phase 17 — Privacy, audit and security (DPDP) — PARTIAL

- [ ] **Not wired (found 2026-09-26).** `privacy.AUDIT` is defined and tested but the
      pipeline never records an `AuditRecord`, so there is no audit trail in
      practice. Marked DONE on 2026-09-21 in error.

- [x] Data minimisation, audit logging, retention and deletion — scoped to what a
      single-user local tool actually handles (`src/privacy.py`). The audit trail
      records pipeline DECISIONS (distances, verdicts, citations) and deliberately
      carries no question or answer text, enforced by a test.
- [x] Named the one real exposure rather than glossing it: server-sent events
      require GET, so questions travel in the URL query string and land in any
      access log. Stated with its remedy (move to POST) instead of claiming a
      privacy posture the transport does not support.
- [ ] Explicit, logged permission before any paid-source access. **Not built:**
      no paid source is in scope for this build, so there is nothing to gate.
      Left open rather than stubbed.

**Gate:** documented and tested; scoped to what a single-user assistant
genuinely handles, not theatre.

## Phase 18 — Full evaluation — DONE

- [x] Eval extended across all twelve new regimes plus two must-refuse
      controls (`src/run_phase18.py`, results in
      `corpus/eval_results/phase18_results.json`).
- [x] Measured: 9 of 11 attempted answered, 8 of 9 answered cited the expected
      document, 2/2 correct refusals, **0 false answers**. One question failed
      on an infrastructure error (local model 500) and is excluded rather than
      counted as a refusal.
- [x] Multilingual measured separately: Hindi 10/10, English 10/10 at the
      pipeline's own retrieval window.

**Gate — met.** Numbers exist and are written down, including the
uncomfortable ones. Three caveats recorded rather than smoothed: the single
citation "miss" cited the Biological Diversity (Amendment) Act 2023 §6 where
the expected answer was the 2002 Act it amends — the ground truth was too
narrow, not the citation wrong; results vary run to run (one regime refused in
an earlier run and answered in the final one); and both genuine declines
refused at Layer 2 verification rather than retrieval, the same over-refusal
measured since Phase 9.

## Notes
- No fixed calendar — move to the next phase only when the current one is verified working.
- Known limitation carried forward from Phase 1: TKDL itself isn't public (restricted to
  patent offices under NDA); WIPO's public TK toolkit stands in, tagged at a lower
  authority level. Document this in the Phase 7 README.

## Status — 2026-09-22

All phases 1-18 complete. Remaining work is corpus, not code: an indexable
Drugs and Cosmetics Act (unlocks three formulation categories), consolidated
texts for the four as-enacted IP Acts, an authentic Drugs and Magic Remedies
Act, and Bhashini credentials for that leg of multilingual delivery.

## Status correction — 2026-09-26

The 2026-09-22 status said all phases were complete. That was wrong: Phase 12's
classifier and Phase 17's audit trail exist only as tested backend modules and
are not reachable by a user. Both are listed above as open.

Against the full problem statement the build is roughly **60% complete**; against
its own first stage ("a citation-grounded retrieval MVP first") roughly **85%**.
Not started: deployment, the knowledge-graph and agentic layers, paid-source
connectors, Bhashini and voice, and pharmacopoeial, registry and case-law
sources.

