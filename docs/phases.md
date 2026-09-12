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

## Phase 6 — Evaluation — not started
20-30 question eval set; citation accuracy, refusal rate, false-refusal rate.

## Phase 7 — Interface & Documentation — not started
Minimal UI, README (architecture, failure mode solved, known limitations).

## Notes
- No fixed calendar — move to the next phase only when the current one is verified working.
- Known limitation carried forward from Phase 1: TKDL itself isn't public (restricted to
  patent offices under NDA); WIPO's public TK toolkit stands in, tagged at a lower
  authority level. Document this in the Phase 7 README.
