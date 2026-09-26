# Backend — TrueCite

Everything that runs on the server: the language and libraries, how a question
becomes a verified answer, every module, the HTTP contract the frontend relies
on, configuration, the corpus build, and testing. Versions below are the exact
ones pinned in `requirements.txt` and installed in `.venv`.

## At a glance

| | |
|---|---|
| **Language** | Python 3.12 |
| **Web framework** | FastAPI 0.141.1, served by Uvicorn 0.52.4 |
| **Vector database** | ChromaDB 1.5.9 (embedded, persisted to `corpus/chroma_db/`) |
| **Embeddings** | BAAI/bge-m3 via sentence-transformers 6.0.1 on PyTorch 2.14 (CPU) |
| **Keyword search** | rank-bm25 0.2.2 (BM25Okapi) |
| **PDF parsing** | pypdf 6.18.1 |
| **Validation** | Pydantic 2.13 (request bodies) |
| **LLM providers** | Ollama (default, local), Google Gemini (`google-genai` 2.23.0), Anthropic (`anthropic` 1.5.0) |
| **HTTP client** | requests 2.34.2 (Ollama) |
| **Tests** | pytest 9.1.1 — 280 tests, model calls mocked |
| **Database / auth** | None. No user accounts, no server-side storage of questions or answers. |

There is no ORM, no task queue, no cache server and no container. The whole
backend is one FastAPI process holding an embedded ChromaDB index, a BM25 index
in memory, and the bge-m3 model. It needs roughly 3-4 GB of RAM, almost all of
it the embedding model plus PyTorch.

## Design in one paragraph

A **fixed-sequence pipeline, not an agent**. Every question passes through the
same stages in the same order; nothing plans, loops, or chooses its own next
step. Three verification layers enforce the project's single principle — the
system must know when it does not know: a retrieval confidence gate (Layer 1),
per-claim verification against the cited passage (Layer 2), and authority
ordering so the most binding source leads (Layer 3). Wherever a legal test has
a crisp answer — jurisdiction, IP-regime routing, formulation category — the
decision is deterministic code, never a model call.

## Request flow

`GET /api/ask` → `generate.answer_query_streaming`, which yields one
server-sent event per stage:

1. **Follow-up condensing** (only if history is sent) — the last 3 turns are
   used to rewrite a follow-up into a standalone question. LLM call.
2. **Jurisdiction filter** — `india`, `international`, or none. Resolved per
   document from `authority.py` at query time, applied to *both* retrievers
   *before* fusion over a 3× over-fetch, so a scoped query still returns a
   full candidate list. An unclassifiable document is excluded, not included.
3. **Vector retrieval** — top 40 by bge-m3 embedding distance.
4. **Layer 1, confidence gate** — if the closest passage's distance exceeds
   **0.90**, refuse immediately. No model call is spent.
5. **Hybrid ranking** — vector and BM25 rankings fused by **Reciprocal Rank
   Fusion** (k = 60), restricted to passages that cleared Layer 1.
6. **Layer 3, authority ordering** — Act (5) › Rules (4) › Treaty (3) ›
   Guideline (2) › Informational (1); more recent first within a level. Top 8
   passages go forward.
7. **Relevance filter** — built, tested, **off by default** (an A/B showed it
   raised false refusals).
8. **Generation** — the model drafts a list of discrete claims, each bound to
   exactly one passage number. Temperature 0.0, fixed seed 42, so it is
   reproducible.
9. **Layer 2, claim verification** — per claim, three independent checks
   (temperature 0.3, distinct seeds) ask "does this passage support this
   claim?"; two must agree or the claim is discarded and listed under "left
   out". If every claim is discarded, the answer is refused.
10. **Citation** — `[Source · §section · effective date]`, built from the
    document registry, never from model output.
11. **Coverage check** — advisory only: "does this actually answer what was
    asked?" It can attach a note; it can never refuse or edit a claim.
12. **Advisory** — confidence, routing, escalation and the disclaimer, emitted
    as one terminal event (see below).

### SSE event contract

Every event is `data: {json}\n\n`. The frontend depends on these types:

| `type` | When | Carries |
|---|---|---|
| `stage` | each stage starts/finishes | `stage`, `status`, `meta` (distances, counts) |
| `sources` | after Layer 3 | the passages sent to generation |
| `claim` | per drafted claim | claim text, source index |
| `claim_result` | per verified claim | `supported`, votes, citation |
| `refused` | Layer 1 or Layer 2 refusal | `refusal_stage`, result |
| `advisory` | always, last before `complete`, or after `refused` | see below |
| `complete` | success | answer, citations, claims, discarded |
| `provider_unavailable` | model rate-limited or unreachable | a user-facing message |
| `error` | unexpected exception | exception type and message |

