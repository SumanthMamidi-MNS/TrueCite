"""Stage 3 of the pipeline — relevance filter (pointwise LLM-as-judge over
Layer-1-approved passages, run once before generation).

NOT part of the PRD's numbered 3-layer defense (Layer 1/2/3) — it's a fixed,
new stage added after live testing found a real gap those three don't cover:
Layer 1 checks raw vector *distance*, which is a similarity score, not a
judgment of whether a passage is actually on-topic for the question. A
passage can clear the distance threshold while being about the wrong
document entirely (see docs/decisions.md's WIPO GRATK Treaty vs. WIPO TK
Toolkit conflation — the correct passage was always retrieved, generation
still drafted a claim about the other document). This stage screens that
out before generation ever sees it.

Deliberately non-blocking: this project's own Phase 6 numbers show a 0/5
false-answer rate against a 5/11 false-refusal rate — the system's failure
mode is over-refusing, not over-asserting. A stage that could refuse would
attack the metric that's already perfect and worsen the one that's already
bad. So this stage only ever narrows the passage set generation sees, never
decides to refuse, and fails open (keeps everything) on any error — same
precedent as generate._condense_followup, for the same reason: it can only
make generation's job easier, so it must never be able to sink the answer.
"""
import json

import llm_client

# Never filter below this many passages, even if every one is judged
# irrelevant — the floor exists so a bad batch of verdicts can narrow the
# set but can never come close to emptying it outright.
MIN_KEEP = 3

# How much of each passage to actually show the model for this stage. Found
# live, not hypothetical: batching all 8 passages at full length (chunks run
# up to MAX_CHUNK_CHARS=3000 each, some front-matter/preamble chunks larger
# still) produced a ~90,000-character prompt that overflowed the local
# model's context — it silently answered as if only the first passage
# existed, which judge_relevance correctly caught and raised on (see its
# docstring), and the caller correctly failed open. But that meant this
# stage rarely actually filtered anything in practice. Judging TOPICAL
# relevance doesn't need the full passage, only enough to identify what it's
# about — a preview is a real accuracy/context-budget trade, not free, but
# the alternative observed live was "silently never fires."
PASSAGE_PREVIEW_CHARS = 400

RELEVANCE_PROMPT_TEMPLATE = """For the question below, judge each numbered passage: is it actually about the topic the question asks about? Mark a passage irrelevant ONLY if it is clearly about a different topic, a different legal instrument, or a different document than the question concerns. If it is plausibly on point, even partially, mark it relevant — you are screening out clearly off-topic passages, not picking the single best one.

Question: {query}

Passages:
{passages_block}

Respond with ONLY a JSON object in this exact format, no other text, with exactly one verdict per passage number shown above:
{{"verdicts": [{{"index": 1, "relevant": true or false, "reason": "a few words"}}, ...]}}
"""


def _build_passages_block(hits: list[dict]) -> str:
    return "\n".join(f"[{i}]\n{h['text']}\n" for i, h in enumerate(hits, start=1))


def judge_relevance(query: str, hits: list[dict], timeout: int = 120) -> list[dict]:
    """One LLM call judging every passage at once (batched — a call per
    passage would cost 20-60s locally for a coarse judgment, not worth it).

    Raises on anything short of a complete, well-formed verdict set — a
    partial or malformed response must never be read as "the rest are
    irrelevant" by a caller. The caller (answer_query_streaming) is what
    decides to fail open; this function itself stays fail-closed at the
    parsing level, same split as _condense_followup / verify_claim.
    """
    if not hits:
        return []
    prompt = RELEVANCE_PROMPT_TEMPLATE.format(
        query=query, passages_block=_build_passages_block(hits)
    )
    raw = llm_client.complete(prompt, timeout=timeout, temperature=0.0, seed=42)
    result = json.loads(raw)
    verdicts = result.get("verdicts")
    if not isinstance(verdicts, list):
        raise ValueError(f"malformed relevance response: {result!r}")

    by_index = {}
    for v in verdicts:
        if not isinstance(v, dict) or not isinstance(v.get("relevant"), bool):
            raise ValueError(f"malformed relevance verdict: {v!r}")
        idx = v.get("index")
        if not isinstance(idx, int):
            raise ValueError(f"malformed relevance verdict index: {v!r}")
        by_index[idx] = v

    if set(by_index) != set(range(1, len(hits) + 1)):
        raise ValueError(
            f"relevance verdicts don't cover every passage: got {sorted(by_index)}, "
            f"expected 1..{len(hits)}"
        )
    return [by_index[i] for i in range(1, len(hits) + 1)]


def apply_relevance(
    hits: list[dict], verdicts: list[dict], min_keep: int = MIN_KEEP
) -> tuple[list[dict], list[dict]]:
    """Pure, no LLM call. Returns (kept_hits, dropped_records).

    Preserves the incoming order of `hits` — that order already reflects
    hybrid-relevance truncation and Layer 3's authority sort; this stage
    only removes entries, it never reorders (reordering is Layer 3's job).
    Enforces `min_keep`: if fewer than that many passages were judged
    relevant, the judged-irrelevant ones are added back in their original
    order until the floor is reached, so a bad batch of verdicts can narrow
    generation's input but never starve it.
    """
    relevant_idx = {v["index"] for v in verdicts if v["relevant"]}
    kept, dropped = [], []
    for i, hit in enumerate(hits, start=1):
        (kept if i in relevant_idx else dropped).append((i, hit))

    if len(kept) < min_keep:
        need = min_keep - len(kept)
        kept.extend(dropped[:need])
        dropped = dropped[need:]
        kept.sort(key=lambda pair: pair[0])

    kept_hits = [hit for _, hit in kept]
    reason_by_index = {v["index"]: v.get("reason", "") for v in verdicts}
    dropped_records = [
        {"chunk_id": hit["chunk_id"], "reason": reason_by_index.get(i, "")} for i, hit in dropped
    ]
    return kept_hits, dropped_records
