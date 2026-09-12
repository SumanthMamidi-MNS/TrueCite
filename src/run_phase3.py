"""Phase 3 gate: compare vector-only vs hybrid (RRF) retrieval on 15 test questions.

PRD gate: "hybrid must genuinely outperform, not just add complexity."

Metric: for each query, does the expected doc_id appear in the top-5 results,
and at what rank? Doc-level (not exact-chunk-level) because several queries
have legitimate multi-chunk support within the expected document — doc-level
hit is the meaningful signal for "did retrieval find the right document."

Run: .venv/Scripts/python.exe src/run_phase3.py
"""
from hybrid_retrieval import retrieve_hybrid
from retrieval import retrieve as retrieve_vector

# (query, expected_doc_id) — grounded in documents actually read during
# Phase 1/2, not invented. Doc-level ground truth, not exact chunk_id, since
# several queries have legitimate multi-chunk support within one document.
TEST_QUERIES = [
    ("Can traditional knowledge be patented in India?", "ipo_tk_biological_material_guidelines_2012"),
    ("What happens if a patent application does not disclose the source of biological material?", "ipo_tk_biological_material_guidelines_2012"),
    ("What is the Traditional Knowledge Digital Library used for?", "wipo_documenting_tk_toolkit"),
    ("What are the requirements for filing a patent application for an Ayush-related invention?", "ipo_ayush_examination_guidelines_2025"),
    ("How many patents have been granted to Indian entities for Ayurvedic medicine?", "pib_faq_patents_traditional_ayurvedic_medicine_2013"),
    ("What must a patent applicant do if their invention uses biological material sourced from India?", "ipo_tk_biological_material_guidelines_2012"),
    ("What systems of medicine does AYUSH cover?", "ipo_ayush_examination_guidelines_2025"),
    ("Is a mere discovery of a new property of a known substance patentable in India?", "patents_act_1970"),
    ("What are the three phases the WIPO toolkit divides TK documentation into?", "wipo_documenting_tk_toolkit"),
    ("Under what section of the Biological Diversity Act must approval be sought before filing a patent based on Indian biological resources?", "ipo_tk_biological_material_guidelines_2012"),
    ("What is the penalty for contravening the Biological Diversity Act's access provisions?", "ipo_tk_biological_material_guidelines_2012"),
    ("How does India's protection of traditional knowledge interact with TRIPS obligations?", "pib_faq_patents_traditional_ayurvedic_medicine_2013"),
    ("What database do patent examiners use to check prior art in traditional Indian medicine?", "ipo_tk_biological_material_guidelines_2012"),
    ("What guiding principles apply to assessing novelty in Ayush-related inventions?", "ipo_ayush_examination_guidelines_2025"),
    ("What license does the WIPO toolkit use?", "wipo_documenting_tk_toolkit"),
]

TOP_K = 5


def _rank_of_expected(hits: list[dict], expected_doc_id: str) -> int | None:
    for i, h in enumerate(hits, 1):
        if h["metadata"]["doc_id"] == expected_doc_id:
            return i
    return None


def main():
    vector_hits_count = 0
    hybrid_hits_count = 0
    rows = []

    for query, expected_doc_id in TEST_QUERIES:
        vector_results = retrieve_vector(query, top_k=TOP_K)
        hybrid_results = retrieve_hybrid(query, top_k=TOP_K)

        v_rank = _rank_of_expected(vector_results, expected_doc_id)
        h_rank = _rank_of_expected(hybrid_results, expected_doc_id)

        if v_rank:
            vector_hits_count += 1
        if h_rank:
            hybrid_hits_count += 1

        rows.append((query, expected_doc_id, v_rank, h_rank))

    print(f"{'query':<70} {'expected doc':<45} {'vec rank':<9} {'hyb rank':<9}")
    print("-" * 135)
    for query, expected_doc_id, v_rank, h_rank in rows:
        q_short = (query[:67] + "...") if len(query) > 70 else query
        d_short = (expected_doc_id[:42] + "...") if len(expected_doc_id) > 45 else expected_doc_id
        print(f"{q_short:<70} {d_short:<45} {str(v_rank):<9} {str(h_rank):<9}")

    n = len(TEST_QUERIES)
    # hit@5 is a coarse, doc-level metric that saturates at 15/15 for both
    # methods on a corpus this small/well-separated — it doesn't distinguish
    # "found it at rank 1" from "found it at rank 5". Average rank (treating a
    # miss as one worse than TOP_K, so misses are penalized rather than
    # ignored) is the metric that actually shows whether hybrid helps.
    def avg_rank(ranks: list[int | None]) -> float:
        return sum((r if r else TOP_K + 1) for r in ranks) / len(ranks)

    vector_ranks = [r[2] for r in rows]
    hybrid_ranks = [r[3] for r in rows]

    print()
    print(f"vector-only: {vector_hits_count}/{n} hit@{TOP_K}, avg rank {avg_rank(vector_ranks):.2f}")
    print(f"hybrid:      {hybrid_hits_count}/{n} hit@{TOP_K}, avg rank {avg_rank(hybrid_ranks):.2f}")


if __name__ == "__main__":
    main()
