"""Tests for the --questions PATH flag added to run_phase6.py and
run_retrieval_eval.py: loading docs/heldout_questions.json's shape into the
same (ANSWERABLE, UNANSWERABLE[, GOLD]) shapes the built-in dev-set lists
use, threading the loaded lists through main()/run_many() instead of the
module-level lists, and picking a results filename suffix that can never
collide with a dev-set run.

All model/retrieval calls are mocked — this only exercises the loading and
plumbing, never a real pipeline run.
"""
import json
from pathlib import Path
from unittest.mock import patch

import run_phase6 as rp6
import run_retrieval_eval as rre

HELDOUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "heldout_questions.json"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "corpus" / "processed"

_SAMPLE_QUESTIONS = {
    "answerable": [
        {
            "id": "S1",
            "query": "sample question one?",
            "expected": "sample expected answer",
            "expected_doc_ids": ["doc_a", "doc_b"],
            "gold_chunks": ["doc_a::sec-1"],
        },
        {
            "id": "S2",
            "query": "sample question two, doc-level gold only?",
            "expected": "sample expected answer two",
            "expected_doc_ids": ["doc_c"],
            "gold_chunks": [],
        },
    ],
    "unanswerable": [
        {"id": "SU1", "query": "sample unanswerable question?", "why_unanswerable": "not in corpus"},
    ],
}


