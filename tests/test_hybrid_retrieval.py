from hybrid_retrieval import reciprocal_rank_fusion


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
