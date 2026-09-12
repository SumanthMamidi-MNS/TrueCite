"""BM25 keyword retrieval over the corpus chunks — the keyword half of Phase 3's hybrid search.

Independent of the embedding model/ChromaDB: BM25 is pure lexical (term-frequency)
matching, built directly from corpus/processed/*.json, no vectors involved.
"""
import re

from rank_bm25 import BM25Okapi

from indexing import load_all_chunks

# \w in Python's re is Unicode-aware by default, so this tokenizes Hindi text
# reasonably too (PRD §6.3 requires English + Hindi at minimum) — not verified
# against real Hindi content yet since the corpus is English-only so far.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c["text"]) for c in chunks])

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
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
