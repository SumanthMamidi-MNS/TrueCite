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

Generation runs through llm_client too (see verification.py's docstring —
same temporary local-Ollama substitution, same one-env-var switch to the
real Claude API once it's actually in use).
"""
import json
import os

import llm_client
from authority import get_authority
from escalation import STANDING_DISCLAIMER, assess
from citation import format_citation, resolve_authority
from confidence_gate import CONFIDENCE_THRESHOLD, passes_confidence_gate
from coverage import assess_coverage
from hybrid_retrieval import _in_jurisdiction, retrieve_hybrid
from knowledge_graph import related_instruments, section_references
from routing import prior_art_pointer, route
from relevance import apply_relevance, judge_relevance
from retrieval import retrieve as retrieve_vector
from verification import verify_claim

# The active model's name, whichever provider llm_client is configured for —
# so the UI's model badge (see api.py's /api/config) always names what's
# actually running, Ollama or (once deployed) the real Anthropic API.
GENERATION_MODEL = llm_client.active_model_name()
CANDIDATE_K = 40
MAX_HISTORY_TURNS = 3

# Fixed seed, temperature 0: generation only ever runs once per query (no
# vote to preserve, unlike verification below), so there's no reason not to
# make it fully reproducible — same query, same passages in, same claims
# out, which matters for eval runs and for debugging a specific answer.
GENERATION_SEED = int(os.environ.get("GENERATION_SEED", "42"))

REFUSAL_MESSAGE = (
    "I don't have enough grounded information in the corpus to answer this "
    "confidently. Please rephrase, or consult a qualified IP professional."
)

# A THIRD, distinct terminal state alongside "complete" and "refused" — see
# ProviderRateLimited's and ProviderUnreachable's docstrings in llm_client.py.
# This must never be spelled like REFUSAL_MESSAGE above: that message is
# specifically about the corpus not grounding an answer (Layer 1/2's job),
# while these are about the LLM infrastructure itself being temporarily
# unavailable — an entirely different thing the user needs to know, and act
# on differently (retry shortly, vs. rephrase or consult a professional).
#
# Two messages, not one, because the two exceptions mean genuinely different
# things and collapsing them into one generic string would misrepresent
# whichever cause didn't actually happen: ProviderRateLimited means the
# provider WAS reached and explicitly said "slow down" — "busy" is literally
# accurate here, so it's used, in the friendly server-is-just-busy register
# a rate limit deserves. ProviderUnreachable means the provider was never
# reached at all (connection refused, or timed out waiting) — calling that
# "busy" would claim contact that never happened, so it gets "isn't
# responding" instead, which is honest either way (a stopped local Ollama or
# a hung timeout both fit "isn't responding" without overclaiming a cause).
PROVIDER_BUSY_MESSAGE = (
    "Our AI server is busy right now — please try again in a moment."
)
PROVIDER_UNREACHABLE_MESSAGE = (
    "Our AI server isn't responding right now — please try again in a moment."
)


def _provider_unavailable_event(exc: Exception) -> dict:
    # isinstance, not a lookup table keyed by exception type — there are only
    # ever these two causes (see llm_client.py), and this is the same
    # explicit isinstance-per-cause shape callers already use to catch both
    # exceptions in the first place.
    message = (
        PROVIDER_BUSY_MESSAGE
        if isinstance(exc, llm_client.ProviderRateLimited)
        else PROVIDER_UNREACHABLE_MESSAGE
    )
    return {"type": "provider_unavailable", "message": message}


GENERATION_PROMPT_TEMPLATE = """You are an assistant answering a question about Indian Ayurveda IP/regulatory law, using ONLY the source passages given below. Do not use outside knowledge. Every factual claim you make must be directly supported by one of these passages. Use the passage's own spelling and wording for every name, technical term, section number, figure, and date — copy them exactly as they appear in the passage, even if a different spelling is more common. When your claim states or implies a specific section, sub-section, or clause number as the legal basis for a fact, that number must be the one that actually appears in the passage you are citing for that claim — never a number recalled from general knowledge or a different passage, even if it seems more specific or correct.

For each claim, first find the passage that is MOST SPECIFICALLY and DIRECTLY on point for the question — a passage that discusses the exact topic asked about beats a passage that is merely more general or from a higher-authority document but doesn't address the specific point. Only when two or more passages are EQUALLY specific and directly on point should you prefer the one earlier in the list below (they are pre-sorted by authority for exactly that tie-breaking case, not as a general preference).

Question: {query}

Source passages, numbered, pre-sorted by authority for tie-breaking only:
{passages_block}

Respond with ONLY a JSON object in this exact format, no other text:
{{"claims": [{{"text": "a single factual claim, in your own words but strictly grounded in one passage", "source": <the passage NUMBER it's based on, e.g. 1>}}]}}

If the passages don't actually answer the question, return {{"claims": []}}.
"""

CONDENSE_PROMPT_TEMPLATE = """Rewrite the follow-up question below as a standalone question that includes whatever context it depends on from the conversation so far — do not answer it, only rewrite it. If it is already standalone, return it unchanged. Do not invent facts that weren't in the conversation.

Conversation so far:
{history_block}

Follow-up question: {query}

Respond with ONLY a JSON object in this exact format, no other text:
{{"standalone_question": "the rewritten question"}}
"""


def _select_grounded_hits_with_diagnostics(
    query: str, top_k: int, jurisdiction: str | None = None
) -> tuple[list[dict], dict]:
    """Layer 1 gate (on vector distance) + hybrid ordering + authority ordering.

    Returns (hits, diagnostics). The diagnostics are what the UI's pipeline
    view reports (candidate counts, the best distance actually seen vs. the
    threshold) — the selection logic itself is unchanged.
    """
    # Layer 1 judges confidence on the SAME jurisdiction the answer will be
    # drawn from. Gating on a mixed pool would let a confident international
    # chunk open the gate for an India-scoped question that has no grounded
    # Indian source -- the gate would pass and the answer would then be
    # built from weaker material, which is precisely the failure Layer 1
    # exists to prevent.
    if jurisdiction:
        vector_hits = [
            h for h in retrieve_vector(query, top_k=CANDIDATE_K * 3)
            if _in_jurisdiction(h, jurisdiction)
        ][:CANDIDATE_K]
    else:
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

    # candidate_k must be passed explicitly here, not left at retrieve_hybrid's
    # own default (20) — this call already asks for top_k=CANDIDATE_K (40),
    # and without candidate_k=CANDIDATE_K too, RRF was only ever fusing the
    # top 20 from each retriever while the vector list used for Layer 1 above
    # is 40 deep: the two halves of the pipeline disagreed about how far down
    # they look, so anything at vector rank 21-40 never entered fusion at
    # all. Same shape of bug docs/decisions.md already records once (CANDIDATE_K
    # itself was raised 20->40 after a correctly-worded statutory clause
    # ranked #29 was outside the old fetch window) — a retrieval window too
    # narrow to reach a passage that's actually there.
    hybrid_hits = retrieve_hybrid(
        query, top_k=CANDIDATE_K, candidate_k=CANDIDATE_K, jurisdiction=jurisdiction
    )
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


def _select_grounded_hits(query: str, top_k: int, jurisdiction: str | None = None) -> list[dict]:
    hits, _ = _select_grounded_hits_with_diagnostics(query, top_k, jurisdiction)
    return hits


def _build_passages_block(hits: list[dict]) -> str:
    # Numbered labels instead of raw chunk_id strings: observed directly that
    # the model would sometimes paraphrase/truncate a chunk_id like
    # "doc::sec-3" down to just "doc" when copying it into its response,
    # silently failing the lookup back to the source chunk and dropping an
    # otherwise-correct, well-grounded claim (a real false-refusal cause, not
    # hypothetical — see docs/decisions.md). A bare integer is far less prone
    # to that kind of copy error.
    #
    # Each passage is also labeled with its source document's short_name.
    # Added after observing the model draft a claim about "the Toolkit" when
    # asked about the WIPO GRATK Treaty — both documents are WIPO-published
    # and discuss documenting/disclosing genetic-resources-related TK, and
    # with passages given as bare unlabeled text the model conflated them
    # even though the correct passage (the treaty's own disclosure article)
    # was right there in the list. The label doesn't fix the model being
    # wrong, but gives it an explicit anchor to tell same-topic documents
    # apart, which a bare passage number can't.
    return "\n".join(
        f"[{i}] (Source: {get_authority(h['metadata']['doc_id'])['short_name']})\n{h['text']}\n"
        for i, h in enumerate(hits, start=1)
    )


def _generate_draft_claims(query: str, hits: list[dict]) -> list[dict]:
    prompt = GENERATION_PROMPT_TEMPLATE.format(
        query=query, passages_block=_build_passages_block(hits)
    )
    raw = llm_client.complete(prompt, timeout=180, temperature=0.0, seed=GENERATION_SEED)
    result = json.loads(raw)
    claims = result.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError(f"malformed generation response: {result!r}")
    return claims


def _format_history(history: list[dict]) -> str:
    return "\n".join(f"Q: {turn['q']}\nA: {turn['a']}" for turn in history)


def _condense_followup(query: str, history: list[dict]) -> str:
    """Rewrite a follow-up into a standalone question using recent turns.

    Only the *query* is rewritten — retrieval, generation, and verification
    still ground strictly in corpus passages, never in conversation history,
    so this can't introduce an ungrounded claim; the worst case is a bad
    rewrite that retrieves the wrong passages, which Layer 1/2 still catch.
    Fails open to the original query on any error (see call site) rather
    than blocking the whole answer on a single extra LLM call.
    """
    prompt = CONDENSE_PROMPT_TEMPLATE.format(
        history_block=_format_history(history), query=query
    )
    raw = llm_client.complete(prompt, timeout=60, temperature=0.0, seed=GENERATION_SEED)
    result = json.loads(raw)
    standalone = result.get("standalone_question")
    if not isinstance(standalone, str) or not standalone.strip():
        raise ValueError(f"malformed condense response: {result!r}")
    return standalone.strip()


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



def _advisory_event(query: str, *, refused: bool, best_distance: float | None,
                    rejected_claims: int = 0, claims: list[dict] | None = None,
                    jurisdiction: str | None = None) -> dict:
    """Everything the pipeline can say ABOUT an answer, as one terminal event.

    Kept out of the answer text deliberately. The disclaimer, the confidence
    label and the escalation offer are not claims drawn from a source, so
    folding them into the answer would put unverifiable sentences next to
    verified ones and ask Layer 2 to check them against a passage. Here they
    are unambiguously commentary.
    """
    routed = route(query)
    out_of_coverage = [e["regime"] for e in routed["out_of_coverage"]]
    advice = assess(
        refused=refused,
        best_distance=best_distance,
        rejected_claims=rejected_claims,
        out_of_coverage_regimes=out_of_coverage,
    )
    return {
        "type": "advisory",
        "disclaimer": STANDING_DISCLAIMER,
        "confidence": advice["confidence"],
        "escalate": advice["escalate"],
        "escalation_reasons": advice["reasons"],
        "escalation_guidance": advice["guidance"],
        "regimes_in_coverage": [e["regime"] for e in routed["in_coverage"]],
        "regimes_out_of_coverage": out_of_coverage,
        "prior_art_pointer": prior_art_pointer(query),
        "related_law": _related_law(claims or [], jurisdiction),
    }


def _related_law(claims: list[dict], jurisdiction: str | None) -> dict:
    """Knowledge-graph navigation for the instruments and provisions an answer
    actually cited. Empty on a refusal — there is nothing cited to relate."""
    doc_ids = list(dict.fromkeys(c["doc_id"] for c in claims if c.get("doc_id")))
    provisions = []
    for c in claims:
        refs = section_references(c.get("chunk_id", ""))
        if refs:
            provisions.append({"citation": c.get("citation"), "refers_to": refs})
    return {
        "instruments": related_instruments(doc_ids, jurisdiction),
        "provisions": provisions,
    }


def answer_query_streaming(
    query: str,
    top_k: int = 8,
    history: list[dict] | None = None,
    relevance_filter: bool = False,
    coverage_check: bool = True,
    jurisdiction: str | None = None,
):
    """Run the pipeline, yielding an event per stage as it happens.

    Same logic as answer_query (which is now a thin wrapper that drains this),
    but observable: the UI renders each layer's decision live rather than
    showing a spinner for the 20-40s a local model takes. Every event is a
    plain dict, JSON-serializable as-is.

    `history` is the last few (q, a) turns of the current conversation, used
    ONLY to rewrite a follow-up into a standalone question before retrieval
    (see `_condense_followup`) — it never reaches generation or verification
    directly, so a follow-up still can't be answered from anything but the
    corpus.

    `relevance_filter` and `coverage_check` gate the two non-blocking stages
    added alongside the PRD's 3-layer defense (see relevance.py / coverage.py
    for why they're non-blocking and untagged in the UI, not "Layer 4/5").
    `relevance_filter` defaults OFF: A/B'd against the 16-question eval set
    (run_phase6.py) and it made the false-refusal rate worse, not better
    (4/11 -> 6/11), with no gain in citation accuracy — it was dropping
    load-bearing passages, exactly the risk flagged when it was built. See
    docs/decisions.md for the numbers. The code stays in (relevance.py,
    tests, the `relevance_filter=True` override) for retuning later — a
    higher MIN_KEEP or a looser prompt might fix it — but it must not ship
    on by default while it measurably hurts the metric that matters most.
    `coverage_check` defaults on: advisory-only, can't cause a refusal, and
    wasn't implicated by this measurement.
    """
    effective_query = query
    if history:
        yield {"type": "stage", "stage": "condense", "status": "start"}
        try:
            effective_query = _condense_followup(query, history[-MAX_HISTORY_TURNS:])
        except (llm_client.ProviderRateLimited, llm_client.ProviderUnreachable) as exc:
            # Deliberately NOT folded into the fail-open Exception handler
            # below. Falling back to the raw query here would just delay the
            # same failure to the generation call a few lines down (still
            # the same unavailable provider) at the cost of a wasted
            # retrieval pass and more retry latency already spent above —
            # stopping now, with an honest "infrastructure unavailable"
            # event, is both faster and doesn't dress up an outage as
            # anything else.
            yield _provider_unavailable_event(exc)
            return
        except Exception:
            # Broad on purpose: this must fail open to the original query
            # regardless of which provider llm_client is configured for
            # (requests' exceptions for Ollama, the anthropic SDK's own
            # exception types once deployed with a real key, or a malformed
            # response caught as ValueError) — a broken rewrite can never be
            # allowed to sink the whole answer.
            effective_query = query
        yield {
            "type": "stage",
            "stage": "condense",
            "status": "done",
            "meta": {
                "standalone_question": effective_query,
                "rewritten": effective_query != query,
            },
        }

    yield {"type": "stage", "stage": "retrieval", "status": "start"}
    hits, diag = _select_grounded_hits_with_diagnostics(effective_query, top_k, jurisdiction)
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
        # The advisory matters MOST here, not least: the user has just been
        # told this tool cannot answer, so the standing disclaimer and the
        # pointer to a human are the only useful things left to give them.
        # Missing it on this path was a real gap — the other two exits had it.
        yield _advisory_event(query, refused=True, best_distance=diag.get("best_distance"))
        return

    if relevance_filter:
        yield {"type": "stage", "stage": "relevance", "status": "start", "meta": {"total": len(hits)}}
        try:
            verdicts = judge_relevance(effective_query, hits)
            hits, dropped = apply_relevance(hits, verdicts)
            yield {
                "type": "stage",
                "stage": "relevance",
                "status": "done",
                "meta": {
                    "failed_open": False,
                    "total": len(hits) + len(dropped),
                    "kept": len(hits),
                    "dropped": len(dropped),
                    "dropped_detail": dropped,
                },
            }
        except Exception:
            # Fail open — see relevance.py's docstring: this stage only ever
            # narrows an already-Layer-1-approved set, so on any failure the
            # safe default is to change nothing, not to guess a narrowing.
            yield {
                "type": "stage",
                "stage": "relevance",
                "status": "done",
                "meta": {"failed_open": True, "total": len(hits), "kept": len(hits), "dropped": 0},
            }

    # sources/indices are built from `hits` AFTER the filter above, so a
    # claim's `source` index (resolved via hits[source_num - 1] below) and
    # every card in the UI's source rail always agree on which passage is
    # which — filtering after this point would desynchronize the two.
    sources = [_describe_source(h, i) for i, h in enumerate(hits, start=1)]
    yield {"type": "sources", "sources": sources}

    yield {"type": "stage", "stage": "generation", "status": "start"}
    try:
        draft_claims = _generate_draft_claims(effective_query, hits)
    except (llm_client.ProviderRateLimited, llm_client.ProviderUnreachable) as exc:
        yield _provider_unavailable_event(exc)
        return
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
        except (llm_client.ProviderRateLimited, llm_client.ProviderUnreachable) as exc:
            # Same reasoning as the generation/condense call sites: an
            # unavailable provider (rate-limited or plain unreachable) must
            # surface as "infrastructure unavailable", never as a per-claim
            # "verification unavailable" that quietly accumulates into a
            # Layer 2 grounding refusal once every claim has been dropped
            # this way (see verification.py's re-raise of these exact
            # exceptions, for exactly this reason).
            yield _provider_unavailable_event(exc)
            return
        except Exception as exc:
            # fail closed: an unverifiable claim is dropped, not kept.
            # Broad on purpose, same reasoning as the condense fallback
            # above — must work the same way regardless of which provider
            # llm_client is configured for.
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
        yield _advisory_event(query, refused=True,
                              best_distance=diag.get("best_distance"),
                              rejected_claims=len(discarded_claims))
        return

    result = {
        "refused": False,
        "refusal_stage": None,
        "answer": "\n".join(f"{c['text']} {c['citation']}" for c in verified_claims),
        "citations": [c["citation"] for c in verified_claims],
        "claims": verified_claims,
        "discarded": discarded_claims,
    }

    if coverage_check:
        # Never runs on a refusal path (both `return`s above already exited)
        # — there is no answer to assess, and spending a call to conclude
        # "this refusal doesn't answer the question" wastes latency on the
        # path the user is already unhappy with.
        yield {"type": "stage", "stage": "coverage", "status": "start"}
        try:
            verdict = assess_coverage(effective_query, result["answer"])
            result["coverage"] = verdict
            yield {
                "type": "stage",
                "stage": "coverage",
                "status": "done",
                "meta": {
                    "available": True,
                    "addresses": verdict["addresses"],
                    "gap": verdict["gap"],
                    "assessed_against": effective_query,
                },
            }
        except Exception:
            # Fail open — see coverage.py's docstring: no verdict, never a
            # negative one guessed from a failure, and the answer already
            # assembled above renders exactly as if this stage didn't run.
            # Deliberately NOT special-cased for ProviderRateLimited (unlike
            # condense/generation/verification above): coverage is
            # advisory-only on an ALREADY-verified, already-complete answer
            # (see coverage.py's docstring — it never modifies answer/claims/
            # citations and this project's own Phase 6 numbers are why it's
            # non-blocking). A quota failure here has nothing left to sink —
            # there's a good answer either way — so it falls into this
            # existing broad `except Exception`, same as any other coverage
            # failure, rather than discarding a successful answer to report
            # an infrastructure hiccup on a stage that was never load-bearing.
            result["coverage"] = None
            yield {"type": "stage", "stage": "coverage", "status": "done", "meta": {"available": False}}

    yield _advisory_event(
        query,
        refused=False,
        best_distance=diag.get("best_distance"),
        rejected_claims=len(result.get("discarded") or []),
        claims=result.get("claims") or [],
        jurisdiction=jurisdiction,
    )
    yield {"type": "complete", "result": result}


def answer_query(
    query: str,
    top_k: int = 8,
    history: list[dict] | None = None,
    relevance_filter: bool = False,
    coverage_check: bool = True,
) -> dict:
    """Returns {"refused": bool, "answer": str, "citations": list[str], "claims": list[dict]}."""
    for event in answer_query_streaming(
        query, top_k, history=history, relevance_filter=relevance_filter, coverage_check=coverage_check
    ):
        if event["type"] in ("complete", "refused"):
            return event["result"]
    return _refusal("verification")
