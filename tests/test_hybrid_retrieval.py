from unittest.mock import patch

from hybrid_retrieval import reciprocal_rank_fusion, retrieve_hybrid


def test_items_in_both_ranked_lists_outrank_single_list_items():
    list_a = [{"chunk_id": "x"}, {"chunk_id": "y"}, {"chunk_id": "z"}]
    list_b = [{"chunk_id": "y"}, {"chunk_id": "w"}, {"chunk_id": "x"}]

    result = reciprocal_rank_fusion(list_a, list_b, top_k=4)
    top_two = {result[0]["chunk_id"], result[1]["chunk_id"]}
    assert top_two == {"x", "y"}


def test_respects_top_k():
    list_a = [{"chunk_id": str(i)} for i in range(10)]
    result = reciprocal_rank_fusion(list_a, top_k=3)
    assert len(result) == 3


def test_single_list_preserves_its_own_order():
    list_a = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    result = reciprocal_rank_fusion(list_a, top_k=3)
    assert [r["chunk_id"] for r in result] == ["a", "b", "c"]


# --- W6: candidate_k must actually reach as deep as top_k -----------------
#
# Bug this guards against: generate.py called
# retrieve_hybrid(query, top_k=CANDIDATE_K) without passing candidate_k, so
# RRF only ever fused the top 20 (candidate_k's old default) from each
# retriever while top_k asked for 40 — anything ranked 21-40 by either
# retriever never entered fusion at all, even though it was "in range" by
# every other measure. See docs/decisions.md's rank-29 statutory-clause
# entry for the same shape of bug at the vector-only layer.


def test_retrieve_hybrid_considers_all_candidates_down_to_candidate_k():
    # "shared" sits at rank 25 in the vector list (squarely in the 21-40
    # range the old unpassed-candidate_k bug would never have fetched at
    # all, since retrieve_vector would only have been asked for its default
    # top 20) but at rank 0 in the bm25 list. The stub retrievers honor
    # top_k like the real ones do (slicing to it), so this only surfaces
    # "shared" to RRF at all if retrieve_hybrid actually asked for 40 deep.
    vector_ids = [f"v{i}" for i in range(25)] + ["shared"] + [f"v{i}" for i in range(25, 39)]
    bm25_ids = ["shared"] + [f"b{i}" for i in range(39)]

    def _stub(all_ids):
        def _retrieve(query, top_k):
            return [{"chunk_id": cid} for cid in all_ids[:top_k]]
        return _retrieve

    with patch("hybrid_retrieval.retrieve_vector", side_effect=_stub(vector_ids)) as mock_vector, \
         patch("hybrid_retrieval.retrieve_bm25", side_effect=_stub(bm25_ids)) as mock_bm25:
        result = retrieve_hybrid("query", top_k=5, candidate_k=40)

    # Both retrievers must actually have been asked for all 40 (not the old
    # default of 20).
    mock_vector.assert_called_once_with("query", top_k=40)
    mock_bm25.assert_called_once_with("query", top_k=40)
    # "shared" is ranked in both lists, so RRF gives it the highest combined
    # score of anything in the pool — it should come out on top, but only
    # because candidate_k=40 let retrieve_vector actually reach rank 25.
    assert result[0]["chunk_id"] == "shared"


def test_retrieve_hybrid_clamps_candidate_k_up_to_top_k():
    # candidate_k < top_k would ask RRF to return more results than it was
    # ever given to fuse from — retrieve_hybrid must widen candidate_k
    # itself rather than silently truncating results below top_k.
    vector_hits = [{"chunk_id": f"v{i}"} for i in range(5)]
    bm25_hits = [{"chunk_id": f"b{i}"} for i in range(5)]

    with patch("hybrid_retrieval.retrieve_vector", return_value=vector_hits) as mock_vector, \
         patch("hybrid_retrieval.retrieve_bm25", return_value=bm25_hits) as mock_bm25:
        retrieve_hybrid("query", top_k=40, candidate_k=5)

    mock_vector.assert_called_once_with("query", top_k=40)
    mock_bm25.assert_called_once_with("query", top_k=40)
