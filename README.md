# IP-SAKTI Sahayak

A multilingual, source-cited RAG assistant for Ayurveda intellectual property and
regulatory guidance, built for SIH26045 (Ministry of Ayush).

## The problem this solves

Ayurveda researchers, practitioners, and companies need reliable answers about IP
and regulatory rules — patents, traditional knowledge protection, national and
international compliance — but the relevant information is scattered across the
Patents Act 1970, Ayush-specific IPO guidelines, and WIPO/TKDL material. A wrong
answer here has real consequences (a missed filing deadline, a misunderstood
disclosure rule).

**The specific failure mode this project targets:** a 2025 Stanford/Magesh study
found that even production legal-AI tools (Westlaw, LexisNexis) routinely cite a
*real* source for a claim that source doesn't actually support. Retrieving the
right document isn't enough — the system also has to check that what it retrieved
actually backs up what it's about to say. That's what Layer 2 below does, and it's
the project's core technical claim.

## Design principle

**The system must know when it doesn't know**, enforced at every layer, not
bolted on at the end:
- Retrieval that isn't confident → refuse, don't guess (Layer 1).
- A citation that's real but doesn't back the claim → reject it, don't show it (Layer 2).
- Multiple sources on the same point → prefer the more authoritative one, don't just
  take whatever scored highest by similarity (Layer 3).

## How it works

```
question
   │
   ├─► vector search (BAAI/bge-m3 + ChromaDB)  ─┐
   └─► BM25 keyword search  ────────────────────┴─► Reciprocal Rank Fusion (hybrid)
                                                          │
                                          Layer 1 — confidence gate
                                    (refuse if no vector hit clears
                                     a calibrated distance threshold)
                                                          │
                                     candidates ordered by authority
                                  (Act > IPO Guideline > Informational,
                                    then recency — citation.py)
                                                          │
                                              generation (local LLM)
                                    produces discrete claims, each tied
                                       to exactly one source passage
                                                          │
                                          Layer 2 — claim verification
                                  (each claim checked against its cited
                                   passage; unsupported claims dropped,
                                        not shown — majority vote
                                       across 3 calls, see below)
                                                          │
                                      answer, built only from surviving
                                     claims, each with a formatted citation
                                  [Source: <name>, §<section>, effective <date>]
```

Structured, not fixed-token, chunking: the corpus's documents each use different
numbering conventions (statutory sections, numbered guideline paragraphs, plain
prose), and legal cross-references break under naive chunk-boundary splitting. See
`docs/architecture.md` for the full chunking strategy and `docs/decisions.md` for
the specific bugs this caught along the way (several were real content-loss or
duplicate-citation bugs, not just style issues).

## Corpus

Five real documents, sourced and provenance-tracked in `corpus/manifest.md`:
the Patents Act 1970, two IPO guideline documents (2012 TK/Biological Material,
2025 AYUSH Examination), a WIPO TK documentation toolkit, and a 2013 PIB press
release. **Known gap**: the actual TKDL database isn't public (restricted to
patent offices under NDA) — the WIPO toolkit is the closest public substitute,
tagged at a lower authority level accordingly.

## Running it

