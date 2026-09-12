from bm25_retrieval import BM25Index, tokenize


def test_tokenize_lowercases_and_splits_on_word_boundaries():
    assert tokenize("Traditional Knowledge, Section 3(p)!") == [
        "traditional",
        "knowledge",
        "section",
        "3",
        "p",
    ]


def test_retrieve_ranks_lexically_matching_chunk_first():
    chunks = [
        {"chunk_id": "a", "text": "The quick brown fox jumps over the lazy dog."},
        {"chunk_id": "b", "text": "Traditional knowledge cannot be patented under section 3(p)."},
        {"chunk_id": "c", "text": "Unrelated text about filing fees and forms."},
    ]
    index = BM25Index(chunks)
    hits = index.retrieve("traditional knowledge patent", top_k=3)
    assert hits[0]["chunk_id"] == "b"


def test_retrieve_respects_top_k():
    chunks = [{"chunk_id": str(i), "text": f"document number {i} about patents"} for i in range(10)]
    index = BM25Index(chunks)
    hits = index.retrieve("patents", top_k=3)
    assert len(hits) == 3
