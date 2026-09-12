"""Vector-only retrieval against the ChromaDB index (Phase 2 — BM25 hybrid comes in Phase 3)."""
import chromadb

from embeddings import embed_texts
from indexing import CHROMA_DB_PATH, COLLECTION_NAME


def get_collection() -> chromadb.api.models.Collection.Collection:
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    return client.get_collection(COLLECTION_NAME)


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    collection = get_collection()
    query_embedding = embed_texts([query])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append(
            {
                "chunk_id": results["ids"][0][i],
                "distance": results["distances"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
            }
        )
    return hits
