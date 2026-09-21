# TrueCite

A source-cited RAG assistant for Ayurveda IP and regulatory guidance — every
citation is checked against the passage it claims to come from before it's
ever shown to you.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![tests](https://img.shields.io/badge/tests-208%20passing-brightgreen)](tests/)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

![TrueCite — the full verification pipeline, every step from question to cited answer](docs/assets/pipeline-poster.png)

## What this solves

Ayurveda researchers, practitioners, and companies need reliable answers
about IP and regulatory rules — patents, traditional knowledge protection,
national and international compliance — scattered across the Patents Act
1970, Ayush-specific IPO guidelines, and WIPO/TKDL material. A 2025
Stanford/Magesh study found that even production legal-AI tools (Westlaw,
LexisNexis) routinely cite a *real* source for a claim that source doesn't
actually support — retrieving the right document isn't enough, the system
also has to check that what it retrieved actually backs up what it's about
to say. That check, enforced at every layer rather than bolted on at the
end, is TrueCite's core technical claim: refuse when retrieval isn't
confident, reject a citation that's real but doesn't support the claim, and
prefer the more authoritative source when two sources disagree.

## How it works

The poster above is the actual explanation: hybrid retrieval → a confidence
gate that refuses rather than guesses → generation that ties every claim to
exactly one source passage → per-claim verification against that passage →
an authority-ranked citation.

It's a **fixed-sequence verification pipeline, not a multi-agent system** —
that distinction is deliberate. Every answer runs the same stages, in the
same order, every time; nothing here has a planner, decides its own next
action, or calls tools dynamically. That rigidity is what makes the pipeline
auditable and what makes "verified" a claim that actually means something.

On top of that engine sits the domain itself: an **India / international
jurisdiction switch** that keeps the two answer-sets from being conflated, a
**formulation-classification flow** that asks the minimum questions needed to
place a product in one of six regulatory categories, **routing across IP
types**, and an **ABS / traditional-knowledge** path. All of it is
deterministic where the decision is deterministic — a decision tree, not a
model, wherever the regulatory test has a crisp answer.

Every answer ends with an advisory: a confidence label derived from the
measured retrieval distance (not from asking a model how sure it is), the
standing "information, not legal advice" disclaimer, any regime the case
touches that the corpus has **no** source for, and an offer to escalate to a
named human body when the pipeline observed a reason to.

<img src="docs/assets/app_01_landing.png" alt="TrueCite's landing screen — suggested questions, corpus and model status in the sidebar" width="720">

Every reply shows its own work while it runs, then collapses to one line:

<img src="docs/assets/app_03_verified.png" alt="A verified answer — collapsed to one badge, with its citation and consulted sources beneath" width="720">

## Results

**Domain regimes, end to end.** Twelve questions spanning every regime added to
the corpus, plus two controls that must refuse — a suite where everything is
answerable cannot detect a system that has stopped refusing.

| | Result |
|---|---|
| Answered | 9 of 11 attempted |
| Cited the expected document | 8 of 9 answered |
| Correct refusals (controls) | **2 of 2** |
| **False answers** | **0** |

Three caveats stated rather than smoothed over. One question failed on an
infrastructure error (the local model returned a 500) and is excluded rather
than counted as a refusal. The single citation "miss" cited the **Biological
Diversity (Amendment) Act 2023 §6** where the expected answer was the 2002 Act
— the Amendment amends that very provision, so the ground truth was too narrow,
not the citation wrong. And results vary run to run: one regime refused in an
earlier run and answered in this one, so a single number here is an
observation, not a guarantee.

The two genuine declines both refused at claim-verification rather than
retrieval: the right statute *was* found, and verification then rejected every
drafted claim. That is over-refusal — the same weakness measured before the
corpus grew, which is the more useful result, because it shows quadrupling the
corpus did not introduce hallucination.

**Retrieval, measured separately.** 13 of 14 regimes return the expected
statute ranked first. Cross-lingual: a Hindi question and its English twin both
reach the expected source **10 out of 10 times** at the window the pipeline
actually uses.

### Earlier measurement (pre-expansion, 7-document corpus)


Measured across 96 question-runs (3 question sets × 3 seeded runs each,
worst-case number reported, not best): a dev set used to find and fix bugs,
plus two held-out sets authored and **committed to git before either was run**
(commit [`4a7a66d`](../../commit/4a7a66d351eb37e966256a6c0ac715be53e4b690))
specifically to catch overfitting.

| Set | Citation accuracy | Correct refusals | False answers |
|---|---|---|---|
| Dev (11+5) | 8/11 worst-case | 5/5 | 0/5 |
| Held-out v1 (10+5) | 5/10 worst-case | 5/5 | 0/5 |
| Held-out v2 (10+5) | 6/10 worst-case | 5/5 | 0/5 |

**Correct-refusal rate (5/5) and false-answer rate (0/5) held on every one
of the 96 runs, no exceptions.** The measured weakness is the opposite of
hallucination: over-refusal, concentrated in two diagnosed patterns
(generation drafting a claim from a plausible-but-wrong passage, and a
model-comprehension limit on relational "how does X interact with Y"
questions). Full methodology and per-question diagnosis: `docs/decisions.md`.

## Known limitations

Measured, not guessed. Each is recorded with its evidence in `docs/`.

- **Over-refusal, not hallucination**, remains the dominant failure mode — 0
  false answers across every evaluation run, but three of twelve regime
  questions were declined despite the right statute being retrieved.
- **Four of the five Indian IP Acts in the corpus are as-originally-enacted
  text**, with later amendments not folded in. Verified by counting amendment
  footnotes: zero in the Trade Marks, GI, Designs and Plant Varieties files,
  against 174 in the Copyright Act, which *is* consolidated. Concretely, the
  Trade Marks copy still describes the Appellate Board, abolished in 2021.
  Every document states its own currency, so a stale text announces itself
  rather than being cited as current.
- **Three of the six formulation categories cannot be answered at all** — new
  drug, phytopharmaceutical and cosmetic are defined by the Drugs and Cosmetics
  Act and its Rules, which could not be sourced in an indexable form. The
  system abstains and names the instrument to read instead, rather than
  reaching for a loosely-related passage. (It was caught doing exactly that:
  a cosmetic query matched the Biological Diversity Act, which merely uses the
  word.)
- **The advertising regime is uncovered.** The only reachable copy of the Drugs
  and Magic Remedies Act 1954 was a departmental extract rather than the Act,
  and was rejected.
- **Generation and verification quality is capped by the configured model.**
  The running app names the active one.
- **Questions travel in the URL query string**, because server-sent events
  require GET, so any component logging URLs records them. Stated rather than
  glossed; see `src/privacy.py`.
- **A relevance-filter stage is built but off by default** — the A/B that
  justified that was later found confounded, so its effect is honestly
  unmeasured rather than confirmed negative.

## Tech stack

A corpus of **20 primary legal instruments** (1,966 chunks) — Indian IP,
biodiversity, and food statutes plus the international treaties — each tagged
with its jurisdiction, the regimes it governs, and how current its text is.
Hybrid retrieval (BAAI/bge-m3 vector search + BM25 keyword search, fused with
Reciprocal Rank Fusion) over a structured, section-aware chunker built
for legal documents (not fixed-token splitting). Generation and Layer 2
verification run on a local Ollama model by default, swappable to Gemini or
Anthropic with one environment variable (`LLM_PROVIDER`).

## Running it locally

Requires Python 3.12. `corpus/processed/` (parsed+chunked corpus) and
`corpus/chroma_db/` (the prebuilt vector index) are committed, so a fresh
clone can go straight to serving — no corpus build step needed:

```bash
python -m venv .venv
source .venv/Scripts/activate   # or .venv\Scripts\activate on Windows cmd
pip install -r requirements.txt

uvicorn src.api:app --port 8000   # then open http://localhost:8000
```

The first start is slow — it loads the embedding stack before serving. By
default this uses a local [Ollama](https://ollama.com) install with
`qwen2.5:7b` pulled; to use Gemini or Anthropic instead:

```bash
LLM_PROVIDER=gemini GEMINI_API_KEY=... uvicorn src.api:app --port 8000
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... uvicorn src.api:app --port 8000
```

`corpus/raw/` (source PDFs) plus `python src/run_phase1.py` and
`src/run_phase2.py` are only needed if you want to rebuild the corpus and
index from scratch (~35 min on modest hardware) — otherwise skip them.

```bash
python -m pytest tests/    # 208 tests, all fast — live model calls are mocked
```

## Running it in a container

A `Dockerfile` at the repo root builds a self-contained image (serves on port
8000, ships the prebuilt corpus and index, so there's no re-embedding step):

```bash
docker build -t truecite .
docker run -p 8000:8000 -e LLM_PROVIDER=gemini -e GEMINI_API_KEY=... truecite
```

There is no hosted instance. The app needs roughly 3-4 GB of RAM (the bge-m3
embedding model plus PyTorch), which rules out the 512 MB free tiers; running
it locally or in the container above is the supported path.

## License

[MIT](LICENSE) — see `docs/` for the full technical write-up (architecture,
every non-obvious decision with its evidence, the build log, and the
evaluation question set), and `corpus/manifest.md` for source provenance.

---

Built by [Sumanth Mamidi](https://github.com/SumanthMamidi-MNS) — [source](https://github.com/SumanthMamidi-MNS/TrueCite). Originally
developed as **IP-SAKTI Sahayak** for SIH26045 (Smart India Hackathon,
Ministry of Ayush); renamed for its public release.
