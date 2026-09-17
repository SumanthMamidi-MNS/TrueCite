"""Layer 2 precision battery — a permanent, re-runnable instrument for
verify_claim (src/verification.py), built after directly observing it reject
TRUE claims: all 3 votes rejected "contravening section 6 ... imprisonment
... five years" against biological_diversity_act_2002::sec-55 (which says
exactly that), reasoning that the passage "does not specify that this applies
exclusively to section 6" — a requirement the claim never made. Same pattern,
10/10, on a PIB patent-count statistic rejected for not repeating the
passage's exact date wording. See docs/decisions.md for the full account.

Every case below was checked against the real chunk text in
corpus/processed/*.json before being trusted here (T1-F9's expected labels
are not asserted, they were read).

This script exists so a prompt change to VERIFICATION_PROMPT_TEMPLATE is
accepted or rejected against real numbers, not a feeling — and so the same
battery can be re-run again later if the prompt or model ever changes again.

Run:
  .venv/Scripts/python.exe src/run_verification_eval.py --prompt current
  .venv/Scripts/python.exe src/run_verification_eval.py --prompt precise
  .venv/Scripts/python.exe src/run_verification_eval.py --prompt precise --json-out corpus/eval_results/verification_battery_precise.json
"""
import argparse
import json
from pathlib import Path

import verification

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus" / "processed"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "corpus" / "eval_results"

# Three distinct seed bases (not just the one verification.py ships with) so
# a prompt's apparent pass/fail isn't an artifact of one lucky/unlucky set of
# 3 seeds — the same reasoning that motivated majority-vote verification in
# the first place (see verification.py's VERIFICATION_TEMPERATURE comment).
SEED_BASES = [(101, 202, 303), (1101, 1202, 1303), (2101, 2202, 2303)]

# (label, expected supported?, claim, chunk_id). F1-F9 are adversarial on
# purpose: each changes exactly one fact (a figure, a section number, an
# entity, a date, or adds a claim the passage doesn't make) so a prompt that
# passes these can't be accused of just accepting everything.
CASES = [
    ("T1", True, "An invention which, in effect, is traditional knowledge is not an invention under the Patents Act, 1970.", "patents_act_1970::sec-3-clause-p"),
    ("T2", True, "Contravening section 6 of the Biological Diversity Act is punishable with imprisonment which may extend to five years.", "biological_diversity_act_2002::sec-55"),
    ("T3", True, "As of March 2013, 93 patents had been granted to Indian entities for Ayurvedic-medicine-related inventions.", "pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2"),
    ("T4", True, "A person must obtain the approval of the National Biodiversity Authority before applying for a patent on an invention based on a biological resource obtained from India.", "biological_diversity_act_2002::sec-6"),
    ("T5", True, "The mere discovery of a new use for a known substance is not an invention under the Patents Act, 1970.", "patents_act_1970::sec-3-clause-d"),
    ("T6", True, "Contravening section 7 of the Biological Diversity Act can be punished with a fine which may extend to five lakh rupees.", "biological_diversity_act_2002::sec-55"),
    ("F1", False, "Contravening section 6 of the Biological Diversity Act is punishable with imprisonment which may extend to ten years.", "biological_diversity_act_2002::sec-55"),
    ("F2", False, "Contravening section 7 of the Biological Diversity Act is punishable with imprisonment which may extend to five years.", "biological_diversity_act_2002::sec-55"),
    ("F3", False, "Section 6 is the only provision of the Biological Diversity Act whose contravention is punishable with imprisonment.", "biological_diversity_act_2002::sec-55"),
    ("F4", False, "As of March 2013, 93 patents had been granted to foreign entities for Ayurvedic-medicine-related inventions.", "pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2"),
    ("F5", False, "The Biological Diversity Act sets a patent filing fee of five thousand rupees.", "biological_diversity_act_2002::sec-55"),
    ("F6", False, "An invention which, in effect, is traditional knowledge can be patented in India.", "patents_act_1970::sec-3-clause-p"),
    ("F7", False, "AYUSH covers Ayurveda, Siddha, Unani, Sowa-Rigpa, Homeopathy, and Yoga & Naturopathy.", "patents_act_1970::sec-3-clause-p"),
    ("F8", False, "As of March 2015, 93 patents had been granted to Indian entities for Ayurvedic-medicine-related inventions.", "pib_faq_patents_traditional_ayurvedic_medicine_2013::para-2"),
    ("F9", False, "Approval from the National Biodiversity Authority is never required before applying for a patent.", "biological_diversity_act_2002::sec-6"),
    # 2026-09-16, second amendment: added alongside the precise prompt's
    # spelling-variant carve-out (see verification.py). T7 is the motivating
    # true case — the passage spells it "Homoeopathy", the claim spells it
    # "Homeopathy", same fact. F10 is the adversarial pair against the SAME
    # chunk: a genuinely different, unsupported system (Chiropractic) swapped
    # in, which must still be rejected — proof the spelling carve-out didn't
    # also loosen entity-substitution detection.
    ("T7", True, "AYUSH covers Ayurveda, Siddha, Unani, Sowa-Rigpa, Homeopathy, and Yoga & Naturopathy.", "ipo_ayush_examination_guidelines_2025::preamble"),
    ("F10", False, "AYUSH covers Ayurveda, Siddha, Unani, Sowa-Rigpa, Chiropractic, and Yoga & Naturopathy.", "ipo_ayush_examination_guidelines_2025::preamble"),
]

_PASSAGE_CACHE: dict[str, str] = {}


