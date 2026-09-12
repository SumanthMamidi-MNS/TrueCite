# PRD — IP-SAKTI Sahayak

### An AI assistant for Ayurveda IP & regulatory guidance

---

## 1. Official Problem Statement (SIH26045)

**Organization:** Ministry of Ayush
**Category:** Software
**PS Number:** SIH26045

> **IP-SAKTI Sahayak** — a multilingual, RAG-based (source-cited) AI assistant
> for Intellectual Property and regulatory guidance in Ayurveda, across
> national and international regimes.

**Restated plainly:** Ayurveda researchers, practitioners, and companies need
reliable answers about IP and regulatory rules (patents, traditional
knowledge protection, national and international compliance), but the
relevant information is scattered across incompatible sources — the Patents
Act 1970, Ayush-specific circulars, and WIPO/TKDL traditional-knowledge
material. Manual lookup is slow, and a wrong answer here has real
consequences (a missed filing deadline, a misunderstood disclosure rule).

---

## 2. Goals

- Answer Ayurveda IP/regulatory questions with citations traceable to a
  specific source document and section.
- Explicitly refuse to answer when the available documents don't actually
  support a confident answer — **never guess.**
- Handle both factual/structured queries (e.g. filing fees, deadlines) and
  narrative/explanatory queries (e.g. "how does India treat traditional
  knowledge disclosure?") correctly, through different retrieval paths.
- Be usable by someone in the actual target role (an Ayush IP officer or
  Ayurveda company researcher) without the builder standing next to them
  explaining it.

## 3. Non-Goals

- Not a general-purpose legal assistant — scope is Ayurveda IP/regulatory
  domain only.
- Not attempting production-scale concurrency — a working, correct
  single/low-user system is the target for this phase.
- Not replacing a qualified IP lawyer — this is a guidance and navigation
  tool, not a source of legal certainty.

## 4. Target User

An Ayurveda company's IP/regulatory point of contact, or a researcher
preparing a patent filing, who needs a fast, trustworthy first-pass answer
before (or instead of) manually searching primary documents.

**Usability bar:** could this person use it unsupervised and trust the
answer, or would they need you standing next to them explaining what it
really means? If the honest answer is "the second one," a feature isn't
done yet.

---

## 5. Core Design Principle

**The system must know when it doesn't know.**

This isn't a RAG-specific feature bolted on at the end — it's the design
philosophy for every component:

- Retrieval that isn't confident → say so, don't guess.
- A citation that doesn't actually support its claim → reject it, don't show it.
- A document that's outdated/superseded → surface the current one, don't
  silently cite the old one.

---

## 6. Functional Requirements

### 6.1 Query routing

- Structured/factual queries (fees, deadlines, filing statuses if a
  structured dataset exists) → direct lookup, never through embeddings.
- Narrative/explanatory queries → RAG pipeline below.

### 6.2 RAG pipeline (three-layer defense)

**Layer 1 — Retrieval confidence gate**
Retrieved chunks must clear a similarity threshold. Below it → refuse
immediately with an explicit "not enough grounded information" response.

**Layer 2 — Claim-support verification**
A separate LLM call checks: "Does this retrieved passage actually support
this specific claim?" (yes/no + reasoning). A citation that's real but
doesn't back the claim must be rejected — this is the specific failure mode
that even production legal-AI tools (Westlaw, LexisNexis) still exhibit,
per the 2025 Stanford/Magesh study. Closing this gap is the project's main
technical claim.

**Layer 3 — Temporal/authority tagging**
Every chunk is tagged with effective date and authority level (Act >
Ministry Circular > FAQ). If multiple versions of a rule exist, the system
must surface the current authoritative one, not just the most semantically
similar chunk.

### 6.3 Multilingual support

Embeddings and retrieval must work across at least English and Hindi at
minimum; verify retrieval quality per language independently rather than
assuming multilingual embeddings perform uniformly.

### 6.4 Citation format

Every generated claim must reference its source with document name, section,
and effective date, e.g. `[Source: Patents Act §3(p), effective 2023]`.

---

## 7. Technical Stack

| Component              | Choice                                                    | Reason                                                                        |
| ---------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Document parsing       | `unstructured` / `pypdf`                                  | Clean handling of legal PDF/text                                              |
| Chunking               | Structural (by section/sub-section), not fixed-token      | Legal cross-references break with naive chunking                              |
| Embeddings             | `BAAI/bge-m3`                                             | Multilingual, runs on 6GB VRAM or CPU                                         |
| Vector store           | ChromaDB (local)                                          | No infra overhead, fits hardware                                              |
| Keyword layer          | BM25 hybrid (`rank_bm25`)                                 | Legal text needs exact statute/section matching, not just semantic similarity |
| Generation             | Claude API                                                | Quality generation without competing for local VRAM against embeddings        |
| Verification (Layer 2) | Separate LLM call, deterministic-style yes/no + reasoning | Catches cited-but-wrong claims                                                |
| Interface              | CLI first → Streamlit/FastAPI once pipeline is proven     | Don't build UI before correctness is proven                                   |

---

## 8. Data Plan

- Ayush-specific IP guidelines (public Ministry circulars)
- Relevant sections of the Indian Patents Act, 1970
- WIPO Traditional Knowledge Digital Library (TKDL) public materials
- Sample regulatory FAQ-style documents
- Decide corpus scope before Day 1 — don't pad with irrelevant filler to
  inflate corpus size; a smaller clean corpus beats a large noisy one.

---

## 9. Build Plan (sequential phases — no fixed schedule)

Work continuously, phase by phase, until each is genuinely done — not until
a day runs out. Each phase gates the next; don't start a phase until the
one before it is verified working.

| Phase                         | Deliverable                                                                                                                                                                  | Gate before moving on                                                                                           |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 1 — Corpus & Chunking         | Corpus finalized. Parsing + structural chunking working.                                                                                                                     | Manually verify chunk quality on 10 samples — no broken cross-references.                                       |
| 2 — Basic Retrieval           | Embeddings + ChromaDB indexing. Vector-only retrieval working end-to-end.                                                                                                    | Retrieval returns sensible chunks for 5 hand-checked queries.                                                   |
| 3 — Hybrid Retrieval          | Add BM25 hybrid search.                                                                                                                                                      | Compare vector-only vs hybrid on 15 test questions — hybrid must genuinely outperform, not just add complexity. |
| 4 — Confidence + Verification | Layer 1 (confidence gate) + Layer 2 (claim-support verification) built.                                                                                                      | Deliberately feed it an unanswerable question and a wrong-citation case — both must be caught.                  |
| 5 — Authority & Citation      | Layer 3 (date/authority tagging). Citation-formatted generation.                                                                                                             | An outdated-vs-current version conflict test must resolve to the current source.                                |
| 6 — Evaluation                | Build 20–30 question eval set — unanswerable questions, outdated-terminology questions, multilingual questions. Measure citation accuracy, refusal rate, false-refusal rate. | Numbers exist and are written down, not just a gut feeling of "it works."                                       |
| 7 — Interface & Documentation | Minimal UI. README documenting architecture, the specific failure mode being solved, and all known limitations found during testing.                                         | A person outside your head could read the README and understand what it does and doesn't do.                    |

---

## 10. Success Criteria

- A question with strong document coverage → correct answer, citation
  verified to actually support the claim.
- A question answerable only by outdated material → system surfaces the
  current authoritative version instead.
- A question with no document coverage → explicit refusal, not a
  hallucinated answer.
- Every known limitation is discovered by testing and documented — not
  discovered by someone else later.

---

## 11. First instruction to give Claude Code

> "Read this PRD. Start with Phase 1 only: set up the project structure,
> implement document parsing and structural chunking, and show me chunk
> output on 3 sample documents before moving to Phase 2."

Review each phase's output before approving the next — don't let it run
ahead to Phase 5 in one pass. Move forward only when a phase is actually
verified working, regardless of how long that takes.
