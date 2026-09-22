# TrueCite

An assistant for Ayurveda intellectual-property and regulatory questions that
checks every citation against the passage it came from before showing it —
and refuses, rather than guesses, when the law it holds cannot support an answer.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![tests](https://img.shields.io/badge/tests-280%20passing-brightgreen)](tests/)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

<p align="center">
  <img src="docs/assets/pipeline-poster.png" alt="The TrueCite pipeline: question, jurisdiction scope, hybrid retrieval, confidence gate, authority ordering, generation, claim verification, citation, coverage check, advisory, answer" width="760">
</p>

## Why it exists

Legal answers fail quietly. A 2025 Stanford study found that even production
legal-AI tools routinely cite a *real* source for a claim that source does not
actually make. Finding the right document is not enough — a system also has to
confirm the document says what it is about to claim. TrueCite enforces that at
every stage, not as a final filter, for a domain where the law is scattered
across patent, trade-mark, biodiversity, food and treaty regimes at once.

## How it works

A **fixed sequence, not an agent**. Every question runs the same stages in the
same order; nothing plans, loops, or decides its own next step. That rigidity is
what makes "verified" mean something.

1. **Jurisdiction scope** — India, international, or both. It decides which
   instruments are searched, so the two answer-sets are never mixed.
2. **Hybrid retrieval** — meaning-based vector search (BAAI/bge-m3, works across
   Hindi and English) fused with exact-term BM25 search.
3. **Layer 1, confidence gate** — if nothing retrieved is close enough, it
   refuses immediately, before any model is called.
4. **Layer 3, authority ordering** — Act, then Rules, Treaty, Guideline,
   Informational; more recent first.
5. **Generation** — every claim is tied to exactly one passage. No free prose.
6. **Layer 2, claim verification** — three independent checks ask whether that
   passage supports that claim; two must agree or the claim is discarded.
7. **Advisory** — a confidence level derived from the measured match (never from
   asking a model how sure it is), any area of law the question touches that
   the corpus does *not* cover, an offer to escalate to a named human body, and
   a standing "information, not legal advice" note.

Around that pipeline sit the domain tools: a **formulation classifier** that
asks the fewest questions needed to place a product in one of six regulatory
categories, **routing across IP types**, and an **access-and-benefit-sharing /
traditional-knowledge** path. Each is a deterministic decision, not a model
call, wherever the underlying legal test has a crisp answer.

<p align="center">
  <img src="docs/assets/app_02_answer.png" alt="A verified answer: one upheld claim with its citation, a coverage note, a moderate confidence reading, a traditional-knowledge prior-art pointer, an escalation offer and the disclaimer" width="820">
  <br><sub>A verified answer — the citation, how confident the match was, and where to go next.</sub>
</p>

<p align="center">
  <img src="docs/assets/app_03_refusal.png" alt="A refusal at the confidence gate, with low confidence and an expanded list of people to ask" width="820">
  <br><sub>A refusal — stopped at Layer 1, with the reason and who to ask instead.</sub>
</p>

## Results

Measured on the running system, not asserted.

| | |
|---|---|
| **False answers** | **0** in every evaluation run |
| Questions that must be refused | **2 of 2** refused |
| Answers citing the expected statute | 8 of 9 |
| Hindi and English questions reaching the right source | 10 of 10 each |
| Regimes whose statute ranks first in retrieval | 13 of 14 |

The one citation counted as a miss cited the *Biological Diversity (Amendment)
Act 2023, §6* where the 2002 Act was expected — the amendment rewrites that very
provision, so the expected answer was too narrow rather than the citation wrong.
Results vary between runs, so treat these as observations rather than
guarantees. An earlier suite of 96 runs on the original corpus, with two
question sets committed to git before they were ever run, also produced zero
false answers.

The weakness is the opposite of hallucination: **over-refusal**. When TrueCite
declines a question it can answer, retrieval has usually found the right
statute and verification has then been too strict.

## What it covers

Twenty primary instruments, 1,966 passages. Every document records its
jurisdiction, the areas of law it governs, and how current its text is.

| India | International |
|---|---|
| Patents Act 1970 · IPO AYUSH and TK guidelines | TRIPS Agreement |
| Trade Marks Act 1999 · GI Act 1999 · Designs Act 2000 | Convention on Biological Diversity |
| Copyright Act 1957 · Plant Varieties Act 2001 | Nagoya Protocol |
| Biological Diversity Act 2002 + 2023 Amendment + 2024 Rules | Patent Cooperation Treaty · Madrid Protocol |
| FSSAI Ayurveda Aahara Regulations 2022 | WIPO GRATK Treaty 2024 · WIPO TK Toolkit |

## Known limitations

Each is recorded with its evidence in `docs/`.

- **Four of the five Indian IP Acts are as-originally-enacted text**, without
  later amendments. Verified by counting amendment footnotes — none in the Trade
  Marks, GI, Designs and Plant Varieties files, 174 in the Copyright Act, which
  is consolidated. Every document states its own currency, so a stale text
  announces itself instead of being cited as current.
- **Three of six formulation categories cannot be answered** — new drug,
  phytopharmaceutical and cosmetic are defined by the Drugs and Cosmetics Act,
  which could not be sourced in an indexable form. TrueCite names that Act and
  abstains rather than reaching for a loosely related passage.
- **The advertising regime is not covered.** The only reachable copy of the
  Drugs and Magic Remedies Act was a departmental extract, not the Act.
- **Traditional Knowledge Digital Library records are not searchable here** —
  TKDL is restricted to patent offices. TrueCite points to it and says so.
- **Answer quality is capped by the configured model.** The app names it.
- **Questions travel in the request URL**, so any log of request URLs records
  them. Details in `src/privacy.py`.

## Running it locally

Requires Python 3.12. The parsed corpus and the vector index are committed, so
a fresh clone serves immediately.

```bash
python -m venv .venv
source .venv/Scripts/activate      # .venv\Scripts\activate on Windows cmd
pip install -r requirements.txt
uvicorn src.api:app --port 8000    # then open http://localhost:8000
```

By default it uses a local [Ollama](https://ollama.com) model (`qwen2.5:7b`).
To use a hosted model instead, copy `.env.example` to `.env` and set
`LLM_PROVIDER` and its key, or pass them inline:

```bash
LLM_PROVIDER=gemini GEMINI_API_KEY=... uvicorn src.api:app --port 8000
```

```bash
python -m pytest tests/            # 280 tests; model calls are mocked
```

Rebuilding the corpus from the source PDFs in `corpus/raw/` is only needed
after changing a document: `python src/run_phase1.py`, then
`python src/run_phase2.py`.

## License

[MIT](LICENSE). The full technical record — architecture, every non-obvious
decision with its evidence, and the evaluation sets — is in `docs/`; source
provenance is in `corpus/manifest.md`.

---

Built by [Sumanth Mamidi](https://github.com/SumanthMamidi-MNS). Developed for
SIH26045, Ministry of Ayush.
