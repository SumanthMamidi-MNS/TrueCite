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

from generate import answer_query_streaming  # noqa: E402  (needs the path insert above)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="IP-SAKTI Sahayak")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/api/ask")
def ask(q: str):
    """Stream pipeline events for a question as server-sent events.

    Declared `def` (not `async def`) on purpose: the pipeline is blocking
    (embedding lookups and local-LLM HTTP calls), so FastAPI runs it in a
    worker thread rather than stalling the event loop.
    """

    def event_stream():
        try:
            for event in answer_query_streaming(q):
                yield _sse(event)
        except Exception as exc:  # surface failures to the UI instead of a dead stream
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
