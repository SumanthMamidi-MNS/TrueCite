# Phases — IP-SAKTI Sahayak

Sequential, gated phases per PRD §9 — no fixed schedule. Each phase gates the next.

## Phase 1 — Corpus & Chunking — IN PROGRESS, awaiting user review
- [x] Corpus sourced: 5 real documents (Patents Act 1970, IPO TK/Biological Material
      Guidelines 2012, IPO AYUSH Examination Guidelines 2025, WIPO TK toolkit, PIB FAQ
      release). Provenance/authority tagged in `corpus/manifest.md`.
- [x] Parsing + structural chunking built (`src/parsing.py`, `src/chunking.py`).
- [x] Ran on 3 sample docs (Patents Act, TK Guidelines 2012, PIB FAQ) — found and fixed
      4 real bugs during manual review (footnote/section-number collisions, duplicate
      chunk IDs, hidden section 11A/11B, lost preamble text).
- [ ] User review of chunk output (gate: 10 samples, no broken cross-references) — pending.
- [ ] Run chunking on remaining 2 docs (AYUSH 2025, WIPO toolkit) once approach is approved.

## Phase 2 — Basic Retrieval — not started
Embeddings + ChromaDB indexing, vector-only retrieval.

## Phase 3 — Hybrid Retrieval — not started
Add BM25, compare vs vector-only on 15 test questions.

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
