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

from authority import get_authority
from citation import format_citation, resolve_authority
from confidence_gate import CONFIDENCE_THRESHOLD, passes_confidence_gate
from hybrid_retrieval import retrieve_hybrid
from retrieval import retrieve as retrieve_vector
from verification import verify_claim

OLLAMA_URL = "http://localhost:11434/api/generate"
GENERATION_MODEL = "qwen2.5:7b"
CANDIDATE_K = 40

REFUSAL_MESSAGE = (
    "I don't have enough grounded information in the corpus to answer this "
    "confidently. Please rephrase, or consult a qualified IP professional."
)

GENERATION_PROMPT_TEMPLATE = """You are an assistant answering a question about Indian Ayurveda IP/regulatory law, using ONLY the source passages given below. Do not use outside knowledge. Every factual claim you make must be directly supported by one of these passages.

For each claim, first find the passage that is MOST SPECIFICALLY and DIRECTLY on point for the question — a passage that discusses the exact topic asked about beats a passage that is merely more general or from a higher-authority document but doesn't address the specific point. Only when two or more passages are EQUALLY specific and directly on point should you prefer the one earlier in the list below (they are pre-sorted by authority for exactly that tie-breaking case, not as a general preference).

Question: {query}

Source passages, numbered, pre-sorted by authority for tie-breaking only:
{passages_block}

Respond with ONLY a JSON object in this exact format, no other text:
{{"claims": [{{"text": "a single factual claim, in your own words but strictly grounded in one passage", "source": <the passage NUMBER it's based on, e.g. 1>}}]}}

If the passages don't actually answer the question, return {{"claims": []}}.
"""


def _select_grounded_hits_with_diagnostics(query: str, top_k: int) -> tuple[list[dict], dict]:
    """Layer 1 gate (on vector distance) + hybrid ordering + authority ordering.

    Returns (hits, diagnostics). The diagnostics are what the UI's pipeline
    view reports (candidate counts, the best distance actually seen vs. the
    threshold) — the selection logic itself is unchanged.
    """
    vector_hits = retrieve_vector(query, top_k=CANDIDATE_K)
    best_distance = vector_hits[0]["distance"] if vector_hits else None
    diagnostics = {
        "candidates_examined": len(vector_hits),
        "best_distance": best_distance,
        "threshold": CONFIDENCE_THRESHOLD,
        "gate_passed": False,
    }
    if not passes_confidence_gate(vector_hits):
        return [], diagnostics
    diagnostics["gate_passed"] = True
    confident_ids = {h["chunk_id"] for h in vector_hits if h["distance"] <= CONFIDENCE_THRESHOLD}
    diagnostics["confident_candidates"] = len(confident_ids)

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
    return top_candidates, diagnostics


def _select_grounded_hits(query: str, top_k: int) -> list[dict]:
    hits, _ = _select_grounded_hits_with_diagnostics(query, top_k)
    return hits


def _build_passages_block(hits: list[dict]) -> str:
    # Numbered labels instead of raw chunk_id strings: observed directly that
    # the model would sometimes paraphrase/truncate a chunk_id like
    # "doc::sec-3" down to just "doc" when copying it into its response,
    # silently failing the lookup back to the source chunk and dropping an
    # otherwise-correct, well-grounded claim (a real false-refusal cause, not
    # hypothetical — see docs/decisions.md). A bare integer is far less prone
    # to that kind of copy error.
    return "\n".join(f"[{i}]\n{h['text']}\n" for i, h in enumerate(hits, start=1))


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


def _refusal(stage: str = "verification") -> dict:
    return {
        "refused": True,
        "refusal_stage": stage,
        "answer": REFUSAL_MESSAGE,
        "citations": [],
        "claims": [],
        "discarded": [],
    }


def _describe_source(hit: dict, index: int) -> dict:
    """Flatten a retrieved hit into what the UI's source rail needs."""
    doc_id = hit["metadata"]["doc_id"]
    meta = get_authority(doc_id)
    return {
        "index": index,
        "chunk_id": hit["chunk_id"],
        "doc_id": doc_id,
        "short_name": meta["short_name"],
        "authority_level": meta["authority_level"],
        "effective_date": meta["effective_date"],
        "section_number": hit["metadata"].get("section_number") or "",
        "heading": hit["metadata"].get("heading") or "",
        "text": hit["text"],
    }


