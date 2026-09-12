"""Phase 2 gate: build the index, run 5 hand-checked test queries, print results for review.

Run: .venv/Scripts/python.exe src/run_phase2.py
"""
from indexing import build_index
from retrieval import retrieve

# 5 hand-picked queries spanning all 5 corpus documents, per PRD's Phase 2 gate
# ("retrieval returns sensible chunks for 5 hand-checked queries").
TEST_QUERIES = [
    ("Can traditional knowledge be patented in India?", "patents_act_1970 sec-3 and/or TK guidelines"),
    (
        "What happens if a patent application does not disclose the source of biological material?",
        "patents_act_1970 (opposition/revocation grounds) and/or TK guidelines",
    ),
    ("What is the Traditional Knowledge Digital Library used for?", "wipo toolkit and/or TK guidelines"),
    (
        "What are the requirements for filing a patent application for an Ayush-related invention?",
        "ipo_ayush_examination_guidelines_2025",
    ),
    (
        "How many patents have been granted to Indian entities for Ayurvedic medicine?",
        "pib_faq (has specific stats)",
    ),
]


def main():
    print("Building index...")
    collection = build_index()
    print(f"Indexed {collection.count()} chunks.\n")

    for query, expected in TEST_QUERIES:
        print("=" * 70)
        print(f"QUERY: {query}")
        print(f"expected source: {expected}")
        print("-" * 70)
        hits = retrieve(query, top_k=5)
        for h in hits:
            preview = h["text"][:150].replace("\n", " ").encode("ascii", errors="replace").decode("ascii")
            print(f"  [{h['distance']:.4f}] {h['chunk_id']}")
            print(f"      {preview}...")
        print()


if __name__ == "__main__":
    main()
