"""BM25 keyword retrieval over the corpus chunks — the keyword half of Phase 3's hybrid search.

Independent of the embedding model/ChromaDB: BM25 is pure lexical (term-frequency)
matching, built directly from corpus/processed/*.json, no vectors involved.
"""
import re

from rank_bm25 import BM25Okapi

from enrichment import build_headings_by_section, build_retrieval_text
from indexing import load_all_chunks

# \w in Python's re is Unicode-aware by default, so this tokenizes Hindi text
# reasonably too (PRD §6.3 requires English + Hindi at minimum) — not verified
# against real Hindi content yet since the corpus is English-only so far.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Measured defect (docs/decisions.md, 2026-09-16): a bare \w+/lowercase split has
# no stopword removal and no stemming, so on
# "What is the penalty under the Biological Diversity Act, 2002 for contravening
# its access provisions?" 11 of 15 tokens are stopwords or the Act's own name —
# BM25's #1 hit was the Act's table-of-contents chunk, not any real section — and
# "penalty"/"Penalties" and "contravening"/"contravenes"/"contravention" never
# matched each other, so the gold chunk (sec-55, "Penalties") stayed outside the
# top 40 while sec-56 ("Penalty for contravention...", the literal string match)
# won on vocabulary alone. Both fixes below are directed at that evidence, not
# generic stemming for its own sake.
#
# Deliberately excluded from the stopword list: "not", "no", "without", "only",
# "shall", "may" — these change legal meaning (negation/modality) and dropping
# them would make BM25 blind to the difference between "may" and "may not".
_STOPWORDS = frozenset({
    "a", "an", "the",
    "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "have", "has", "had", "will", "would",
    "of", "to", "in", "on", "at", "for", "by", "with", "from", "as",
    "what", "which", "who", "how", "when", "where", "why",
    "it", "its", "this", "that",
})

# Longest-suffix-first stemmer, no NLTK dependency. Each entry is
# (suffix, replacement); a suffix is stripped only if what remains (after
# applying the replacement) is at least 4 characters, so short words like
# "act"/"use"/"acts" are never truncated into something unrecognizable.
#
# Two entries are narrow, evidence-driven additions beyond the base suffix list
# the task specified (ization/isation/ations/ation/ements/ement/ings/ing/ives/
# ive/ies/ied/es/ed/ly/s), both needed to actually collapse the two pairs above
# into shared stems rather than just "have a stemmer":
#   - "ies" -> "y" (not "ies" -> "") so "penalties" stems to "penalty", matching
#     "penalty" itself (which has no suffix to strip at all). A plain strip would
#     give "penalt", which never matches unstemmed "penalty".
#   - "tion" (in addition to the given "ation") so "contravention" stems to
#     "contraven", matching "contravenes" (strip "es") and "contravening" (strip
#     "ing"), both of which already land on "contraven". "ation" alone doesn't
#     fire here because "contravention" has "n", not "a", before "tion".
# Order matters: longer suffixes are tried first so "ation" (5 chars) still wins
# over the new "tion" (4 chars) for words that do have the "a", e.g.
# "duplication" -> "duplic", not the less-specific "duplica".
_SUFFIXES: list[tuple[str, str]] = sorted(
    [
        ("ization", ""), ("isation", ""),
        ("ations", ""), ("ements", ""),
        ("ation", ""), ("ement", ""),
        ("tion", ""), ("ings", ""), ("ives", ""),
        ("ing", ""), ("ive", ""), ("ies", "y"), ("ied", ""),
        ("es", ""), ("ed", ""), ("ly", ""),
        ("s", ""),
    ],
    key=lambda pair: -len(pair[0]),
)

_MIN_STEM_LEN = 4


def _stem(token: str) -> str:
    """Strip the longest matching suffix, ASCII tokens only (see `tokenize`)."""
    for suffix, replacement in _SUFFIXES:
        if token.endswith(suffix):
            stem = token[: -len(suffix)] + replacement
            if len(stem) >= _MIN_STEM_LEN:
                return stem
    return token


def tokenize(text: str) -> list[str]:
    """Lowercase, split on word boundaries, drop stopwords, stem ASCII tokens.

    Devanagari (or any non-ASCII) token is returned exactly as split — the
    stemmer's suffix rules are English-specific and would corrupt it, so it
    passes through unchanged, keeping this function's Unicode-handling claim
    (see the module-level comment on `_TOKEN_RE`) true for Hindi text.
    """
    tokens = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS:
            continue
        tokens.append(_stem(tok) if tok.isascii() else tok)
    return tokens


class BM25Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks

        # Same THE SAFETY PROPERTY as indexing.py: tokenize the enriched
        # (cross-reference-trailer) text for SCORING only. `retrieve` below
        # still returns `self.chunks[i]["text"]` — the true chunk text — so
        # the trailer never reaches generation, verification, citations, or
        # the UI. See enrichment.py.
        chunks_by_doc: dict[str, list[dict]] = {}
        for c in chunks:
            chunks_by_doc.setdefault(c.get("doc_id", ""), []).append(c)
        headings_by_doc = {
            doc_id: build_headings_by_section(cs) for doc_id, cs in chunks_by_doc.items()
        }
        retrieval_texts = [
            build_retrieval_text(c, headings_by_doc[c.get("doc_id", "")]) for c in chunks
        ]
        tokenized = [tokenize(t) for t in retrieval_texts]
        # Kept for the token-overlap check in `retrieve` — see the comment
        # there. Stored rather than read back off BM25Okapi so this does not
        # depend on rank_bm25's internal attributes.
        self._doc_tokens = [set(toks) for toks in tokenized]
        self._bm25 = BM25Okapi(tokenized)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        query_tokens = tokenize(query)
        scores = self._bm25.get_scores(query_tokens)
        # Drop chunks sharing no token with the query. Without this, a query
        # that matches nothing still yields top_k chunks in corpus order —
        # and RRF fuses them at full weight, because it ranks rather than
        # scores. A pure-Devanagari query matches nothing in this English
        # corpus, so BM25 was injecting the same five arbitrary chunks into
        # every Hindi result. See docs/decisions.md 2026-09-20.
        #
        # Tested on token overlap, not `score > 0`: BM25 IDF is exactly zero
        # for a term in half the corpus, which a two-chunk index hits for a
        # genuine match (tests/test_enrichment.py builds one). Overlap says
        # what is actually meant here and holds at any corpus size.
        wanted = set(query_tokens)
        ranked = [
            i
            for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            if self._doc_tokens[i] & wanted
        ][:top_k]
        return [
            {
                "chunk_id": self.chunks[i]["chunk_id"],
                "score": float(scores[i]),
                "text": self.chunks[i]["text"],
                "metadata": {
                    "doc_id": self.chunks[i].get("doc_id", ""),
                    "heading": self.chunks[i].get("heading", ""),
                    "section_number": self.chunks[i].get("section_number", ""),
                },
            }
            for i in ranked
        ]


_index: BM25Index | None = None


def get_index() -> BM25Index:
    global _index
    if _index is None:
        _index = BM25Index(load_all_chunks())
    return _index


def retrieve_bm25(query: str, top_k: int = 5) -> list[dict]:
    return get_index().retrieve(query, top_k)


if __name__ == "__main__":
    idx = get_index()
    print(f"BM25 index built over {len(idx.chunks)} chunks.")
