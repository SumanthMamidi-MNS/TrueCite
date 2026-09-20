"""Phase 18: end-to-end evaluation across the regimes added in Phase 10.

Measures the FULL pipeline, not retrieval alone — the Phase 10 gate already
established that the right statute is reachable, so what is unknown is whether
the pipeline then answers from it, cites it correctly, or refuses.

Records four things per question:
  answered / refused      did it produce an answer at all
  cited_expected          is the expected document among the citations
  confidence              the advisory's own label
  escalated               did it offer a human

An out-of-corpus control question is included deliberately: a suite where
everything is answerable cannot detect a system that has stopped refusing.

Run: .venv/Scripts/python.exe src/run_phase18.py
"""
import json
import sys
import time
from pathlib import Path

from generate import answer_query_streaming

OUT = Path(__file__).resolve().parent.parent / "corpus" / "eval_results"

# (regime, question, expected_doc_id or None for a question that SHOULD refuse)
CASES = [
    ("patent", "Can an invention that is essentially traditional knowledge be patented in India?",
     "patents_act_1970"),
    ("trademark", "What marks are refused registration as trade marks in India?",
     "trade_marks_act_1999"),
    ("gi", "Who may apply to register a geographical indication for goods in India?",
     "geographical_indications_act_1999"),
    ("design", "Which designs are prohibited from registration under the Designs Act?",
     "designs_act_2000"),
    ("copyright", "What is the term of copyright in a literary work in India?",
     "copyright_act_1957"),
    ("plant-variety", "Who may apply for registration of a new plant variety in India?",
     "plant_varieties_act_2001"),
    ("abs", "What approval is needed before accessing Indian biological resources for research?",
     "biological_diversity_act_2002"),
    ("abs-rules", "What is the procedure for seeking approval to access biological resources?",
     "biological_diversity_rules_2024"),
    ("food", "What is Ayurveda Aahara under the FSSAI regulations?",
     "fssai_ayurveda_aahara_regulations_2022"),
    ("intl-trips", "What does TRIPS require of members regarding patentable subject matter?",
     "trips_agreement"),
    ("intl-cbd", "What are the objectives of the Convention on Biological Diversity?",
     "cbd_convention"),
    ("intl-nagoya", "What does the Nagoya Protocol require for access to genetic resources?",
     "nagoya_protocol"),
    # Controls: must refuse. A suite where everything is answerable cannot
    # detect a system that has stopped refusing.
    ("control-out-of-scope", "What is the capital city of France?", None),
    ("control-unsourced", "What are the exact fees for a trade mark opposition in rupees?", None),
]


def run_one(regime: str, question: str, expected: str | None) -> dict:
    t0 = time.time()
    refused, refusal_stage, answer, citations, advisory = False, None, "", [], None
    try:
        for ev in answer_query_streaming(question):
            if ev["type"] == "refused":
                refused, refusal_stage = True, ev.get("refusal_stage")
            elif ev["type"] == "advisory":
                advisory = ev
            elif ev["type"] == "complete":
                answer = ev["result"].get("answer", "")
                citations = ev["result"].get("citations", []) or []
            elif ev["type"] == "provider_unavailable":
                return {"regime": regime, "question": question, "error": ev["message"]}
    except Exception as exc:
        return {"regime": regime, "question": question,
                "error": f"{type(exc).__name__}: {exc}"}

    cited_expected = bool(expected) and any(
        expected.replace("_", " ").split()[0].lower() in c.lower() for c in citations
    )
    should_refuse = expected is None
    return {
        "regime": regime,
        "question": question,
        "expected": expected,
        "refused": refused,
        "refusal_stage": refusal_stage,
        "correct_refusal": should_refuse and refused,
        "false_answer": should_refuse and not refused,
        "cited_expected": cited_expected,
        "citations": citations,
        "answer": answer[:300],
        "confidence": (advisory or {}).get("confidence"),
        "escalated": (advisory or {}).get("escalate"),
        "seconds": round(time.time() - t0, 1),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for regime, q, expected in CASES:
        r = run_one(regime, q, expected)
        results.append(r)
        flag = ("ERROR" if r.get("error")
                else "REFUSED" if r["refused"] else "answered")
        extra = "" if r.get("error") else f" cited_expected={r['cited_expected']} conf={r['confidence']}"
        print(f"{regime:22} {flag:9}{extra} ({r.get('seconds','-')}s)", flush=True)

    answerable = [r for r in results if r.get("expected") and not r.get("error")]
    controls = [r for r in results if r.get("expected") is None and not r.get("error")]
    summary = {
        "answerable": len(answerable),
        "answered": sum(1 for r in answerable if not r["refused"]),
        "cited_expected": sum(1 for r in answerable if r["cited_expected"]),
        "controls": len(controls),
        "correct_refusals": sum(1 for r in controls if r["correct_refusal"]),
        "false_answers": sum(1 for r in controls if r["false_answer"]),
        "errors": sum(1 for r in results if r.get("error")),
    }
    print("\n" + json.dumps(summary, indent=2))
    (OUT / "phase18_results.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nwritten to {OUT / 'phase18_results.json'}")


if __name__ == "__main__":
    sys.exit(main())