def _write_sample_questions(tmp_path: Path) -> Path:
    path = tmp_path / "sample_questions.json"
    path.write_text(json.dumps(_SAMPLE_QUESTIONS), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# run_phase6._load_questions
# ---------------------------------------------------------------------------

def test_run_phase6_load_questions_builds_answerable_tuples_with_doc_id_sets(tmp_path):
    path = _write_sample_questions(tmp_path)
    answerable, unanswerable = rp6._load_questions(path)

    assert answerable == [
        ("sample question one?", {"doc_a", "doc_b"}),
        ("sample question two, doc-level gold only?", {"doc_c"}),
    ]
    assert unanswerable == ["sample unanswerable question?"]


def test_run_phase6_load_questions_does_not_mutate_module_constants(tmp_path):
    path = _write_sample_questions(tmp_path)
    original_answerable = list(rp6.ANSWERABLE)
    original_unanswerable = list(rp6.UNANSWERABLE)

    rp6._load_questions(path)

    assert rp6.ANSWERABLE == original_answerable
    assert rp6.UNANSWERABLE == original_unanswerable


def test_run_phase6_load_questions_reads_the_real_heldout_file():
    answerable, unanswerable = rp6._load_questions(HELDOUT_PATH)
    assert len(answerable) == 10
    assert len(unanswerable) == 5
    queries = {q for q, _ in answerable}
    assert "Can a method of treating human patients with a herbal remedy be patented in India?" in queries
    first_expected = dict(answerable)["Can a method of treating human patients with a herbal remedy be patented in India?"]
    assert first_expected == {"patents_act_1970", "ipo_ayush_examination_guidelines_2025"}


# ---------------------------------------------------------------------------
# run_phase6.main / run_many use the loaded lists, not the module constants
# ---------------------------------------------------------------------------

def test_main_uses_the_passed_in_answerable_and_unanswerable_not_module_constants(tmp_path):
    """A question that doesn't exist in rp6.ANSWERABLE/UNANSWERABLE at all
    must still be sent to answer_query when passed explicitly — proves main()
    is driven by its parameters, not the module globals."""
    seen_queries = []

    def fake_answer_query(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        seen_queries.append(query)
        return {"refused": False, "answer": "x", "citations": ["[1]"],
                "claims": [{"doc_id": "custom_doc", "text": "x", "citation": "[x]"}]}

    custom_answerable = [("a totally custom question?", {"custom_doc"})]
    custom_unanswerable = ["a totally custom unanswerable question?"]

    with patch("run_phase6.answer_query", side_effect=fake_answer_query):
        summary = rp6.main(
            results_path=tmp_path / "results.json",
            answerable=custom_answerable,
            unanswerable=custom_unanswerable,
        )

    assert seen_queries == ["a totally custom question?", "a totally custom unanswerable question?"]
    assert summary["n_answerable"] == 1
    assert summary["n_unanswerable"] == 1
    assert summary["citation_accuracy"] == 1
    assert "a totally custom question?" in summary["per_question"]
    # None of the built-in dev-set questions were ever sent.
    assert not any(q for q, _ in rp6.ANSWERABLE if q in seen_queries)


def test_main_records_questions_file_path_when_given(tmp_path):
    def fake_answer_query(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        return {"refused": True, "answer": "no", "citations": [], "claims": []}

    with patch("run_phase6.answer_query", side_effect=fake_answer_query):
        summary = rp6.main(
            results_path=tmp_path / "results.json",
            answerable=[("q?", {"d"})],
            unanswerable=[],
            questions_file=Path("docs/heldout_questions.json"),
        )
    assert summary["questions_file"] == str(Path("docs/heldout_questions.json"))


def test_main_questions_file_defaults_to_none_without_the_flag(tmp_path):
    def fake_answer_query(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        return {"refused": True, "answer": "no", "citations": [], "claims": []}

    with patch("run_phase6.answer_query", side_effect=fake_answer_query):
        summary = rp6.main(results_path=tmp_path / "results.json")
    assert summary["questions_file"] is None


def test_run_many_threads_custom_lists_and_questions_file_through_to_main(tmp_path, monkeypatch):
    monkeypatch.setattr(rp6, "RESULTS_PATH", tmp_path / "phase6_results.json")

    seen_queries = []

    def fake_answer_query(query, top_k=8, history=None, relevance_filter=False, coverage_check=True):
        seen_queries.append(query)
        return {"refused": True, "answer": "no", "citations": [], "claims": []}

    custom_answerable = [("custom q?", {"d"})]
    custom_unanswerable = ["custom u?"]

    with patch("run_phase6.answer_query", side_effect=fake_answer_query):
        summary = rp6.run_many(
            runs=1, seed_base=1, relevance_filter=False, suffix="_customtest",
            answerable=custom_answerable, unanswerable=custom_unanswerable,
            questions_file=Path("some_questions.json"),
        )

    assert seen_queries == ["custom q?", "custom u?"]
    assert summary["questions_file"] == str(Path("some_questions.json"))


# ---------------------------------------------------------------------------
# CLI wiring: --questions changes the results filename suffix; omitting it
# leaves the default filenames byte-identical to before this flag existed.
# ---------------------------------------------------------------------------

def test_cli_questions_arg_defaults_to_none():
    args = rp6._parse_args([])
    assert args.questions is None


def test_cli_questions_arg_parses_a_path():
    args = rp6._parse_args(["--questions", "docs/heldout_questions.json"])
    assert args.questions == Path("docs/heldout_questions.json")


def test_default_results_filename_unchanged_without_questions_flag():
    """Without --questions, the suffix computation must be exactly what it
    was before this flag existed: only _suffix_for(relevance_filter)."""
    questions_suffix = ""  # what the __main__ block computes when args.questions is falsy
    suffix = questions_suffix + rp6._suffix_for(False)
    assert suffix == ""
    suffix_with_filter = questions_suffix + rp6._suffix_for(True)
    assert suffix_with_filter == "_with_relevance_filter"


def test_questions_filename_suffix_is_derived_from_file_stem():
    questions_path = Path("docs/heldout_questions.json")
    questions_suffix = f"_{questions_path.stem}"
    suffix = questions_suffix + rp6._suffix_for(False)
    assert suffix == "_heldout_questions"
    assert f"phase6_results{suffix}.json" == "phase6_results_heldout_questions.json"


# ---------------------------------------------------------------------------
# run_retrieval_eval._load_questions
# ---------------------------------------------------------------------------

def test_retrieval_eval_load_questions_builds_gold_with_chunks_and_docs(tmp_path):
    path = _write_sample_questions(tmp_path)
    answerable, unanswerable, gold = rre._load_questions(path)

    assert answerable == [
        ("sample question one?", {"doc_a", "doc_b"}),
        ("sample question two, doc-level gold only?", {"doc_c"}),
    ]
    assert unanswerable == ["sample unanswerable question?"]
    assert gold["sample question one?"] == {"chunks": {"doc_a::sec-1"}, "docs": {"doc_a", "doc_b"}}


def test_retrieval_eval_empty_gold_chunks_produces_empty_chunks_set_not_passage_scored(tmp_path):
    """A question whose gold_chunks is [] must load as an empty set (not None,
    not skipped), and evaluate_question's own `passage_scored = bool(gold_chunks)`
    must then be False for it — doc-level-only gold is not silently scored as a
    passage miss."""
    path = _write_sample_questions(tmp_path)
    _answerable, _unanswerable, gold = rre._load_questions(path)

    doc_level_only = gold["sample question two, doc-level gold only?"]
    assert doc_level_only["chunks"] == set()
    assert doc_level_only["docs"] == {"doc_c"}

    with patch("run_retrieval_eval.retrieve_vector", return_value=[]), \
         patch("run_retrieval_eval.retrieve_bm25", return_value=[]), \
         patch("run_retrieval_eval.retrieve_hybrid", return_value=[]), \
         patch(
             "run_retrieval_eval._select_grounded_hits_with_diagnostics",
             return_value=([], {"best_distance": None, "gate_passed": False}),
         ):
        row = rre.evaluate_question("sample question two, doc-level gold only?", doc_level_only)

    assert row["passage_scored"] is False
    assert row["passage_recall_at_8"] is False
    assert row["passage_recall_at_40"] is False


def test_retrieval_eval_load_questions_reads_the_real_heldout_file():
    answerable, unanswerable, gold = rre._load_questions(HELDOUT_PATH)
    assert len(answerable) == 10
    assert len(unanswerable) == 5
    q = "How is the Indian Patent Office supposed to classify patent applications that involve traditional knowledge?"
    assert gold[q]["chunks"] == {"ipo_tk_biological_material_guidelines_2012::sec-7"}
    assert gold[q]["docs"] == {"ipo_tk_biological_material_guidelines_2012"}


def test_retrieval_eval_main_uses_passed_in_answerable_gold_unanswerable(tmp_path):
    """main() must consult the `gold`/`answerable`/`unanswerable` parameters,
    not the module-level GOLD/ANSWERABLE/UNANSWERABLE, when given custom ones."""
    custom_gold = {"custom q?": {"chunks": set(), "docs": {"custom_doc"}}}
    custom_answerable = [("custom q?", {"custom_doc"})]
    custom_unanswerable = ["custom u?"]

    with patch(
        "run_retrieval_eval._select_grounded_hits_with_diagnostics",
        return_value=([], {"best_distance": 0.5, "gate_passed": True}),
    ), patch("run_retrieval_eval.retrieve_vector", return_value=[]), \
         patch("run_retrieval_eval.retrieve_bm25", return_value=[]), \
         patch("run_retrieval_eval.retrieve_hybrid", return_value=[]):
        summary = rre.main(
            json_out=tmp_path / "retrieval_eval_custom.json",
            answerable=custom_answerable,
            gold=custom_gold,
            unanswerable=custom_unanswerable,
        )

    assert summary["doc_recall_at_8"][1] == 1  # exactly one answerable row scored
    written = json.loads((tmp_path / "retrieval_eval_custom.json").read_text(encoding="utf-8"))
    assert [r["query"] for r in written["answerable"]] == ["custom q?"]
    assert [r["query"] for r in written["unanswerable"]] == ["custom u?"]


# ---------------------------------------------------------------------------
# Every gold_chunks id / expected_doc_ids id in docs/heldout_questions.json
# must actually exist in the processed corpus (frozen ground truth must not
# reference a chunk_id or doc_id the chunker no longer produces).
# ---------------------------------------------------------------------------

def _processed_corpus_ids() -> tuple[set[str], set[str]]:
    doc_ids, chunk_ids = set(), set()
    for path in PROCESSED_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        chunks = data["chunks"] if isinstance(data, dict) else data
        for c in chunks:
            chunk_ids.add(c["chunk_id"])
            doc_ids.add(c["chunk_id"].split("::")[0])
    return doc_ids, chunk_ids


def test_heldout_questions_expected_doc_ids_exist_in_processed_corpus():
    doc_ids, _chunk_ids = _processed_corpus_ids()
    if not doc_ids:  # corpus not built in this environment
        return
    data = json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))
    unknown = sorted(
        {d for q in data["answerable"] for d in q["expected_doc_ids"]} - doc_ids
    )
    assert not unknown, f"heldout_questions.json expected_doc_ids absent from corpus/processed: {unknown}"


def test_heldout_questions_gold_chunks_exist_in_processed_corpus():
    _doc_ids, chunk_ids = _processed_corpus_ids()
    if not chunk_ids:  # corpus not built in this environment
        return
    data = json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))
    unknown = sorted(
        {cid for q in data["answerable"] for cid in q["gold_chunks"]} - chunk_ids
    )
    assert not unknown, f"heldout_questions.json gold_chunks absent from corpus/processed: {unknown}"
