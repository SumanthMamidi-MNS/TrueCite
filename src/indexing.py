"""Build the ChromaDB index from corpus/processed/*.json chunk files."""
import json
from pathlib import Path

import chromadb

from embeddings import embed_texts
from enrichment import build_headings_by_section, build_retrieval_text

CORPUS_PROCESSED = Path(__file__).resolve().parent.parent / "corpus" / "processed"
CHROMA_DB_PATH = Path(__file__).resolve().parent.parent / "corpus" / "chroma_db"
COLLECTION_NAME = "ip_sakti_chunks"


def load_all_chunks() -> list[dict]:
    chunks = []
    for path in sorted(CORPUS_PROCESSED.glob("*.json")):
        chunks.extend(json.loads(path.read_text(encoding="utf-8")))
    return chunks


def _metadata_for(chunk: dict) -> dict:
    # Chroma metadata values can't be None, so empty-string any unset field.
    return {
        "doc_id": chunk["doc_id"],
        "heading": chunk["heading"] or "",
        "section_number": chunk["section_number"] or "",
        "parent_section_number": chunk["parent_section_number"] or "",
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],
    }


def build_index(batch_size: int = 32) -> chromadb.api.models.Collection.Collection:
    """(Re)build the index from scratch. Safe to re-run as the corpus/chunker changes."""
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    chunks = load_all_chunks()

    # Headings are only valid cross-reference targets within their own
    # document (enrichment.py's build_headings_by_section docstring), so the
    # map is built per doc_id, not once globally.
    chunks_by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        chunks_by_doc.setdefault(c["doc_id"], []).append(c)
    headings_by_doc = {doc_id: build_headings_by_section(cs) for doc_id, cs in chunks_by_doc.items()}

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        # THE SAFETY PROPERTY: embed the enriched text (so retrieval scoring
        # can see same-document cross-references), but store the chunk's TRUE
        # text as the Chroma `documents` — that's what a hit returns, and
        # what generation/citations/the UI ever see. See enrichment.py.
        retrieval_texts = [build_retrieval_text(c, headings_by_doc[c["doc_id"]]) for c in batch]
        true_texts = [c["text"] for c in batch]
        embeddings = embed_texts(retrieval_texts)
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=embeddings,
            documents=true_texts,
            metadatas=[_metadata_for(c) for c in batch],
        )
    return collection


if __name__ == "__main__":
    coll = build_index()
    print(f"Indexed {coll.count()} chunks into {CHROMA_DB_PATH}")
