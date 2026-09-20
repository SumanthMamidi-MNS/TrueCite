"""Data handling, audit trail and retention (problem statement: "privacy,
audit and security aligned to the Digital Personal Data Protection regime").

Scoped honestly to what this system actually is. TrueCite has no accounts, no
login, no server-side user records and no database of people: the only
personal data it can receive is whatever a user chooses to type into a
question. Building session management, consent flows and a retention scheduler
around that would be security theatre — it would add attack surface and
maintenance burden while protecting nothing that exists.

What IS worth doing, and is done here:

1. An audit trail of pipeline DECISIONS, not question content. What a
   verification tool needs to be able to prove afterwards is "why did it
   answer that, and what did it refuse" — which is about distances,
   thresholds, verdicts and citations, none of which require retaining the
   question.
2. Naming the one real exposure honestly (see QUERY_STRING_EXPOSURE below)
   rather than claiming a privacy posture the transport does not support.
3. A retention statement a user can act on, given the data genuinely lives in
   their own browser.
"""
import time
from dataclasses import asdict, dataclass, field

# The real, un-fixable-here exposure. Server-sent events are an EventSource
# API, and EventSource supports only GET, so the question travels in the URL
# query string. Anything that logs URLs therefore logs the question: uvicorn's
# default access log does, and so would any reverse proxy in front of it.
#
# This is stated rather than quietly accepted because a tool whose entire
# premise is honesty about its own limits cannot claim a privacy posture its
# transport does not support. It is also why the audit trail below does not
# store question text: doing so would be the one place this codebase ADDS a
# copy of something a user might reasonably expect to be transient.
QUERY_STRING_EXPOSURE = (
    "Questions are sent in the URL query string, because server-sent events "
    "require GET. Any component that logs request URLs — the development "
    "server's own access log, or a reverse proxy — will therefore record the "
    "question text. Treat server logs as containing user questions, and do not "
    "deploy this behind logging infrastructure you do not control without "
    "either disabling URL logging or moving the pipeline to POST."
)

DATA_INVENTORY = [
    {
        "data": "Question text",
        "where": "Browser memory during a request; the URL query string in transit",
        "server_persistence": "None. Not written to any file or database by this application.",
        "note": "Appears in server access logs — see QUERY_STRING_EXPOSURE.",
    },
    {
        "data": "Conversation history (questions and answers)",
        "where": "The user's own browser, in localStorage, capped at 40 conversations",
        "server_persistence": "None. Never transmitted except as context on a follow-up question.",
        "note": "Cleared by the user at any time; see RETENTION.",
    },
    {
        "data": "Jurisdiction preference",
        "where": "The user's own browser, in localStorage",
        "server_persistence": "None.",
        "note": "A single word ('india' / 'international'); not personal data.",
    },
    {
        "data": "Pipeline decision audit records",
        "where": "In-process, in memory, for the life of the server process",
        "server_persistence": "None by default — not written to disk.",
        "note": "Deliberately excludes question and answer text; see AuditRecord.",
    },
]

RETENTION = (
    "This application stores nothing server-side. Conversation history lives in "
    "the browser's localStorage and is deleted when the user clears it or their "
    "browser data. No copy exists elsewhere for an operator to delete on request, "
    "which is a deliberate design property rather than an omission."
)


@dataclass
class AuditRecord:
    """One pipeline run, recorded by what it DECIDED rather than what was said.

    Question and answer text are deliberately absent. The auditable questions
    for a citation-verification tool are "did the gate pass, what did Layer 2
    reject, what was finally cited" — all answerable without retaining
    content, and retaining content would make this the one component that
    creates a durable copy of it.
    """
    at: float = field(default_factory=time.time)
    jurisdiction: str | None = None
    gate_passed: bool = False
    best_distance: float | None = None
    candidates_examined: int = 0
    claims_drafted: int = 0
    claims_rejected: int = 0
    cited_doc_ids: list[str] = field(default_factory=list)
    refused_at: str | None = None
    confidence: str | None = None
    escalated: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


class AuditTrail:
    """A bounded in-memory trail. Bounded because an unbounded one is a slow
    memory leak on a long-running server, and because the recent decisions are
    the ones anyone actually inspects."""

    def __init__(self, limit: int = 200):
        self.limit = limit
        self._records: list[AuditRecord] = []

    def record(self, rec: AuditRecord) -> AuditRecord:
        self._records.append(rec)
        if len(self._records) > self.limit:
            del self._records[: len(self._records) - self.limit]
        return rec

    def recent(self, n: int = 20) -> list[dict]:
        return [r.as_dict() for r in self._records[-n:]]

    def clear(self) -> int:
        n = len(self._records)
        self._records.clear()
        return n

    def __len__(self) -> int:
        return len(self._records)


AUDIT = AuditTrail()
