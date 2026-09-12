# Architecture — IP-SAKTI Sahayak

## Tech stack
- Language: Python 3.12
- Framework(s): none yet (CLI scripts only — Phase 1 scope). Later phases add ChromaDB, rank_bm25, Claude API per PRD §7.
- Database (if any): none yet. ChromaDB (local, embedded) planned for Phase 2.
- Key libraries: `pypdf` (PDF text extraction).

## Folder structure
```
corpus/
  raw/            # source PDFs/text, as downloaded — untouched
  processed/      # chunked output, one JSON array of chunks per doc_id
  manifest.md     # provenance: source URL, authority level, effective/publish date per document
src/
  parsing.py      # extract_pages(path) -> per-page text (PDF or .txt)
  chunking.py     # chunk_document(doc_id, pages, body_start_anchor=None) -> list[Chunk]
  run_phase1.py   # Phase 1 gate script: parses+chunks the 3 sample docs, prints + saves output
requirements.txt
.venv/            # local virtualenv, not committed
```

## Data flow (Phase 1, current)
1. `parsing.extract_pages` reads a PDF (via `pypdf`) or `.txt` file and returns one text string per page.
2. `chunking.chunk_document` joins page texts (tracking each page's character offset, for citation page numbers), cleans page-footer noise (amendment footnotes, bare page numbers, amendment-insertion brackets), then chunks structurally:
   - Detect numbered sections/paragraphs at line start; filter out footnote-content false-positives; keep only a strictly-increasing numeric sequence (handles page footnotes that restart their own numbering).
   - If a section's body exceeds ~3000 chars, split further at numbered subsections `(1)`, `(2)`, ... tagging each with its parent section number.
   - If no numbering is detected at all in a region, fall back to paragraph-grouping (blank-line delimited, merged toward a target size) — never a fixed-token window.
3. Each `Chunk` carries: `doc_id`, `chunk_id`, `heading`, `section_number`, `parent_section_number`, `page_start`, `page_end`, `text`, `char_count`.
4. Output written to `corpus/processed/<doc_id>.json`.

Not yet built: embeddings, vector store, BM25, retrieval, verification layers, generation, UI — these arrive in later phases per PRD §9.

## Deployment / how it runs
Local only, for now. `python -m venv .venv` + `pip install -r requirements.txt`, then `python src/run_phase1.py`.
