"""End-to-end pipeline: retrieval -> Layer 1 -> generation -> Layer 2 -> citations.

This is where the PRD's core design principle ("the system must know when it
doesn't know") gets enforced end-to-end, not just per-layer:
  1. Retrieve vector hits (what Layer 1's threshold was calibrated against)
     and hybrid hits (what Phase 3 showed ranks better) separately.
  2. Layer 1 (confidence_gate): refuse immediately if no vector hit clears
     the distance threshold, before spending an LLM call on it.
  3. Restrict to chunks that passed Layer 1, ordered by hybrid rank among
     those survivors — combines "is this even grounded" (vector distance,
     Layer 1's job) with "what's the best ordering" (hybrid, Phase 3's job)
     rather than conflating the two.
  4. Sort by authority (citation.resolve_authority) within that so
     generation sees the most authoritative source first, per doc_id.
  5. Generate a draft answer as a list of discrete claims, each explicitly
     tied to the one chunk_id it's based on (not free-form prose) — that
     structure is what makes per-claim verification possible at all.
  6. Layer 2 (verification): verify each claim against its cited chunk's
     actual text. Drop any claim that doesn't pass — a citation that's real
     but doesn't back the claim must be rejected, not shown.
  7. Compose the final answer only from surviving claims, each formatted
     with citation.format_citation. If every claim was dropped, refuse.

Uses the local Ollama model for generation too (see verification.py's
docstring — no Anthropic API key configured yet, same temporary substitution
for the Claude API the PRD specifies for generation).
"""
import json

import requests

from citation import format_citation, resolve_authority
from confidence_gate import passes_confidence_gate
from hybrid_retrieval import retrieve_hybrid
from retrieval import retrieve as retrieve_vector
from verification import verify_claim

OLLAMA_URL = "http://localhost:11434/api/generate"
GENERATION_MODEL = "qwen2.5:7b"
CANDIDATE_K = 20

REFUSAL_MESSAGE = (
    "I don't have enough grounded information in the corpus to answer this "
    "confidently. Please rephrase, or consult a qualified IP professional."
)

GENERATION_PROMPT_TEMPLATE = """You are an assistant answering a question about Indian Ayurveda IP/regulatory law, using ONLY the source passages given below. Do not use outside knowledge. Every factual claim you make must be directly supported by one of these passages.

Question: {query}

Source passages (in priority order — prefer the more authoritative source when they cover the same point):
{passages_block}

Respond with ONLY a JSON object in this exact format, no other text:
{{"claims": [{{"text": "a single factual claim, in your own words but strictly grounded in one passage", "chunk_id": "the chunk_id of the ONE passage it's based on"}}]}}

If the passages don't actually answer the question, return {{"claims": []}}.
"""


def _select_grounded_hits(query: str, top_k: int) -> list[dict]:
    """Layer 1 gate (on vector distance) + hybrid ordering + authority ordering,
    composed into the final candidate list handed to generation."""
    vector_hits = retrieve_vector(query, top_k=CANDIDATE_K)
    if not passes_confidence_gate(vector_hits):
        return []
    confident_ids = {h["chunk_id"] for h in vector_hits if h["distance"] <= 0.90}

    hybrid_hits = retrieve_hybrid(query, top_k=CANDIDATE_K)
    candidates = [h for h in hybrid_hits if h["chunk_id"] in confident_ids]
    if not candidates:
        # Hybrid's own top-K didn't include any Layer-1-confident chunk even
        # though one exists (possible with a narrow candidate_k) — fall back
        # to the vector-confident hits directly rather than refusing wrongly.
        candidates = [h for h in vector_hits if h["chunk_id"] in confident_ids]

    # Truncate to top_k by relevance (hybrid rank) BEFORE applying authority
    # order — authority is a presentation/tie-break preference among sources
    # covering the same point, not a relevance signal. Sorting the whole
    # candidate pool by authority first would let several lower-relevance,
    # higher-authority-tier chunks bump an actually on-point chunk out of the
    # top_k entirely (this was a real bug, caught by exactly this scenario:
    # the PIB press release's specific statistic outranked by AYUSH-2025
    # boilerplate purely because IPO Guideline > Informational).
    top_candidates = candidates[:top_k]
    doc_ids_present = list({h["metadata"]["doc_id"] for h in top_candidates})
    authority_order = resolve_authority(doc_ids_present)
    top_candidates.sort(key=lambda h: authority_order.index(h["metadata"]["doc_id"]))
    return top_candidates


def _build_passages_block(hits: list[dict]) -> str:
    return "\n".join(f"[{h['chunk_id']}]\n{h['text']}\n" for h in hits)


def _generate_draft_claims(query: str, hits: list[dict]) -> list[dict]:
    prompt = GENERATION_PROMPT_TEMPLATE.format(
        query=query, passages_block=_build_passages_block(hits)
    )
    response = requests.post(
        OLLAMA_URL,
        json={"model": GENERATION_MODEL, "prompt": prompt, "stream": False, "format": "json"},
        timeout=180,
    )
    response.raise_for_status()
    result = json.loads(response.json()["response"])
    claims = result.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError(f"malformed generation response: {result!r}")
    return claims


def _refusal() -> dict:
    return {"refused": True, "answer": REFUSAL_MESSAGE, "citations": [], "claims": []}


def answer_query(query: str, top_k: int = 5) -> dict:
    """Returns {"refused": bool, "answer": str, "citations": list[str], "claims": list[dict]}."""
    hits = _select_grounded_hits(query, top_k)
    if not hits:
        return _refusal()

    chunk_by_id = {h["chunk_id"]: h for h in hits}
    draft_claims = _generate_draft_claims(query, hits)

    verified_claims = []
    for claim in draft_claims:
        chunk = chunk_by_id.get(claim.get("chunk_id"))
        if chunk is None:
            continue  # generation cited a chunk_id we didn't actually give it
        try:
            verdict = verify_claim(claim["text"], chunk["text"])
        except (ValueError, requests.RequestException):
            continue  # fail closed: an unverifiable claim is dropped, not kept
        if verdict["supported"]:
            verified_claims.append(
                {
                    **claim,
                    "doc_id": chunk["metadata"]["doc_id"],
                    "section_number": chunk["metadata"].get("section_number"),
                }
            )

    if not verified_claims:
        return _refusal()

    answer_lines, citations = [], []
    for c in verified_claims:
        cite = format_citation(c["doc_id"], c["section_number"])
        answer_lines.append(f"{c['text']} {cite}")
        citations.append(cite)

    return {
        "refused": False,
        "answer": "\n".join(answer_lines),
        "citations": citations,
        "claims": verified_claims,
    }
