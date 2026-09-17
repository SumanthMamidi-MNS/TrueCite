"""Guards against the eval's ground truth silently drifting out of date.

This exists because it already happened. The Biological Diversity Act was added
to the corpus on 2026-09-13, but run_phase6.ANSWERABLE's expected-document sets
had been written on 2026-09-12 and were never revisited. The system then cited
the Act's own §6 for a question that asks *about the Act*, and the eval scored
that as a MISS — the measuring instrument was wrong, not the system.

Nothing here checks that an answer is correct. These only check that the eval's
ground truth refers to documents and passages that actually exist in the corpus,
which is the specific failure mode that produced the stale entries.
"""
import glob
import json
from pathlib import Path

import run_retrieval_eval as rre
from run_phase6 import ANSWERABLE

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "corpus" / "processed"


def _corpus() -> tuple[set[str], set[str]]:
    """(doc_ids, chunk_ids) present in the processed corpus; empty if unbuilt."""
    doc_ids, chunk_ids = set(), set()
    for path in glob.glob(str(PROCESSED / "*.json")):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        chunks = data["chunks"] if isinstance(data, dict) else data
        for c in chunks:
            chunk_ids.add(c["chunk_id"])
            doc_ids.add(c["chunk_id"].split("::")[0])
    return doc_ids, chunk_ids


def test_every_expected_doc_id_exists_in_the_corpus():
    doc_ids, _ = _corpus()
    if not doc_ids:  # corpus not built in this environment
        return
    unknown = sorted(
        {d for _q, expected in ANSWERABLE for d in expected} - doc_ids
    )
    assert not unknown, f"eval expects doc_ids absent from the corpus: {unknown}"


def test_biological_diversity_act_is_accepted_for_questions_about_it():
    """The specific regression: a question that names the Act by title must accept
    the Act's own text as a correct source. Scoring the primary statute as a miss
    while accepting a guideline's secondhand summary of it is backwards."""
    for query, expected in ANSWERABLE:
        if "Biological Diversity Act" in query:
            assert "biological_diversity_act_2002" in expected, (
                f"question names the Biological Diversity Act but does not accept "
                f"the Act itself as a source: {query!r}"
            )


def test_retrieval_gold_and_phase6_questions_stay_in_sync():
    missing = [q for q, _ in ANSWERABLE if q not in rre.GOLD]
    assert not missing, f"questions with no passage-level GOLD entry: {missing}"


def test_every_gold_chunk_id_exists_in_the_corpus():
    _docs, chunk_ids = _corpus()
    if not chunk_ids:
        return
    unknown = sorted(
        {cid for gold in rre.GOLD.values() for cid in gold["chunks"]} - chunk_ids
    )
    assert not unknown, f"gold chunk_ids absent from the corpus: {unknown}"


def test_gold_docs_are_consistent_with_gold_chunks():
    """A passage-level gold whose document isn't in the same entry's doc set would
    make passage recall and document recall disagree about the same answer."""
    for query, gold in rre.GOLD.items():
        for cid in gold["chunks"]:
            doc = cid.split("::")[0]
            assert doc in gold["docs"], (
                f"gold chunk {cid} belongs to {doc}, which is missing from the "
                f"doc-level gold for {query!r}"
            )
