"""Hybrid retrieval: fuse vector (ChromaDB) and BM25 keyword rankings via Reciprocal Rank Fusion.

RRF instead of a weighted score blend, because vector cosine-distance and BM25
term-frequency scores live on incomparable scales with no natural common zero
point — RRF only needs each retriever's *rank order*, not its raw scores, so
there's no manual score-normalization/weight-tuning step to get wrong.
"""
from authority import get_authority
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


def _in_jurisdiction(hit: dict, jurisdiction: str | None) -> bool:
    """Whether a hit belongs to the requested jurisdiction.

    Resolved from authority.py per doc_id rather than from vector-store
    metadata on purpose: jurisdiction is editorial metadata about a document,
    not a property of its embedding, and storing it in the index would mean a
    full re-embed every time one is corrected.

    A doc_id with no authority entry is EXCLUDED when a jurisdiction is
    requested. Failing closed matters here -- the problem statement asks for
    the two answer-sets to be "never conflated", so an unclassifiable document
    must not silently land in a jurisdiction-scoped answer.
    """
    if jurisdiction is None:
        return True
    try:
        return get_authority(hit["metadata"]["doc_id"])["jurisdiction"] == jurisdiction
    except (KeyError, TypeError):
        return False


def retrieve_hybrid(
    query: str, top_k: int = 5, candidate_k: int = 20, jurisdiction: str | None = None
) -> list[dict]:
    # candidate_k must be at least top_k, or RRF would be asked to return
    # more results than it was ever given to fuse from. Clamped up rather
    # than raised: a caller asking for top_k=40 candidate_k=20 clearly wants
    # 40 results back, and silently narrowing that to "whatever candidate_k
    # allows" is exactly the bug docs/decisions.md already records once
    # (generate.py calling retrieve_hybrid(query, top_k=CANDIDATE_K) without
    # passing candidate_k at all, so RRF only fused the top 20 from each
    # retriever while the vector-only list it was meant to match was 40
    # deep — a correctly-worded, rank-29 statutory clause was outside the
    # narrower window and never entered fusion). Clamping here makes that
    # mismatch impossible to reintroduce silently, regardless of what any
    # call site remembers to pass.
    candidate_k = max(candidate_k, top_k)
    # Over-fetch before filtering, then filter each retriever's ranking before
    # fusion. Filtering after fusion would silently return fewer than top_k
    # results for a jurisdiction-scoped query, because the pool would already
    # have been narrowed to top_k by documents from both jurisdictions.
    fetch_k = candidate_k * 3 if jurisdiction else candidate_k
    vector_hits = [h for h in retrieve_vector(query, top_k=fetch_k)
                   if _in_jurisdiction(h, jurisdiction)][:candidate_k]
    bm25_hits = [h for h in retrieve_bm25(query, top_k=fetch_k)
                 if _in_jurisdiction(h, jurisdiction)][:candidate_k]
    return reciprocal_rank_fusion(vector_hits, bm25_hits, top_k=top_k)