The **advisory** event: `disclaimer`, `confidence` (`high` / `moderate` /
`low`), `escalate`, `escalation_reasons` (each tied to something the pipeline
observed), `escalation_guidance` (named bodies with URLs),
`regimes_in_coverage`, `regimes_out_of_coverage`, `prior_art_pointer`. It is
kept out of the answer text deliberately: these are statements *about* the
answer, not claims from a source, and must never be sent through Layer 2.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/ask?q=&history=&jurisdiction=` | Stream the pipeline as SSE. `history` is JSON (EventSource only supports GET). `jurisdiction` is `india` / `international`; anything else means no filter. |
| `POST` | `/api/translate` | `{text, language="Hindi"}` → `{translated}`. Translates an already-verified answer. |
| `GET` | `/api/config` | Active model and provider, corpus document count, per-jurisdiction counts. |
| `GET` | `/` | Serves `web/index.html`; `web/` is mounted as static files. |

## Modules (`src/`)

**Pipeline**

| Module | Role |
|---|---|
| `api.py` | FastAPI app, the four endpoints, SSE framing, history parsing |
| `generate.py` | The pipeline orchestrator and the advisory event |
| `retrieval.py` | Vector search against ChromaDB |
| `bm25_retrieval.py` | BM25 index and tokenizer; abstains when no query token matches |
| `hybrid_retrieval.py` | Reciprocal Rank Fusion and the jurisdiction filter |
| `confidence_gate.py` | Layer 1 — the 0.90 distance threshold |
| `verification.py` | Layer 2 — three-vote claim-support check |
| `citation.py` | Layer 3 — citation formatting and authority resolution |
| `relevance.py` | Optional relevance filter (off by default) |
| `coverage.py` | Advisory "does it answer the question" check |
| `translation.py` | Answer translation through the configured model |
| `llm_client.py` | The only seam to any model; provider switch, retries, rate-limit and unreachable handling |

**Domain**

| Module | Role |
|---|---|
| `authority.py` | Registry of all 20 documents: authority level, effective date, jurisdiction, regimes, amendment currency, source URL |
| `routing.py` | Which IP regimes a question touches; coverage derived from `authority.py`; ABS/TK triggers; TKDL pointer |
| `escalation.py` | Confidence label from measured distance; escalation reasons and contacts; standing disclaimer |
| `classification.py` | Deterministic six-category formulation classifier (see *Wiring status*) |
| `privacy.py` | Data inventory, retention statement, bounded decision audit trail (see *Wiring status*) |

**Corpus build**

| Module | Role |
|---|---|
| `parsing.py` | Per-page text extraction from PDF or text |
| `chunking.py` | Structure-aware chunker: sections, sub-sections, lettered clauses, treaty articles, schedules; build-time validator |
| `enrichment.py` | Adds cross-reference headings to the text used for *scoring* only — never to the text shown or cited |
| `embeddings.py` | bge-m3 wrapper |
| `indexing.py` | Builds the ChromaDB collection from `corpus/processed/` |
| `run_phase1.py` | Parse and chunk all 20 documents (per-document anchors, page windows, treaty style) |
| `run_phase2.py` | Build the vector index |

**Evaluation** — `run_phase3.py`, `run_phase5.py`, `run_phase6.py`,
`run_phase18.py`, `run_retrieval_eval.py`, `run_verification_eval.py`.

## Configuration

Set as environment variables or in a local `.env` (gitignored; template in
`.env.example`).

| Variable | Default | |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama`, `gemini` or `anthropic` |
| `OLLAMA_MODEL` | `qwen2.5:7b` | |
| `OLLAMA_NUM_CTX` | `8192` | Ollama silently truncates to 2,048 without this |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-2.5-flash` | |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | — / `claude-sonnet-5` | |
| `GENERATION_SEED` | `42` | |

## Corpus

20 primary instruments, 1,966 passages, committed pre-built so a fresh clone
serves without a 30-minute embedding step. 13 Indian (Acts, Rules, IPO
guidelines, one PIB release) and 7 international (TRIPS, CBD, Nagoya, PCT,
Madrid, WIPO GRATK, WIPO TK Toolkit). Each carries jurisdiction, regimes and an
`amendment_currency` statement — four Indian IP Acts are as-originally-enacted
and say so. Full provenance, retrieval dates and every rejected source are in
`corpus/manifest.md`.

Rebuild after changing a document: `python src/run_phase1.py`, then
`python src/run_phase2.py`. The build fails loudly on duplicate chunk IDs or
chunks over 20,000 characters, because the vector store would otherwise
overwrite duplicates silently.

## Testing

```bash
python -m pytest tests/        # 280 tests; every model call is mocked
```

Tests cover chunking regressions (one per real bug found), retrieval and
fusion, the BM25 abstention, jurisdiction filtering, Layer 1/2/3 behaviour,
provider failure handling, classification, routing, escalation, privacy
invariants, and the corpus build. End-to-end quality is measured separately by
the `run_phase*.py` evaluators against the live model.

## Wiring status

Two modules are implemented and tested but **not yet reachable by a user**:

- **`classification.py`** has no API endpoint and no UI. The decision tree and
  its structural abstentions work and are tested; nothing calls them.
- **`privacy.AUDIT`** is defined but never written to. The pipeline does not
  yet record an `AuditRecord` per question.

Both are listed as open work in `docs/phases.md`.

## Security and privacy

No accounts, no login, no server-side persistence of user content. The one
real exposure: server-sent events require GET, so a question travels in the
URL and appears in any access log — documented in `privacy.py` with its
remedy (move the pipeline to POST). API keys are read from the environment
only and are never committed.
