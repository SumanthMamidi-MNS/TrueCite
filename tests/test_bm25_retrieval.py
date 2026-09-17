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


def test_penalty_and_penalties_share_a_stem():
    # The measured defect (docs/decisions.md, 2026-09-16): "penalty" and
    # "Penalties" never matched under the old bare-split tokenizer.
    assert tokenize("Penalties") == tokenize("penalty")


def test_contravenes_contravening_contravention_share_a_stem():
    stems = {tokenize("contravenes")[0], tokenize("contravening")[0], tokenize("contravention")[0]}
    assert len(stems) == 1


def test_stopwords_are_dropped_but_negation_and_modality_survive():
    tokens = tokenize("What is the penalty for this, it is not without effect?")
    for stopword in ("what", "is", "the", "for", "this", "it"):
        assert stopword not in tokens
    # Negation/modality changes legal meaning and must never be filtered out.
    assert "not" in tokens
    assert "without" in tokens


def test_devanagari_token_passes_through_unstemmed():
    # The stemmer's suffix rules are English-specific; a non-ASCII token must
    # come back exactly as split, not mangled by an English suffix rule. Uses a
    # word of plain base consonants (no dependent vowel signs) because \w+'s
    # existing Unicode behavior already splits at combining marks — a
    # pre-existing _TOKEN_RE characteristic this task isn't asked to fix, so the
    # test isolates the one thing it does check: the stemmer leaves it alone.
    assert tokenize("मन") == ["मन"]


def test_short_words_are_not_truncated_below_four_characters():
    # A stripped suffix must never leave a stem shorter than 4 characters, so
    # short legal words aren't mangled into something unrecognizable.
    assert tokenize("act") == ["act"]
    assert tokenize("use") == ["use"]
    assert tokenize("acts") == ["acts"]
