"""Retrieval-only evaluation: measure what retrieval alone delivers, with no LLM in the loop.

Why this exists as a separate harness from run_phase6.py
-------------------------------------------------------
run_phase6.py runs the full pipeline, so every number it produces is a blend of
retrieval quality *and* generation/verification quality, measured through a
sampling local model that gives different answers run to run. That makes it the
wrong instrument for the question "did this retrieval change help?" — it is slow
(~25s/question), noisy, and it cannot see a retrieval defect at all if generation
happens to paper over it.

It also has a blind spot that motivated this file. run_phase6.py scores a
citation as correct when the cited *document* is right. But the Biological
Diversity Act penalty question was retrieving §56 ("Penalty for contravention of
directions or orders...") instead of §55 ("Penalties" — the one that actually
answers it). Both live in the same document, so document-level scoring calls that
a hit. Passage-level scoring calls it what it is: the wrong section.

So this harness is deterministic (no LLM calls at all), fast, and scores at
PASSAGE level as well as document level. It is the instrument retrieval changes
are accepted or rejected against.

Run: .venv/Scripts/python.exe src/run_retrieval_eval.py
     .venv/Scripts/python.exe src/run_retrieval_eval.py --json-out corpus/eval_results/retrieval_before.json
"""
import argparse
import json
import sys
from pathlib import Path

from confidence_gate import CONFIDENCE_THRESHOLD
from generate import _select_grounded_hits_with_diagnostics
from hybrid_retrieval import retrieve_hybrid
from bm25_retrieval import retrieve_bm25
from retrieval import retrieve as retrieve_vector
from run_phase6 import ANSWERABLE, UNANSWERABLE

RESULTS_PATH = Path(__file__).resolve().parent.parent / "corpus" / "eval_results" / "retrieval_eval.json"


