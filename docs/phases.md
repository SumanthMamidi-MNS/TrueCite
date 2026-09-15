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

## Notes
- No fixed calendar — move to the next phase only when the current one is verified working.
- Known limitation carried forward from Phase 1: TKDL itself isn't public (restricted to
  patent offices under NDA); WIPO's public TK toolkit stands in, tagged at a lower
  authority level. Document this in the Phase 7 README.
