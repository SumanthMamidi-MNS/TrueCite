"""Tests for the passage-level retrieval harness's scoring primitives.

These run against stubbed hit lists, never the real index — the point is that
the *scoring* is trustworthy before any retrieval number it reports is used to
accept or reject a change.

The important case here is the ">40" sentinel. A gold chunk that is absent from
the candidate list entirely must be reported as a miss, never silently scored as
rank 0 or folded in with "found but ranked poorly" — that distinction is the
whole reason this harness exists (the Biological Diversity Act §55 case, where
the correct passage was absent from every retriever's top 40 while a
wrong-but-similar section ranked 3rd).
"""
import run_retrieval_eval as rre


def hit(chunk_id: str, doc_id: str | None = None) -> dict:
    return {
        "chunk_id": chunk_id,
        "metadata": {"doc_id": doc_id or chunk_id.split("::")[0]},
    }


def test_rank_of_finds_first_gold_chunk():
    hits = [hit("d::a"), hit("d::b"), hit("d::c")]
    assert rre.rank_of(hits, {"d::b"}) == 2


def test_rank_of_is_one_based_not_zero_based():
    assert rre.rank_of([hit("d::a")], {"d::a"}) == 1


def test_rank_of_returns_first_match_when_several_gold_chunks_present():
    hits = [hit("d::a"), hit("d::b"), hit("d::c")]
    assert rre.rank_of(hits, {"d::c", "d::b"}) == 2


def test_rank_of_returns_none_when_gold_absent():
    """Absent must be None, NOT 0 — 0 would sort as the best possible rank."""
    hits = [hit("d::a"), hit("d::b")]
    assert rre.rank_of(hits, {"d::zzz"}) is None


def test_rank_of_none_is_rendered_as_beyond_depth_sentinel():
    assert rre._fmt(None) == f">{rre.SEARCH_DEPTH}"
    assert rre._fmt(None, 8) == ">8"
    assert rre._fmt(3) == "3"


def test_missing_gold_is_not_counted_as_a_hit():
    """The regression this guards: a miss scoring as recall because None is falsy
    in one place and 0-like in another."""
    hits = [hit("d::a")]
    rank = rre.rank_of(hits, {"d::missing"})
    assert rank is None
    assert not (rank is not None)


def test_exit_code_is_zero_when_controls_all_stopped():
    assert rre._exit_code({"unrelated_controls_all_stopped": True}) == 0


def test_exit_code_is_nonzero_when_a_control_regresses():
    """The one hard safety regression this harness detects — an unrelated
    control no longer stopped at the gate — must fail the process, not just
    print '<-- REGRESSION' and exit 0 like the script used to."""
    assert rre._exit_code({"unrelated_controls_all_stopped": False}) == 1


def test_doc_rank_matches_on_document_not_chunk():
    hits = [hit("other::x", "other"), hit("target::y", "target")]
    assert rre.doc_rank_of(hits, {"target"}) == 2
    assert rre.doc_rank_of(hits, {"absent"}) is None


def test_every_answerable_question_has_a_gold_entry():
    """run_phase6.ANSWERABLE and this harness's GOLD table must not drift apart —
    exactly the failure mode that left the eval's expected-doc sets stale after a
    new document was added to the corpus."""
    from run_phase6 import ANSWERABLE

    missing = [q for q, _ in ANSWERABLE if q not in rre.GOLD]
    assert not missing, f"questions with no GOLD entry: {missing}"


def test_gold_chunk_ids_all_exist_in_the_processed_corpus():
    """Catches a gold id that names a chunk the chunker no longer produces —
    how docs/eval_questions.md came to reference `patents_act_1970::sec-3`, an id
    that does not exist because §3 is split per lettered clause."""
    import glob
    import json
    from pathlib import Path

    root = Path(rre.__file__).resolve().parent.parent
    ids = set()
    for path in glob.glob(str(root / "corpus" / "processed" / "*.json")):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        chunks = data["chunks"] if isinstance(data, dict) else data
        ids |= {c["chunk_id"] for c in chunks}

    if not ids:  # corpus not built in this environment — nothing to check
        return

    unknown = sorted(
        {cid for gold in rre.GOLD.values() for cid in gold["chunks"]} - ids
    )
    assert not unknown, f"gold chunk_ids not present in corpus/processed: {unknown}"