def answer_query_streaming(query: str, top_k: int = 8):
    """Run the pipeline, yielding an event per stage as it happens.

    Same logic as answer_query (which is now a thin wrapper that drains this),
    but observable: the UI renders each layer's decision live rather than
    showing a spinner for the 20-40s a local model takes. Every event is a
    plain dict, JSON-serializable as-is.
    """
    yield {"type": "stage", "stage": "retrieval", "status": "start"}
    hits, diag = _select_grounded_hits_with_diagnostics(query, top_k)
    yield {
        "type": "stage",
        "stage": "retrieval",
        "status": "done",
        "meta": {"candidates_examined": diag["candidates_examined"], "selected": len(hits)},
    }
    yield {
        "type": "stage",
        "stage": "gate",
        "status": "done",
        "meta": {
            "passed": diag["gate_passed"],
            "best_distance": diag["best_distance"],
            "threshold": diag["threshold"],
        },
    }

    if not hits:
        yield {"type": "refused", "refusal_stage": "gate", "result": _refusal("gate")}
        return

    sources = [_describe_source(h, i) for i, h in enumerate(hits, start=1)]
    yield {"type": "sources", "sources": sources}

    yield {"type": "stage", "stage": "generation", "status": "start"}
    draft_claims = _generate_draft_claims(query, hits)
    yield {
        "type": "stage",
        "stage": "generation",
        "status": "done",
        "meta": {"drafted": len(draft_claims)},
    }

    yield {"type": "stage", "stage": "verification", "status": "start",
           "meta": {"total": len(draft_claims)}}

    verified_claims, discarded_claims = [], []
    for i, claim in enumerate(draft_claims):
        source_num = claim.get("source")
        if not isinstance(source_num, int) or not (1 <= source_num <= len(hits)):
            # generation cited a passage number we didn't actually give it
            discarded_claims.append(
                {"text": claim.get("text", ""), "reason": "cited a source that wasn't provided"}
            )
            continue
        chunk = hits[source_num - 1]

        yield {
            "type": "claim",
            "index": i,
            "text": claim["text"],
            "source_index": source_num,
            "status": "verifying",
        }

        try:
            verdict = verify_claim(claim["text"], chunk["text"])
        except (ValueError, requests.RequestException) as exc:
            # fail closed: an unverifiable claim is dropped, not kept
            discarded_claims.append(
                {"text": claim["text"], "reason": f"verification unavailable ({type(exc).__name__})"}
            )
            yield {
                "type": "claim_result",
                "index": i,
                "supported": False,
                "reasoning": "Verification could not be completed, so this claim was dropped.",
                "votes": [],
            }
            continue

        if verdict["supported"]:
            enriched = {
                **claim,
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["metadata"]["doc_id"],
                "section_number": chunk["metadata"].get("section_number"),
            }
            enriched["citation"] = format_citation(
                enriched["doc_id"], enriched["section_number"]
            )
            verified_claims.append(enriched)
        else:
            discarded_claims.append({"text": claim["text"], "reason": verdict["reasoning"]})

        yield {
            "type": "claim_result",
            "index": i,
            "supported": verdict["supported"],
            "reasoning": verdict["reasoning"],
            "votes": verdict.get("votes", []),
            "citation": format_citation(
                chunk["metadata"]["doc_id"], chunk["metadata"].get("section_number")
            )
            if verdict["supported"]
            else None,
            "source_index": source_num,
        }

    if not verified_claims:
        result = _refusal("verification")
        result["discarded"] = discarded_claims
        yield {"type": "refused", "refusal_stage": "verification", "result": result}
        return

    result = {
        "refused": False,
        "refusal_stage": None,
        "answer": "\n".join(f"{c['text']} {c['citation']}" for c in verified_claims),
        "citations": [c["citation"] for c in verified_claims],
        "claims": verified_claims,
        "discarded": discarded_claims,
    }
    yield {"type": "complete", "result": result}


def answer_query(query: str, top_k: int = 8) -> dict:
    """Returns {"refused": bool, "answer": str, "citations": list[str], "claims": list[dict]}."""
    for event in answer_query_streaming(query, top_k):
        if event["type"] in ("complete", "refused"):
            return event["result"]
    return _refusal("verification")