Requires Python 3.12 and a local [Ollama](https://ollama.com) install with
`qwen2.5:7b` pulled (see "Known limitations" below for why a local model, not
the Claude API this was originally scoped for).

```bash
python -m venv .venv
source .venv/Scripts/activate   # or .venv\Scripts\activate on Windows cmd
pip install -r requirements.txt

python src/run_phase1.py   # parse + chunk the corpus
python src/run_phase2.py   # build the vector index, sanity-check retrieval
python -m pytest tests/    # run the automated test suite (46 tests, all fast — no live model calls)
```

To ask a question directly:
```python
from generate import answer_query
result = answer_query("Can traditional knowledge be patented in India?")
print(result["answer"])
```

## Known limitations

Found through actual testing, not assumed away — documented here rather than
discovered later by someone else:

- **No Claude API key configured.** The PRD specifies the Claude API for
  generation and Layer 2 verification; this build substitutes a local Ollama
  model (Qwen 2.5 7B) instead, as an explicit, temporary decision (see
  `docs/decisions.md`). This is the single biggest thing to revisit before any
  real deployment — see the reliability note below.
- **Local-model reliability.** The substitute 7B model gave inconsistent
  verdicts across repeated calls on the same (claim, passage) pair during
  testing — one genuinely well-supported claim was incorrectly rejected 1
  time in 3. Mitigated with majority-vote verification (3 calls, take the
  consensus), which measurably helped but doesn't guarantee determinism. A
  frontier model would likely need this less.
- **Local-model extraction quality.** Phase 6 measured a 5/11 false-refusal
  rate on answerable questions. The unanswerable side is clean (5/5 correct
  refusals, 0 false answers) — the failures are specifically the smaller
  model sometimes not extracting the right fact even when it's present in
  the top-ranked passage it was given (verified directly on one case: the
  right sentence was there, generation picked an unrelated example from
  later in the same passage instead). See "Evaluation" below.
- **A real vocabulary/framing gap in retrieval.** Terse, negatively-framed
  statutory clauses (e.g. Patents Act §3(p), which never actually uses the
  word "patent") don't reliably rank highly against natural-language
  questions ("can X be patented?") — true for vector search, BM25, and their
  hybrid alike. The system still returns a substantively correct, citable
  answer from a secondary source discussing the same rule in fuller prose,
  but won't always lead with the primary statutory text itself.
- **No genuine version-conflict test case.** Layer 3 is built to prefer the
  more authoritative/current source when two sources disagree, but this
  corpus's two guideline documents (2012, 2025) complement rather than
  supersede each other — so this behavior is verified with synthetic data,
  not a real example from the corpus.
- **No Hindi content yet.** PRD §6.3 requires verifying retrieval quality in
  English and Hindi independently; the corpus is English-only so far, so
  multilingual retrieval quality is unverified.
- **Not production-scale.** Single-user, local-only, no concurrency handling
  — matches the PRD's stated non-goals for this phase.

## Evaluation

`src/run_phase6.py` runs 11 answerable + 5 unanswerable questions
(`docs/eval_questions.md` categories A/B/C) through the real pipeline. Most
recent measured results:

| Metric | Result |
|---|---|
| Correct-refusal rate (unanswerable questions correctly refused) | **5/5** |
| False-answer rate (unanswerable questions incorrectly answered) | **0/5** |
| Citation accuracy (answerable questions, correct source cited) | **5/11** |
| False-refusal rate (answerable questions incorrectly refused) | **5/11** |

**The unanswerable side is clean** — the system never confidently answered a
question the corpus can't actually support, across every debugging run. The
answerable side is weaker, and getting to these numbers found and fixed 4 real
pipeline bugs along the way (chunk-ID references the model mangled when
copying, a retrieval window too narrow to reach a correctly-worded but
rank-29 statutory clause, an authority-preference instruction the model
over-applied, and an eval ground truth that was itself too narrow — see
`docs/decisions.md` for each, with evidence). The **remaining false
refusals trace to a genuine local-7B-model limitation**, not a further
pipeline defect: in the case investigated directly, the exact right sentence
was present in the #1-ranked candidate passage, but generation extracted an
unrelated example from later in that same long passage instead. This is the
concrete, measured cost of substituting a local model for the Claude API the
PRD specifies (see "Known limitations") — expect it to improve significantly
once a real API key is available. Also observed: genuine run-to-run
variance from LLM sampling — a single run's numbers are indicative, not an
exact reproducible score. Full question set and per-question ground truth
in `docs/eval_questions.md`; full debugging narrative in `docs/phases.md`
Phase 6 and `docs/decisions.md`.

## Project docs

- `docs/PRD.md` — original requirements (kept as originally written).
- `docs/architecture.md` — current actual architecture, data flow, folder structure.
- `docs/decisions.md` — every non-obvious technical choice, with the evidence behind it.
- `docs/phases.md` — living build log, phase by phase, with gate criteria and results.
- `docs/eval_questions.md` — the Phase 6 evaluation question set.