def _load_passage(chunk_id: str) -> str:
    """Loads a chunk's stored text by chunk_id from corpus/processed/<doc_id>.json
    — the same processed corpus retrieval reads from, not a re-transcription,
    so a case can never silently drift from what the pipeline actually sees."""
    if chunk_id in _PASSAGE_CACHE:
        return _PASSAGE_CACHE[chunk_id]
    doc_id = chunk_id.split("::")[0]
    with open(CORPUS_DIR / f"{doc_id}.json", encoding="utf-8") as f:
        chunks = json.load(f)
    for c in chunks:
        if c["chunk_id"] == chunk_id:
            _PASSAGE_CACHE[chunk_id] = c["text"]
            return c["text"]
    raise KeyError(f"chunk_id not found in {doc_id}.json: {chunk_id}")


def run_battery(prompt: str) -> dict:
    """Runs every case in CASES through the real verify_claim, at all three
    SEED_BASES, using the named prompt ("current" = the pre-2026-09-16
    original, "precise" = the exclusivity/wording fix).

    Redirects verify_claim by temporarily reassigning verification's module
    globals (VERIFICATION_SEEDS, VERIFICATION_PROMPT_TEMPLATE) — both are
    read as globals inside _verify_claim_once/verify_claim at call time (not
    bound at import time), so this is enough to control seeding and prompt
    selection without changing verify_claim's signature. Always restores both
    afterward, even on error, so running this is safe from within another
    process (e.g. a test suite) that imports verification itself.
    """
    original_seeds = verification.VERIFICATION_SEEDS
    original_template = verification.VERIFICATION_PROMPT_TEMPLATE
    verification.VERIFICATION_PROMPT_TEMPLATE = (
        verification.VERIFICATION_PROMPT_TEMPLATE_PRECISE
        if prompt == "precise"
        else verification.VERIFICATION_PROMPT_TEMPLATE_ORIGINAL
    )
    try:
        per_seed_base = []
        for seeds in SEED_BASES:
            verification.VERIFICATION_SEEDS = seeds
            verdicts = {}
            for label, _expected, claim, chunk_id in CASES:
                passage = _load_passage(chunk_id)
                result = verification.verify_claim(claim, passage)
                verdicts[label] = result["supported"]
            per_seed_base.append({"seeds": list(seeds), "verdicts": verdicts})
    finally:
        verification.VERIFICATION_SEEDS = original_seeds
        verification.VERIFICATION_PROMPT_TEMPLATE = original_template

    true_labels = [label for label, expected, *_ in CASES if expected]
    false_labels = [label for label, expected, *_ in CASES if not expected]

    true_accepts = sum(
        1 for base in per_seed_base for label in true_labels if base["verdicts"][label]
    )
    false_accepts = sum(
        1 for base in per_seed_base for label in false_labels if base["verdicts"][label]
    )
    # Which false cases were ever accepted, and at which seed bases — this is
    # what Step 4's HARD REJECT criterion actually inspects, not just the
    # false_accepts count, since even one occurrence is disqualifying.
    false_accept_detail = [
        {"label": label, "seeds": base["seeds"]}
        for base in per_seed_base
        for label in false_labels
        if base["verdicts"][label]
    ]

    return {
        "prompt": prompt,
        "seed_bases": [list(s) for s in SEED_BASES],
        "per_seed_base": per_seed_base,
        "true_accepts": true_accepts,
        "true_total": len(true_labels) * len(SEED_BASES),
        "false_accepts": false_accepts,
        "false_total": len(false_labels) * len(SEED_BASES),
        "false_accept_cases": sorted({d["label"] for d in false_accept_detail}),
        "false_accept_detail": false_accept_detail,
    }


def decide(baseline: dict, candidate: dict) -> dict:
    """Applies the PRE-COMMITTED accept/reject rule for the candidate prompt,
    given the baseline's and candidate's run_battery() summaries. Coded once
    here rather than eyeballed from printed tables each run, so the same rule
    applies identically whether this is run once or re-run later:

      - HARD REJECT if the candidate lets ANY false case through as majority
        supported, at ANY seed base. One is enough.
      - Otherwise ACCEPT only if candidate true_accepts is STRICTLY greater
        than baseline true_accepts.
    """
    hard_reject = candidate["false_accepts"] > 0
    improved = candidate["true_accepts"] > baseline["true_accepts"]
    return {
        "accept": (not hard_reject) and improved,
        "hard_reject": hard_reject,
        "improved_true_accepts": improved,
        "baseline_true_accepts": baseline["true_accepts"],
        "candidate_true_accepts": candidate["true_accepts"],
        "candidate_false_accepts": candidate["false_accepts"],
        "candidate_false_accept_cases": candidate["false_accept_cases"],
    }


def _print_summary(summary: dict) -> None:
    print(f"Prompt: {summary['prompt']}")
    for base in summary["per_seed_base"]:
        line = " ".join(
            f"{label}={'S' if v else 'X'}" for label, v in base["verdicts"].items()
        )
        print(f"  seeds={tuple(base['seeds'])}: {line}")
    print(f"true-accepts: {summary['true_accepts']}/{summary['true_total']}")
    tail = f"  ({', '.join(summary['false_accept_cases'])})" if summary["false_accept_cases"] else ""
    print(f"false-accepts: {summary['false_accepts']}/{summary['false_total']}{tail}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", choices=["current", "precise"], default="current")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    summary = run_battery(args.prompt)
    _print_summary(summary)

    out_path = Path(args.json_out) if args.json_out else RESULTS_DIR / f"verification_battery_{args.prompt}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
