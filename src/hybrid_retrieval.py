"""Hybrid retrieval: fuse vector (ChromaDB) and BM25 keyword rankings via Reciprocal Rank Fusion.

RRF instead of a weighted score blend, because vector cosine-distance and BM25
term-frequency scores live on incomparable scales with no natural common zero
point — RRF only needs each retriever's *rank order*, not its raw scores, so
there's no manual score-normalization/weight-tuning step to get wrong.
"""
from bm25_retrieval import retrieve_bm25
from retrieval import retrieve as retrieve_vector

RRF_K = 60


def reciprocal_rank_fusion(
    *ranked_lists: list[dict], k: int = RRF_K, top_k: int = 5
) -> list[dict]:
    """Each ranked_lists arg is a list of hit dicts (must have 'chunk_id'), best-first."""
    scores: dict[str, float] = {}
    chunk_by_id: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked):
            cid = hit["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            chunk_by_id.setdefault(cid, hit)

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [{**chunk_by_id[cid], "rrf_score": score} for cid, score in ordered]


def retrieve_hybrid(query: str, top_k: int = 5, candidate_k: int = 20) -> list[dict]:
    vector_hits = retrieve_vector(query, top_k=candidate_k)
    bm25_hits = retrieve_bm25(query, top_k=candidate_k)
    return reciprocal_rank_fusion(vector_hits, bm25_hits, top_k=top_k)
