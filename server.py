"""
FastAPI chat server — Phase 2 entry point.

Endpoints:
  GET  /           → serve chat UI (static/index.html)
  POST /chat       → SSE stream: agent events as JSON lines
  GET  /health     → liveness check
  DELETE /history/{session_id} → clear a session's conversation history

Run:
  venv\\Scripts\\python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from agent.agent import chat_stream, clear_history
from config import WEB_HOST, WEB_PORT

app = FastAPI(title="GO Transit Chat Agent", version="2.0")

_STATIC = Path(__file__).parent / "static" / "index.html"


# ── Request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return _STATIC.read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    SSE stream. Each event is:
      data: {"type": "status"|"answer"|"error", "text": "..."}

    The stream ends with:
      data: [DONE]
    """
    async def generate():
        async for event in chat_stream(req.message, req.session_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/history/{session_id}")
async def clear_history_endpoint(session_id: str):
    """Delete the saved conversation history for a session."""
    if clear_history(session_id):
        return {"cleared": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host=WEB_HOST, port=WEB_PORT, reload=True)
