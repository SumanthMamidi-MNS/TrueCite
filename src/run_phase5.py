"""Phase 5 gate: end-to-end pipeline (retrieval -> Layer 1 -> generation -> Layer 2 -> citations).

Not part of the automated pytest suite — makes live local-LLM calls (slow,
and non-deterministic by nature for the generation step), so this is a
manual gate script in the same spirit as run_phase2.py/run_phase3.py.

Run: .venv/Scripts/python.exe src/run_phase5.py
"""
from generate import answer_query

TEST_CASES = [
    (
        "How many patents have been granted to Indian entities for Ayurvedic medicine?",
        "answerable — exact statistic in PIB press release",
    ),
    (
        "Explain the rules of cricket.",
        "genuinely unanswerable — Layer 1 should refuse before any LLM call",
    ),
    (
        "What is the current government filing fee for a patent application in India?",
        "topically relevant but not specific — corpus only says fees are 'as prescribed', "
        "no figures. Section 3(p)'s well-known false-refusal risk in reverse: this must "
        "refuse or omit the fabricated figure, not confidently state a wrong one.",
    ),
]


def main():
    for query, note in TEST_CASES:
        print("=" * 70)
        print(f"QUERY: {query}")
        print(f"note:  {note}")
        print("-" * 70)
        result = answer_query(query)
        if result["refused"]:
            print("REFUSED (correctly, if this was the unanswerable/fee case)")
        else:
            print(f"ANSWER: {result['answer']}")
        print()


if __name__ == "__main__":
    main()
