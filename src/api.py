"""FastAPI server for the web UI (PRD §7: "CLI first -> Streamlit/FastAPI once
the pipeline is proven").

The one interesting endpoint is /api/ask, which streams the pipeline's stages
as server-sent events instead of blocking until the whole answer is ready. On
a local model the pipeline takes 20-40s; streaming lets the UI show each
layer's decision — retrieval, the confidence gate's actual distance vs. its
threshold, per-claim verification verdicts — as they happen, which is both
better feedback and a more honest depiction of what the system is doing than
a spinner.

Run: .venv/Scripts/uvicorn.exe src.api:app  (or via .claude/launch.json)
"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_client  # noqa: E402
from authority import DOC_AUTHORITY  # noqa: E402
from generate import MAX_HISTORY_TURNS, answer_query_streaming  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="IP-SAKTI Sahayak")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _parse_history(raw: str) -> list[dict]:
    """Decode the `history` query param into the [{"q":.., "a":..}] shape
    generate.py expects, dropping anything malformed rather than erroring —
    a client-sent history is a convenience for follow-ups, never load-bearing
    (a bad or missing one just means the question is treated as standalone).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    turns = [
        {"q": t["q"], "a": t["a"]}
        for t in data
        if isinstance(t, dict) and isinstance(t.get("q"), str) and isinstance(t.get("a"), str)
    ]
    return turns[-MAX_HISTORY_TURNS:]


@app.get("/api/ask")
def ask(q: str, history: str = "[]"):
    """Stream pipeline events for a question as server-sent events.

    Declared `def` (not `async def`) on purpose: the pipeline is blocking
    (embedding lookups and local-LLM HTTP calls), so FastAPI runs it in a
    worker thread rather than stalling the event loop.

    `history` is the last few turns of the current conversation, JSON-encoded
    in the query string (EventSource only supports GET, so it can't ride in
    a request body) — used solely to resolve follow-up questions, see
    generate.answer_query_streaming.
    """
    turns = _parse_history(history)

    def event_stream():
        try:
            for event in answer_query_streaming(q, history=turns):
                yield _sse(event)
        except Exception as exc:  # surface failures to the UI instead of a dead stream
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/config")
def config():
    """What the UI's sidebar reads for its model badge and corpus count —
    both come from the pipeline's own source of truth (llm_client's active
    provider/model, and authority.py's document registry) rather than being
    hardcoded in the page, so neither can go stale as either one changes."""
    return {
        "model": llm_client.active_model_name(),
        "provider": llm_client.LLM_PROVIDER,
        "corpus_docs": len(DOC_AUTHORITY),
    }


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
