"""Phase 6 gate: run the eval set through the real end-to-end pipeline and
measure citation accuracy, refusal rate, and false-refusal rate.

Question set drawn from docs/eval_questions.md categories A (single-doc
answerable), B (cross-doc answerable), and C (deliberately unanswerable).
Categories D (authority-conflict) and E (multilingual) are excluded here —
D has no genuine conflicting-rule pair in this corpus to score against, and
E has no Hindi corpus content yet; both are documented gaps, not silently
skipped (see docs/eval_questions.md, docs/decisions.md).

Not part of the automated pytest suite — many live local-LLM calls (a
generation + up to 3 verification calls per claim, per question), so this
is a manual gate script like run_phase2/3/5.py, not something to run on
every commit.

Run: .venv/Scripts/python.exe src/run_phase6.py
"""
import json
import sys
import time
from pathlib import Path

from generate import answer_query

RESULTS_PATH = Path(__file__).resolve().parent.parent / "corpus" / "eval_results" / "phase6_results.json"

# (query, {acceptable doc_ids}). Several questions have more than one genuinely
# correct source — e.g. the Patents Act's own §10(4)(ii)(D) AND the TK
# Guidelines both correctly state the biological-material disclosure rule, one
# more authoritative and one more explanatory. An earlier version of this list
# used a single expected doc_id per question and undercounted correct answers
# whenever the system found a different-but-equally-valid source; corrected
# after verifying each case against the actual chunk text, not guessed.
ANSWERABLE = [
    ("Can an invention that is essentially traditional knowledge be patented in India?", {"patents_act_1970", "ipo_tk_biological_material_guidelines_2012"}),
    ("What must a patent applicant do if their invention uses biological material sourced from India?", {"patents_act_1970", "ipo_tk_biological_material_guidelines_2012"}),
    ("What database do patent examiners use to check for prior art in traditional Indian medicine?", {"ipo_tk_biological_material_guidelines_2012", "ipo_ayush_examination_guidelines_2025"}),
    ("As of March 2013, how many patents had been granted to Indian entities for Ayurvedic-medicine-related inventions?", {"pib_faq_patents_traditional_ayurvedic_medicine_2013"}),
    ("What systems of medicine does AYUSH cover?", {"ipo_ayush_examination_guidelines_2025"}),
    ("What happens if a patent applicant wrongly discloses the geographical origin of biological material used in their invention?", {"patents_act_1970", "ipo_tk_biological_material_guidelines_2012"}),
    ("Is a mere discovery of a new property of a known substance patentable in India?", {"patents_act_1970"}),
    ("What are the three phases the WIPO toolkit divides TK documentation into?", {"wipo_documenting_tk_toolkit"}),
    ("Under what section of the Biological Diversity Act, 2002 must approval be sought before filing a patent application based on Indian biological resources?", {"ipo_tk_biological_material_guidelines_2012", "pib_faq_patents_traditional_ayurvedic_medicine_2013"}),
    ("What is the penalty under the Biological Diversity Act, 2002 for contravening its access provisions?", {"ipo_tk_biological_material_guidelines_2012"}),
    ("How does India's approach to protecting traditional knowledge in patent law interact with its TRIPS obligations?", {"pib_faq_patents_traditional_ayurvedic_medicine_2013"}),
]

UNANSWERABLE = [
    "What is the current government filing fee for a patent application in India?",
    "How does the European Patent Office treat traditional-knowledge-based patent applications?",
    "What was the outcome of the Neem patent case (EPO opposition)?",
    "Can a company patent a yoga asana (posture) sequence in the United States?",
    "What is the boiling point of water at sea level?",
]


def main(relevance_filter: bool = True, results_path: Path = RESULTS_PATH):
    """`relevance_filter` exists so this script can A/B Stage 3 (see
    src/relevance.py) against the false-refusal rate before trusting it in
    the UI — run once with it on, once with it off, compare. Per-question
    wall time is recorded so the two runs' latency cost is measured, not
    guessed (see docs/decisions.md for why that matters for this stage).
    """
    results = []

    print("=" * 70)
    print(f"ANSWERABLE QUESTIONS (relevance_filter={relevance_filter})")
    print("=" * 70)
    correct_citation = 0
    false_refusals = 0
    for query, expected_doc_ids in ANSWERABLE:
        t0 = time.time()
        r = answer_query(query, relevance_filter=relevance_filter)
        elapsed = round(time.time() - t0, 1)
        cited_doc_ids = {c["doc_id"] for c in r["claims"]}
        got_it_right = (not r["refused"]) and bool(cited_doc_ids & expected_doc_ids)
        if r["refused"]:
            false_refusals += 1
        elif got_it_right:
            correct_citation += 1
        status = "OK" if got_it_right else ("FALSE REFUSAL" if r["refused"] else "WRONG/PARTIAL CITATION")
        print(f"[{status}] ({elapsed}s) {query[:65]}")
        print(f"   expected any of={sorted(expected_doc_ids)} got={sorted(cited_doc_ids) if cited_doc_ids else '(refused)'}")
        results.append({
            "query": query, "category": "answerable", "expected_doc_ids": sorted(expected_doc_ids),
            "elapsed_seconds": elapsed, **r,
        })

    print()
    print("=" * 70)
    print("UNANSWERABLE QUESTIONS")
    print("=" * 70)
    correctly_refused = 0
    for query in UNANSWERABLE:
        t0 = time.time()
        r = answer_query(query, relevance_filter=relevance_filter)
        elapsed = round(time.time() - t0, 1)
        if r["refused"]:
            correctly_refused += 1
        status = "OK (refused)" if r["refused"] else "FALSE ANSWER (should have refused)"
        print(f"[{status}] ({elapsed}s) {query[:65]}")
        if not r["refused"]:
            print(f"   answered: {r['answer'][:150]}")
        results.append({
            "query": query, "category": "unanswerable", "expected_doc_id": None,
            "elapsed_seconds": elapsed, **r,
        })

    n_answerable = len(ANSWERABLE)
    n_unanswerable = len(UNANSWERABLE)
    avg_elapsed = round(sum(r["elapsed_seconds"] for r in results) / len(results), 1)
    print()
    print("=" * 70)
    print("METRICS")
    print("=" * 70)
    print(f"Citation accuracy (of answerable questions, correct source cited): {correct_citation}/{n_answerable}")
    print(f"False-refusal rate (answerable questions incorrectly refused):     {false_refusals}/{n_answerable}")
    print(f"Correct-refusal rate (unanswerable questions correctly refused):   {correctly_refused}/{n_unanswerable}")
    print(f"False-answer rate (unanswerable questions incorrectly answered):   {n_unanswerable - correctly_refused}/{n_unanswerable}")
    print(f"Average time per question:                                        {avg_elapsed}s")

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Full results written to {results_path}")


if __name__ == "__main__":
    relevance_filter = "--no-relevance-filter" not in sys.argv
    suffix = "" if relevance_filter else "_no_relevance_filter"
    out_path = RESULTS_PATH.with_name(f"phase6_results{suffix}.json")
    main(relevance_filter=relevance_filter, results_path=out_path)
