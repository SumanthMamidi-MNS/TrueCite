from dataclasses import fields

from privacy import (
    DATA_INVENTORY,
    QUERY_STRING_EXPOSURE,
    RETENTION,
    AuditRecord,
    AuditTrail,
)


def test_audit_record_never_carries_question_or_answer_text():
    # The point of the audit trail is to make DECISIONS reviewable without
    # this component becoming the one place a durable copy of user content
    # exists. A field named for content is a regression, not a feature.
    names = {f.name for f in fields(AuditRecord)}
    for forbidden in ("question", "query", "answer", "text", "claims_text", "prompt"):
        assert forbidden not in names, f"AuditRecord must not store {forbidden!r}"


def test_audit_record_captures_what_actually_needs_auditing():
    names = {f.name for f in fields(AuditRecord)}
    for required in ("gate_passed", "best_distance", "claims_rejected",
                     "cited_doc_ids", "refused_at", "confidence", "escalated"):
        assert required in names


def test_trail_is_bounded_so_a_long_running_server_does_not_leak():
    trail = AuditTrail(limit=5)
    for _ in range(20):
        trail.record(AuditRecord())
    assert len(trail) == 5


def test_trail_keeps_the_most_recent_records():
    trail = AuditTrail(limit=3)
    for i in range(6):
        trail.record(AuditRecord(candidates_examined=i))
    assert [r["candidates_examined"] for r in trail.recent(3)] == [3, 4, 5]


def test_clear_reports_how_many_it_removed():
    trail = AuditTrail()
    for _ in range(4):
        trail.record(AuditRecord())
    assert trail.clear() == 4
    assert len(trail) == 0


def test_query_string_exposure_is_stated_not_glossed():
    # A tool whose premise is honesty about its limits cannot claim a privacy
    # posture its transport does not support.
    assert "query string" in QUERY_STRING_EXPOSURE
    assert "access log" in QUERY_STRING_EXPOSURE or "logs" in QUERY_STRING_EXPOSURE
    assert "POST" in QUERY_STRING_EXPOSURE, "should name the actual remedy"


def test_data_inventory_covers_every_store_and_states_server_persistence():
    assert len(DATA_INVENTORY) >= 4
    for entry in DATA_INVENTORY:
        assert entry["data"] and entry["where"] and entry["server_persistence"]


def test_inventory_does_not_claim_server_side_storage_that_does_not_exist():
    for entry in DATA_INVENTORY:
        assert "None" in entry["server_persistence"]


def test_retention_is_honest_about_there_being_nothing_to_delete_serverside():
    assert "localStorage" in RETENTION or "browser" in RETENTION
    assert "nothing server-side" in RETENTION or "stores nothing" in RETENTION
