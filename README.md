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

Seven real documents, sourced and provenance-tracked in `corpus/manifest.md`:
the Patents Act 1970, the Biological Diversity Act 2002, two IPO guideline
documents (2012 TK/Biological Material, 2025 AYUSH Examination), a WIPO TK
documentation toolkit, the 2024 WIPO Treaty on IP, Genetic Resources and
Associated Traditional Knowledge, and a 2013 PIB press release.

**Known gaps**: the actual TKDL database isn't public (restricted to patent
offices under NDA) — the WIPO toolkit is the closest public substitute, tagged
at a lower authority level accordingly. The WIPO GRATK Treaty is real,
adopted text but **not yet in force** (needs 15 ratifications) — tagged
Informational rather than Act specifically so it can never be cited as if it
were binding Indian law. A real Patents Rules / 2024 Amendment pair — which
would also have covered filing fees and given Layer 3 a genuine two-version
conflict to resolve — was sourced but rejected: the only available mirror of
the base 2003 text was a corrupted OCR scan, unacceptable for a citation-trust
tool (see `corpus/manifest.md` for the specifics).

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

uvicorn src.api:app --port 8000   # then open http://localhost:8000
```

The first start is slow — it loads the embedding stack before serving.

To use a different local Ollama model, set `OLLAMA_MODEL` before starting the
server (e.g. `OLLAMA_MODEL=llama3.1:8b uvicorn src.api:app --port 8000`) — the
UI's sidebar badge picks it up automatically, no code change needed.

Two run modes are supported. Running locally like above (Ollama, no key)
is meant to stay the permanent way to self-host this from the GitHub repo —
it's free and works offline. **For an actual hosted deployment**, switch to
a cloud provider instead:

```bash
# Gemini — the intended deployment provider
LLM_PROVIDER=gemini GEMINI_API_KEY=... uvicorn src.api:app --port 8000

# Anthropic — the PRD's original choice, built first, kept available
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... uvicorn src.api:app --port 8000
```

Every generation and Layer 2 call routes through `src/llm_client.py`, so
this env-var change is all deployment needs — see "Known limitations" below
for why neither cloud path has been exercised against a real key yet. Note
that GitHub itself only hosts the *code*; a live deployment needs an actual
Python-capable host (e.g. Hugging Face Spaces, Render) — not set up yet.

### The interface

A consultation tool rather than a search box: a thread you can keep adding to,
past consultations in the sidebar, and the composer pinned at the bottom.

While an answer is being produced, the **verification pipeline runs visibly
inside the reply** — passages retrieved, the confidence gate's actual distance
against its 0.90 threshold, then a ✓/✗ verdict per claim as each is checked
against the passage it cites. Once it settles, the whole thing collapses to a
single badge (`✓ Verified · 1 claim upheld · 1 source · 34.9s`) that can be
re-expanded. Citations are clickable and open the exact source passage, tagged
with its authority tier and effective date; anything the system discarded is
listed under "What this answer left out".

A follow-up question ("what about for Unani specifically?") is rewritten into
a standalone question from the last 3 turns before retrieval — shown as its
own "Understand follow-up" step — but the rewrite itself is never verified,
only the answer is, so a confusing follow-up may retrieve the wrong passages
rather than the right ones (in which case the pipeline still refuses instead
of guessing). The sidebar footer names the model actually running, read from
the active provider, so it never goes stale if the model is swapped.

Each answer has a **"View in Hindi" button** — translates the already-
verified English answer on request (`/api/translate`), rather than
retrieving/generating natively in Hindi; see "Known limitations" for why.

To use the pipeline directly instead:
```python
from generate import answer_query
result = answer_query("Can traditional knowledge be patented in India?")
print(result["answer"])
```

```bash
python -m pytest tests/    # 46 tests, all fast — live model calls are mocked
```

## Known limitations

Found through actual testing, not assumed away — documented here rather than
discovered later by someone else:

- **Real cloud API keys exist, deliberately not yet in use.** The PRD
  specifies the Claude API for generation and Layer 2 verification; this
  build defaults to a local Ollama model (Qwen 2.5 7B) instead, routed
  through `src/llm_client.py` (see `docs/decisions.md`) — that stays the
  permanent mode for anyone self-hosting from this repo. Real Gemini and
  Anthropic keys exist for an actual hosted deployment, held back
  specifically to avoid burning through rate limits during development —
  switching is one env var change (`LLM_PROVIDER=gemini` or `anthropic`),
  reviewed but **not live-tested against a real key**, so re-verify with
  `run_phase6.py` once one is actually in use. This is the single biggest
  thing that would change the numbers below.
- **Local-model reliability.** The substitute 7B model gave inconsistent
  verdicts across repeated calls on the same (claim, passage) pair during
  testing — one genuinely well-supported claim was incorrectly rejected 1
  time in 3. Mitigated with majority-vote verification (3 calls, take the
  consensus), which measurably helped but doesn't guarantee determinism. A
  frontier model would likely need this less.
- **Follow-up rewriting is best-effort, unverified.** The same local model
  resolves a follow-up into a standalone question from the last 3 turns
  (see "The interface" above); observed live on a genuinely ambiguous
  follow-up, it produced a plausible but not necessarily intended reading of
  an earlier turn. The rewrite is shown to the user but isn't itself checked
  against anything — the safety net is that retrieval/verification still
  only ground in the corpus, so a bad rewrite produces a refusal or a
  differently-scoped answer, never a fabricated one.
- **No table/comparison view.** Every claim is tied to exactly one source
  passage (that's what makes Layer 2 possible); a comparison question gets a
  claim list with per-source authority tiers rather than a table, since a
  table cell doesn't have a single passage to verify it against.
- **The two WIPO documents get confused with each other.** Asking about the
  2024 GRATK Treaty's Article 3 disclosure requirement, the local model
  repeatedly drafted a claim about the older WIPO TK documentation toolkit
  instead — even though the treaty's own Article 3 text was correctly
  retrieved and given to it every time (confirmed directly, across 4 query
  phrasings). Layer 2 caught every one of these mismatches and refused rather
  than showing a wrong answer, so this shows up as an elevated refusal rate
  for treaty-specific questions, not a false answer. Same underlying cause as
  the local-model extraction-quality limitation below, just harder to trigger
  before this corpus had two similarly-themed WIPO sources.
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
- **Hindi is a translation layer, not native retrieval.** PRD §6.3 asks for
  retrieval quality verified in English and Hindi independently. Retrieval,
  generation, and Layer 2 stay English-only (deliberately — see
  `docs/decisions.md`); a "View in Hindi" button on each answer translates
  the already-verified English text on request instead. This narrows what
  the PRD literally asks for — no Hindi retrieval is ever exercised, so
  there's nothing to verify there — in exchange for zero new hallucination
  risk (translating settled text can only be mistranslated, not fabricated).
  Translation quality itself inherits the same local-model ceiling as
  everything else — observed live: a real but minor instruction-following
  slip (a citation marker partly translated) and a genuine mixed-script
  glitch in one run. Machine-translation disclaimer shown in the UI itself.
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