def _load_questions(path: Path) -> tuple[list[tuple[str, set[str]]], list[str], dict]:
    """Load (answerable, unanswerable, gold) from a questions file like
    docs/heldout_questions.json, instead of this module's own hand-authored
    GOLD table and run_phase6's dev-set ANSWERABLE/UNANSWERABLE.

    Gold chunks come from each question's `gold_chunks`; gold docs from its
    `expected_doc_ids`. An empty `gold_chunks` list (a question with only
    document-level ground truth) produces an empty `chunks` set, which
    `evaluate_question` already treats as "not passage-scored" — same
    behavior as the built-in GOLD table's own doc-only entries.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    answerable = [(q["query"], set(q["expected_doc_ids"])) for q in data["answerable"]]
    unanswerable = [q["query"] for q in data["unanswerable"]]
    gold = {
        q["query"]: {
            "chunks": set(q.get("gold_chunks") or []),
            "docs": set(q["expected_doc_ids"]),
        }
        for q in data["answerable"]
    }
    return answerable, unanswerable, gold

SEARCH_DEPTH = 40
TOP_K = 8

# Gold passages, transcribed from the **Source:** lines already hand-authored in
# docs/eval_questions.md — not new ground truth invented here. Two transcription
# notes, both verified against the actual chunk text rather than assumed:
#
#   - docs/eval_questions.md writes `patents_act_1970::sec-3` for Q1 and Q7, but
#     no such chunk exists: §3 is long and is split per lettered clause
#     (sec-3-clause-a ... sec-3-clause-p, see docs/decisions.md on lettered-clause
#     chunking). The doc's `::sec-3` is shorthand for the section. The specific
#     clause that answers each question is used here instead, confirmed by reading
#     the text: §3(p) is the traditional-knowledge exclusion (Q1), §3(d) is the
#     "mere discovery of a new property of a known substance" exclusion (Q7).
#   - Some **Source:** lines name only a document, with no section (Q2, Q3's
#     second source, Q8). Those get document-level gold only; `chunks` is left
#     empty and passage-level recall is not scored for them rather than inventing
#     a passage the doc never named.
GOLD = {
    "Can an invention that is essentially traditional knowledge be patented in India?": {
        "chunks": {"patents_act_1970::sec-3-clause-p"},
        "docs": {"patents_act_1970", "ipo_tk_biological_material_guidelines_2012"},
    },
    # The doc set here intentionally includes the PIB release, which
    # run_phase6.ANSWERABLE's set for this same question does not. The two are
    # different instruments and the divergence is deliberate: run_phase6 scores
    # CITATION accuracy against its own (unchanged) expected sources, while this
    # harness scores whether RETRIEVAL can surface any passage that answers the
    # question. `::para-3` does answer it — "Section 6(i) of the Biological
    # Diversity Act, 2002 requires an applicant to obtain the previous approval
    # of the National Biodiversity Authority before applying for a patent for any
    # invention based on biological resources obtained from India" — and
    # docs/eval_questions.md names it for this question. Widening run_phase6's
    # set instead would loosen the citation metric, which was deliberately not
    # done; only the two Biological Diversity Act entries were corrected there,
    # each with its own evidence.
    "What must a patent applicant do if their invention uses biological material sourced from India?": {
        "chunks": {"pib_faq_patents_traditional_ayurvedic_medicine_2013::para-3"},
        "docs": {"patents_act_1970", "ipo_tk_biological_material_guidelines_2012",
                 "pib_faq_patents_traditional_ayurvedic_medicine_2013"},
    },
    "What database do patent examiners use to check for prior art in traditional Indian medicine?": {
        "chunks": {"ipo_tk_biological_material_guidelines_2012::preamble"},
        "docs": {"ipo_tk_biological_material_guidelines_2012", "ipo_ayush_examination_guidelines_2025"},
    },
    "As of March 2013, how many patents had been granted to Indian entities for Ayurvedic-medicine-related inventions?": {
        "chunks": {"pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2"},
        "docs": {"pib_faq_patents_traditional_ayurvedic_medicine_2013"},
    },
    "What systems of medicine does AYUSH cover?": {
        "chunks": {"ipo_ayush_examination_guidelines_2025::preamble"},
        "docs": {"ipo_ayush_examination_guidelines_2025"},
    },
    "What happens if a patent applicant wrongly discloses the geographical origin of biological material used in their invention?": {
        "chunks": {"patents_act_1970::sec-25-sub-1", "patents_act_1970::sec-25-sub-2"},
        "docs": {"patents_act_1970", "ipo_tk_biological_material_guidelines_2012"},
    },
    "Is a mere discovery of a new property of a known substance patentable in India?": {
        "chunks": {"patents_act_1970::sec-3-clause-d"},
        "docs": {"patents_act_1970"},
    },
    "What are the three phases the WIPO toolkit divides TK documentation into?": {
        "chunks": set(),
        "docs": {"wipo_documenting_tk_toolkit"},
    },
    "Under what section of the Biological Diversity Act, 2002 must approval be sought before filing a patent application based on Indian biological resources?": {
        "chunks": {"biological_diversity_act_2002::sec-6"},
        "docs": {"biological_diversity_act_2002", "ipo_tk_biological_material_guidelines_2012",
                 "pib_faq_patents_traditional_ayurvedic_medicine_2013"},
    },
    "What is the penalty under the Biological Diversity Act, 2002 for contravening its access provisions?": {
        "chunks": {"biological_diversity_act_2002::sec-55"},
        "docs": {"biological_diversity_act_2002", "ipo_tk_biological_material_guidelines_2012"},
    },
    # docs/eval_questions.md names `::para-3` as this question's source, but that
    # is a transcription error in the doc, found while building this harness and
    # verified by reading both chunks: para-3 is about the Biological Diversity
    # Act §6(i) prior-approval requirement and contains no mention of TRIPS at
    # all. The TRIPS discussion ("Under the Agreement on Trade Related
    # Intellectual Property Rights (TRIPS Agreement) to which India is
    # committed...") is in para-2. Scored against para-2 here; the doc is
    # corrected to match.
    "How does India's approach to protecting traditional knowledge in patent law interact with its TRIPS obligations?": {
        "chunks": {"pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2"},
        "docs": {"pib_faq_patents_traditional_ayurvedic_medicine_2013"},
    },
}

# Genuinely-unrelated controls from the original Layer 1 calibration
# (confidence_gate.py's docstring). These must stay ABOVE the distance
# threshold — i.e. stopped at the gate. A retrieval change that starts pulling
# these in is making irrelevant chunks look relevant, which is the one thing
# retrieval work here must never do.
UNRELATED_CONTROLS = [
    "What are the rules of cricket?",
    "How do I bake a chocolate cake?",
    "What is the boiling point of water at sea level?",
    "How is a Delaware LLC taxed?",
]


def rank_of(hits: list[dict], gold_chunks: set[str]) -> int | None:
    """1-based rank of the first gold chunk, or None if absent from `hits`.

    None is deliberately distinct from a large rank: "not found within the
    search depth" is a different fact from "found, but ranked badly", and
    collapsing the two would hide exactly the defect this harness was built to
    catch. Callers render None as ">N".
    """
    for i, h in enumerate(hits, start=1):
        if h["chunk_id"] in gold_chunks:
            return i
    return None


def doc_rank_of(hits: list[dict], gold_docs: set[str]) -> int | None:
    for i, h in enumerate(hits, start=1):
        if h["metadata"]["doc_id"] in gold_docs:
            return i
    return None


def _fmt(rank: int | None, depth: int = SEARCH_DEPTH) -> str:
    return f">{depth}" if rank is None else str(rank)


def evaluate_question(query: str, gold: dict) -> dict:
    gold_chunks, gold_docs = gold["chunks"], gold["docs"]

    vector_hits = retrieve_vector(query, top_k=SEARCH_DEPTH)
    bm25_hits = retrieve_bm25(query, top_k=SEARCH_DEPTH)
    hybrid_hits = retrieve_hybrid(query, top_k=SEARCH_DEPTH, candidate_k=SEARCH_DEPTH)
    # The real selection path, including Layer 1 and the authority re-sort —
    # this is what generation actually receives, which is the number that
    # matters. Measuring only raw retriever rank would miss a gold chunk being
    # ranked well but then dropped by the gate or pushed out by authority order.
    final_hits, diag = _select_grounded_hits_with_diagnostics(query, TOP_K)

    return {
        "query": query,
        "gold_chunks": sorted(gold_chunks),
        "gold_docs": sorted(gold_docs),
        "passage_rank": {
            "vector": rank_of(vector_hits, gold_chunks) if gold_chunks else None,
            "bm25": rank_of(bm25_hits, gold_chunks) if gold_chunks else None,
            "hybrid": rank_of(hybrid_hits, gold_chunks) if gold_chunks else None,
            "final": rank_of(final_hits, gold_chunks) if gold_chunks else None,
        },
        "passage_scored": bool(gold_chunks),
        "passage_recall_at_8": bool(gold_chunks) and rank_of(final_hits, gold_chunks) is not None,
        "passage_recall_at_40": bool(gold_chunks) and rank_of(hybrid_hits, gold_chunks) is not None,
        "doc_rank_final": doc_rank_of(final_hits, gold_docs),
        "doc_recall_at_8": doc_rank_of(final_hits, gold_docs) is not None,
        "best_distance": diag["best_distance"],
        "gate_passed": diag["gate_passed"],
        "confident_candidates": diag.get("confident_candidates"),
        "final_selected": len(final_hits),
    }


def main(
    json_out: Path = RESULTS_PATH,
    answerable: list[tuple[str, set[str]]] = ANSWERABLE,
    gold: dict = GOLD,
    unanswerable: list[str] = UNANSWERABLE,
) -> dict:
    """`answerable`/`gold`/`unanswerable` default to this module's own
    built-in dev-set question list and hand-authored GOLD table, but are
    threaded through as parameters (never mutated) so the CLI's --questions
    flag can swap in a different question set — e.g.
    docs/heldout_questions.json via `_load_questions` — without touching the
    dev-set data other tests and scripts still rely on.
    """
    answerable_rows = []
    print("=" * 108)
    print("PASSAGE-LEVEL RETRIEVAL EVAL (no LLM calls — deterministic)")
    print("=" * 108)
    print(f"{'#':>2}  {'vec':>5} {'bm25':>5} {'hyb':>5} {'fin':>5}  {'dist':>6} {'gate':>5}  question")
    print("-" * 108)

    for i, (query, _expected_docs) in enumerate(answerable, start=1):
        q_gold = gold.get(query)
        if q_gold is None:
            print(f"{i:>2}  !! no GOLD entry for: {query[:70]}")
            continue
        row = evaluate_question(query, q_gold)
        answerable_rows.append(row)
        pr = row["passage_rank"]
        if not row["passage_scored"]:
            # No passage-level gold was ever authored for this question, so the
            # rank columns are "not measured", NOT ">40". Rendering an unscored
            # row as a miss would be a lie in the direction that flatters
            # nothing but confuses everything.
            cols = f"{'n/a':>5} {'n/a':>5} {'n/a':>5} {'n/a':>5}"
            note = "   (doc-level gold only - passage not scored)"
        else:
            cols = (f"{_fmt(pr['vector']):>5} {_fmt(pr['bm25']):>5} "
                    f"{_fmt(pr['hybrid']):>5} {_fmt(pr['final'], TOP_K):>5}")
            note = "" if row["passage_recall_at_8"] else "   <-- gold passage NOT in top-8"
        print(
            f"{i:>2}  {cols}  {row['best_distance']:.3f} {str(row['gate_passed']):>5}  {query[:52]}{note}"
        )

    scored_rows = [r for r in answerable_rows if r["passage_scored"]]
    passage_at_8 = sum(r["passage_recall_at_8"] for r in scored_rows)
    passage_at_40 = sum(r["passage_recall_at_40"] for r in scored_rows)
    doc_at_8 = sum(r["doc_recall_at_8"] for r in answerable_rows)

    print("-" * 108)
    print(f"Passage-level recall@{TOP_K} (into generation): {passage_at_8}/{len(scored_rows)}")
    print(f"Passage-level recall@{SEARCH_DEPTH} (hybrid)    : {passage_at_40}/{len(scored_rows)}")
    print(f"Document-level recall@{TOP_K}                 : {doc_at_8}/{len(answerable_rows)}")

    print()
    print("=" * 108)
    print("UNANSWERABLE — must be refused (gate stops them, or Layer 2 does downstream)")
    print("=" * 108)
    unanswerable_rows = []
    for q in unanswerable:
        _hits, diag = _select_grounded_hits_with_diagnostics(q, TOP_K)
        unanswerable_rows.append({"query": q, "best_distance": diag["best_distance"], "gate_passed": diag["gate_passed"]})
        print(f"  dist={diag['best_distance']:.3f}  gate_passed={str(diag['gate_passed']):>5}  {q[:70]}")

    print()
    print("=" * 108)
    print("UNRELATED CONTROLS — gate MUST stop every one of these")
    print("=" * 108)
    control_rows = []
    controls_ok = True
    for q in UNRELATED_CONTROLS:
        _hits, diag = _select_grounded_hits_with_diagnostics(q, TOP_K)
        ok = not diag["gate_passed"]
        controls_ok = controls_ok and ok
        control_rows.append({"query": q, "best_distance": diag["best_distance"], "gate_passed": diag["gate_passed"], "ok": ok})
        print(f"  dist={diag['best_distance']:.3f}  stopped={str(ok):>5}  {'' if ok else '<-- REGRESSION '}{q[:70]}")

    summary = {
        "passage_recall_at_8": [passage_at_8, len(scored_rows)],
        "passage_recall_at_40": [passage_at_40, len(scored_rows)],
        "doc_recall_at_8": [doc_at_8, len(answerable_rows)],
        "unrelated_controls_all_stopped": controls_ok,
        "threshold": CONFIDENCE_THRESHOLD,
        "search_depth": SEARCH_DEPTH,
        "top_k": TOP_K,
    }
    print()
    print("SUMMARY:", json.dumps(summary))

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(
            {"summary": summary, "answerable": answerable_rows,
             "unanswerable": unanswerable_rows, "controls": control_rows},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {json_out}")
    return summary


def _exit_code(summary: dict) -> int:
    """1 iff an unrelated control stopped being stopped at the gate — the one
    hard safety regression this harness exists to catch. 0 for every softer
    recall/precision miss, including a bad passage or document rank, so this
    harness stays a measuring instrument and not a second pass/fail gate for
    ordinary retrieval-quality changes.

    Previously `sys.exit(0 if main(...) else 0)` always exited 0 regardless of
    `main`'s return value — a control-question regression was printed with
    "<-- REGRESSION" but never failed the process.
    """
    return 0 if summary["unrelated_controls_all_stopped"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--questions", type=Path, default=None,
        help="Load answerable/unanswerable questions and gold from this "
             "file (e.g. docs/heldout_questions.json) instead of "
             "run_phase6's dev-set lists and this module's own GOLD table. "
             "The default --json-out filename gets a suffix derived from "
             "the file's stem so dev-set results are never overwritten.",
    )
    args = parser.parse_args()

    answerable, unanswerable, gold = ANSWERABLE, UNANSWERABLE, GOLD
    json_out = args.json_out
    if args.questions:
        answerable, unanswerable, gold = _load_questions(args.questions)
        if json_out is None:
            json_out = RESULTS_PATH.with_name(f"retrieval_eval_{args.questions.stem}.json")
    if json_out is None:
        json_out = RESULTS_PATH

    sys.exit(_exit_code(main(json_out, answerable=answerable, gold=gold, unanswerable=unanswerable)))
