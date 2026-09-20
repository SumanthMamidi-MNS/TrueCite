# Container image for TrueCite (runs on any Docker host; see docker-compose.yml).
#
# Python 3.12 to match what this project was built and tested against
# (docs/architecture.md: "Language: Python 3.12").
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first, separately from the app code, so an app-only
# change (e.g. a README edit) doesn't invalidate this layer and force a full
# reinstall of sentence-transformers/torch/chromadb on every rebuild.
COPY requirements.txt .
# sentence-transformers pulls in torch; PyPI's default wheel bundles full
# CUDA support (~3GB of libraries this CPU-only deployment never uses).
# Installing the CPU-only build first (unpinned, so the same file also
# builds on ARM servers) keeps the rest of the install from quietly
# pulling the CUDA build back in.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Only what src/api.py actually reads at request time (see src/generate.py,
# src/indexing.py, src/retrieval.py, src/bm25_retrieval.py):
#   - src/     the pipeline itself
#   - web/     the static UI api.py serves at "/"
#   - corpus/processed/  parsed+chunked corpus JSON (bm25_retrieval.py reads
#                         it directly; indexing.load_all_chunks too)
#   - corpus/chroma_db/  the prebuilt vector index (retrieval.py's
#                         PersistentClient loads it directly, no rebuild)
#   - corpus/raw/        the original source PDFs; not read by the running
#                         app (citations link to their public source_url in
#                         authority.py), kept in the image for provenance and
#                         so the corpus can be reprocessed from inside a
#                         running container if ever needed
# docs/, tests/, and corpus/eval_results/ are deliberately left out — none
# of them are needed to serve the app, and leaving them out keeps the image
# lean.
COPY src/ ./src/
COPY web/ ./web/
COPY corpus/raw/ ./corpus/raw/
COPY corpus/processed/ ./corpus/processed/
COPY corpus/chroma_db/ ./corpus/chroma_db/

EXPOSE 8000

# LLM_PROVIDER / GEMINI_API_KEY / ANTHROPIC_API_KEY are intentionally not set
# here — they're supplied at runtime through the host's environment or a
# local .env file (see docker-compose.yml). Unset,
# llm_client.py already defaults to the local Ollama provider, which is a
# safe (if non-functional without an Ollama host reachable from the
# container) default rather than silently baking in a provider choice.
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
