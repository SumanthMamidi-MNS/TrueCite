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
import argparse
import json
import statistics
import time
from pathlib import Path

import llm_client
import verification
from generate import answer_query

RESULTS_PATH = Path(__file__).resolve().parent.parent / "corpus" / "eval_results" / "phase6_results.json"


def _load_questions(path: Path) -> tuple[list[tuple[str, set[str]]], list[str]]:
    """Load an (ANSWERABLE, UNANSWERABLE)-shaped pair from a questions file
    like docs/heldout_questions.json, instead of this module's own built-in
    dev-set lists. File shape: {"answerable": [{"query", "expected_doc_ids",
    ...}], "unanswerable": [{"query", ...}]} — see docs/heldout_questions.json's
    own "_about" field for the held-out set's provenance and pre-commitment.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    answerable = [(q["query"], set(q["expected_doc_ids"])) for q in data["answerable"]]
    unanswerable = [q["query"] for q in data["unanswerable"]]
    return answerable, unanswerable

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
    # 2026-09-16: `biological_diversity_act_2002` added to both of the next two
    # entries. This is a correction to a stale measuring instrument, not a
    # loosening of the bar to flatter a metric, and the evidence is:
    #
    #   1. Both questions ask explicitly about the Biological Diversity Act. The
    #      Act's own text is the MOST authoritative correct source for each, and
    #      it is in the corpus.
    #   2. The chunks state the expected answers verbatim.
    #      `::sec-6` — "No person shall apply for any intellectual property
    #      right, by whatever name called, in or outside India for any invention
    #      based on any research or information on a biological resource obtained
    #      from India without obtaining the previous approval of the National
    #      Biodiversity Authority before making such application".
    #      `::sec-55` — "Whoever contravenes ... the provisions of section 3 or
    #      section 4 or section 6 shall be punishable with imprisonment for a
    #      term which may extend to five years, or with fine which may extend to
    #      ten lakh rupees".
    #   3. docs/eval_questions.md has named `biological_diversity_act_2002::sec-6`
    #      and `::sec-55` as these questions' sources since 2026-09-13. Only this
    #      list lagged — the doc was updated when the Act was added and the code
    #      was not.
    #   4. This list was last edited 2026-09-12 (commit b4ed57c); the Act entered
    #      the corpus 2026-09-13 (commit 707fded). A ground-truth list written
    #      before a document existed cannot have considered it. Commit 4152250
    #      touched this file but not these sets.
    #
    # Direction of the change: it makes the citation-accuracy metric EASIER, so
    # post-correction figures are NOT comparable to pre-correction ones. The
    # pre-correction number is kept alongside in README.md rather than replaced.
    # No other entry was widened.
    ("Under what section of the Biological Diversity Act, 2002 must approval be sought before filing a patent application based on Indian biological resources?", {"biological_diversity_act_2002", "ipo_tk_biological_material_guidelines_2012", "pib_faq_patents_traditional_ayurvedic_medicine_2013"}),
    ("What is the penalty under the Biological Diversity Act, 2002 for contravening its access provisions?", {"biological_diversity_act_2002", "ipo_tk_biological_material_guidelines_2012"}),
    ("How does India's approach to protecting traditional knowledge in patent law interact with its TRIPS obligations?", {"pib_faq_patents_traditional_ayurvedic_medicine_2013"}),
]

UNANSWERABLE = [
    "What is the current government filing fee for a patent application in India?",
    "How does the European Patent Office treat traditional-knowledge-based patent applications?",
    "What was the outcome of the Neem patent case (EPO opposition)?",
    "Can a company patent a yoga asana (posture) sequence in the United States?",
    "What is the boiling point of water at sea level?",
]


def main(
    relevance_filter: bool = False,
    results_path: Path = RESULTS_PATH,
    answerable: list[tuple[str, set[str]]] = ANSWERABLE,
    unanswerable: list[str] = UNANSWERABLE,
    questions_file: Path | None = None,
):
    """`relevance_filter` exists so this script can A/B Stage 3 (see
    src/relevance.py) against the false-refusal rate before trusting it in
    the UI — run once with it on, once with it off, compare. Defaults to
    False (off) to match generate.answer_query's own default: the filter was
    measured to hurt the false-refusal rate and is disabled in the shipped
    pipeline, so a bare run of this script measures what ships. Per-question
    wall time is recorded so the two runs' latency cost is measured, not
    guessed (see docs/decisions.md for why that matters for this stage).

    `answerable`/`unanswerable` default to this module's own dev-set lists
    (ANSWERABLE/UNANSWERABLE) but are threaded through as parameters, never
    mutated, so a caller (the CLI's --questions flag, or run_many) can swap
    in a different question set — e.g. docs/heldout_questions.json — without
    touching the dev-set lists other tests and scripts still rely on.
    `questions_file`, if given, is recorded in the returned dict only for
    provenance (which set produced these numbers); it changes no logic here.
    """
    results = []

    print("=" * 70)
    print(f"ANSWERABLE QUESTIONS (relevance_filter={relevance_filter})")
    print("=" * 70)
    correct_citation = 0
    false_refusals = 0
    for query, expected_doc_ids in answerable:
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
    for query in unanswerable:
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

    n_answerable = len(answerable)
    n_unanswerable = len(unanswerable)
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

    return {
        "citation_accuracy": correct_citation,
        "false_refusals": false_refusals,
        "correct_refusals": correctly_refused,
        "false_answers": n_unanswerable - correctly_refused,
        "n_answerable": n_answerable,
        "n_unanswerable": n_unanswerable,
        "avg_elapsed": avg_elapsed,
        "questions_file": str(questions_file) if questions_file else None,
        # Per-question pass/fail, so run_many can report WHICH questions are
        # unstable rather than only that the totals moved.
        "per_question": {
            r["query"]: (not r["refused"]) and bool(
                {c["doc_id"] for c in r["claims"]} & set(r.get("expected_doc_ids") or [])
            )
            for r in results
            if r["category"] == "answerable"
        },
    }


def _reseed(run_index: int, seed_base: int) -> dict:
    """Point generation and verification at a distinct, recorded seed set.

    Set directly on the module objects rather than through the environment so a
    single process can do several runs without reimporting the (slow) embedding
    and Chroma stack. Every seed used is returned and written into the results
    file, so any recorded number can be reproduced exactly.
    """
    import generate
    import verification

    offset = run_index * 1000
    generation_seed = seed_base + offset
    verification_seeds = tuple(seed_base + offset + 100 * (i + 1) for i in range(3))
    generate.GENERATION_SEED = generation_seed
    verification.VERIFICATION_SEEDS = verification_seeds
    return {"generation_seed": generation_seed, "verification_seeds": list(verification_seeds)}


def _summarize(values: list[int]) -> dict:
    """min/median/max across runs.

    `statistics.median` (not `ordered[len(ordered) // 2]`) so an even run
    count reports the true median — the average of the two middle values —
    rather than silently the upper-middle one. With `--runs 2` the old code
    reported ordered[1], i.e. the BETTER of the two runs, exactly backwards
    for a script whose own docstring says to report the worst case.
    """
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
        "runs": values,
    }


def run_many(
    runs: int,
    seed_base: int,
    relevance_filter: bool,
    suffix: str,
    answerable: list[tuple[str, set[str]]] = ANSWERABLE,
    unanswerable: list[str] = UNANSWERABLE,
    questions_file: Path | None = None,
) -> dict:
    """Run the eval `runs` times at different seeds and report a RANGE.

    A single run's numbers are not trustworthy on this stack, and that is a
    measured fact rather than a precaution: two questions flipped between
    refused and correctly-answered across consecutive runs of identical code,
    and one of them survived Layer 2 on a 2-1 vote. Reporting one run's total
    as "the" score would be reporting a coin flip.

    The honest headline is therefore the range's WORST case, not its best —
    which is also the number that survives a judge re-running the demo.

    `answerable`/`unanswerable`/`questions_file` are threaded straight
    through to `main` on every run — see `main`'s own docstring.
    """
    per_run, seeds_used = [], []
    for i in range(runs):
        seeds = _reseed(i, seed_base)
        seeds_used.append(seeds)
        print()
        print("#" * 70)
        print(f"# RUN {i + 1} of {runs}   seeds={seeds}")
        print("#" * 70)
        out = RESULTS_PATH.with_name(f"phase6_results{suffix}_run{i + 1}.json")
        per_run.append(main(
            relevance_filter=relevance_filter, results_path=out,
            answerable=answerable, unanswerable=unanswerable,
            questions_file=questions_file,
        ))

    metrics = ["citation_accuracy", "false_refusals", "correct_refusals", "false_answers"]
    aggregate = {m: _summarize([r[m] for r in per_run]) for m in metrics}
    n_answerable = per_run[0]["n_answerable"]
    n_unanswerable = per_run[0]["n_unanswerable"]

    # How many runs each answerable question passed — a question that passes
    # 3/3 and one that passes 1/3 are different facts, and a single-run total
    # hides the difference entirely.
    stability = {
        q: sum(r["per_question"].get(q, False) for r in per_run)
        for q in per_run[0]["per_question"]
    }

    print()
    print("=" * 78)
    print(f"AGGREGATE OVER {runs} RUNS  (report the worst case, not the best)")
    print("=" * 78)
    print(f"{'metric':<34} {'min':>5} {'median':>7} {'max':>5}   runs")
    for m in metrics:
        a = aggregate[m]
        denom = n_answerable if m in ("citation_accuracy", "false_refusals") else n_unanswerable
        print(f"{m + ' (/' + str(denom) + ')':<34} {a['min']:>5} {a['median']:>7} {a['max']:>5}   {a['runs']}")

    print()
    print("PER-QUESTION STABILITY (answerable — runs passed out of %d)" % runs)
    for q, passed in sorted(stability.items(), key=lambda kv: kv[1]):
        flag = "  <-- UNSTABLE" if 0 < passed < runs else ""
        print(f"  {passed}/{runs}  {q[:78]}{flag}")

    summary = {
        "runs": runs,
        "seed_base": seed_base,
        "seeds_used": seeds_used,
        "relevance_filter": relevance_filter,
        "questions_file": str(questions_file) if questions_file else None,
        "config": {
            "model": llm_client.active_model_name(),
            "provider": llm_client.LLM_PROVIDER,
            "ollama_num_ctx": getattr(llm_client, "OLLAMA_NUM_CTX", None),
            "verification_temperature": getattr(verification, "VERIFICATION_TEMPERATURE", None),
        },
        "aggregate": aggregate,
        "per_question_stability": stability,
        "avg_elapsed_per_run": [r["avg_elapsed"] for r in per_run],
    }
    summary_path = RESULTS_PATH.with_name(f"phase6_summary{suffix}.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Aggregate summary written to {summary_path}")
    return summary


def _parse_args(argv=None):
    """Extracted from `if __name__ == "__main__"` purely so tests can drive
    the CLI's argument parsing directly, without exec'ing the whole script.

    Off by default: matches generate.answer_query's own default (the filter
    was measured to hurt the false-refusal rate and is disabled in the
    shipped pipeline — see commit 4152250 / docs/decisions.md). Opt in with
    --relevance-filter. --no-relevance-filter is kept as a no-op alias so
    old commands (in docs, muscle memory) still run and still mean "off".
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--relevance-filter", action="store_true")
    parser.add_argument("--no-relevance-filter", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument(
        "--questions", type=Path, default=None,
        help="Load ANSWERABLE/UNANSWERABLE from this file (e.g. "
             "docs/heldout_questions.json) instead of this module's own "
             "dev-set lists. Results filenames get a suffix derived from "
             "the file's stem so dev-set results are never overwritten.",
    )
    return parser.parse_args(argv)


def _suffix_for(relevance_filter: bool) -> str:
    """Output-file suffix: the default (filter off) run stays unsuffixed
    (phase6_results.json etc., unchanged filenames from before this default
    flip); an opted-in filter run is marked so it's never mistaken for the
    shipped configuration."""
    return "_with_relevance_filter" if relevance_filter else ""


if __name__ == "__main__":
    args = _parse_args()

    relevance_filter = args.relevance_filter
    answerable, unanswerable = ANSWERABLE, UNANSWERABLE
    # Questions-file suffix comes first (it identifies which question set
    # produced these numbers at a glance) then the relevance-filter suffix —
    # with neither flag set, this is "", byte-identical to the pre-existing
    # default filenames.
    questions_suffix = ""
    if args.questions:
        answerable, unanswerable = _load_questions(args.questions)
        questions_suffix = f"_{args.questions.stem}"
    suffix = questions_suffix + _suffix_for(relevance_filter)
    if args.runs == 1:
        _reseed(0, args.seed_base)
        main(relevance_filter=relevance_filter,
             results_path=RESULTS_PATH.with_name(f"phase6_results{suffix}.json"),
             answerable=answerable, unanswerable=unanswerable,
             questions_file=args.questions)
    else:
        run_many(args.runs, args.seed_base, relevance_filter, suffix,
                  answerable=answerable, unanswerable=unanswerable,
                  questions_file=args.questions)
