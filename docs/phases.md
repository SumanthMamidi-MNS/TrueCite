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

## Phase 3 — Hybrid Retrieval — IN PROGRESS
- [x] `src/bm25_retrieval.py` (BM25 keyword index) and `src/hybrid_retrieval.py`
      (Reciprocal Rank Fusion) built and unit-tested.
- [ ] Gate: compare vector-only vs. hybrid on 15 test questions — hybrid must genuinely
      outperform, not just add complexity. Not yet run at the 15-question scale.

## Phase 4 — Confidence + Verification — not started
Layer 1 (confidence gate) + Layer 2 (claim-support verification).

## Phase 5 — Authority & Citation — not started
Layer 3 (date/authority tagging), citation-formatted generation.

## Phase 6 — Evaluation — not started
20-30 question eval set; citation accuracy, refusal rate, false-refusal rate.

## Phase 7 — Interface & Documentation — not started
Minimal UI, README (architecture, failure mode solved, known limitations).

## Notes
- No fixed calendar — move to the next phase only when the current one is verified working.
- Known limitation carried forward from Phase 1: TKDL itself isn't public (restricted to
  patent offices under NDA); WIPO's public TK toolkit stands in, tagged at a lower
  authority level. Document this in the Phase 7 README.
