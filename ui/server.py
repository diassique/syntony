"""L4 — spectator backend (FastAPI).

A domain-independent viewer over a Band room. It renders, side by side, what *each*
participating account sees in a room — which makes the mesh's privacy model visible:
a private event (a ``thought``) authored by one side appears in that side's column and
is absent from the other's.

The backend never writes to Band. It reads each account's own chat context with that
account's agent key, exposes it over ``GET /api/state`` and a live ``/ws`` WebSocket,
and serves the built React app (``web/dist``) when present. Two accounts are read from
the environment (``CLINIC_*`` / ``PAYER_*``); labels are presentation-only.

Run (binds to localhost; reach it over an SSH tunnel or a forwarded port):
    .venv/bin/python ui/server.py
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from band.client.rest import RestClient

# Run as a script (`python ui/server.py`) puts ui/ on sys.path, not the repo root —
# prepend the root so the local `control` package imports under systemd too.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control.api import router as auth_router, runs_router

load_dotenv()

REST_URL = os.environ.get("BAND_REST_URL", "https://app.band.ai")
DEFAULT_ROOM = os.environ.get("SYNTONY_VIEW_ROOM", "")
POLL_SECONDS = float(os.environ.get("SYNTONY_POLL_SECONDS", "2.0"))

# The two accounts to display: (label, env prefix). Presentation labels only.
SIDES = [
    (os.environ.get("LEFT_LABEL", "Clinic"), "CLINIC"),
    (os.environ.get("RIGHT_LABEL", "Payer"), "PAYER"),
]

_MENTION_TOKEN = re.compile(r"@\[\[[0-9a-f-]+\]\]\s*")
_DIST = Path(__file__).parent / "web" / "dist"

app = FastAPI(title="Syntony spectator")

# Control-plane API (auth + org-scoped run audit). Registered before the SPA catch-all mount.
app.include_router(auth_router)
app.include_router(runs_router)


def _client(prefix: str) -> RestClient | None:
    key = os.environ.get(f"{prefix}_AGENT_API_KEY", "").strip()
    return RestClient(api_key=key, base_url=REST_URL) if key else None


def _serialize(msg: Any) -> dict:
    """Reduce a Band ChatMessage to the fields the UI renders."""
    meta = getattr(msg, "metadata", None) or {}
    mentions = [m.get("name") or m.get("handle") for m in (meta.get("mentions") or [])]
    content = _MENTION_TOKEN.sub("", getattr(msg, "content", "") or "").strip()
    ts = getattr(msg, "inserted_at", None)
    return {
        "id": getattr(msg, "id", None),
        "type": getattr(msg, "message_type", "text"),
        "sender": getattr(msg, "sender_name", None) or getattr(msg, "sender_id", "?"),
        "content": content,
        "mentions": mentions,
        "ts": ts.isoformat() if ts else None,
    }


def _context(prefix: str, room_id: str) -> dict:
    client = _client(prefix)
    if client is None:
        return {"error": f"{prefix}_AGENT_API_KEY not set in .env"}
    try:
        resp = client.agent_api_context.get_agent_chat_context(chat_id=room_id)
        return {"items": [_serialize(m) for m in resp.data]}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


def build_state(room_id: str) -> dict:
    if not room_id:
        return {"room": "", "sides": []}
    sides = [{"label": label, "prefix": prefix, **_context(prefix, room_id)} for label, prefix in SIDES]
    return {"room": room_id, "sides": sides}


@app.get("/api/state")
def state(room: str = "") -> JSONResponse:
    return JSONResponse(build_state(room or DEFAULT_ROOM))


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    room_id = websocket.query_params.get("room") or DEFAULT_ROOM
    try:
        while True:
            payload = await asyncio.to_thread(build_state, room_id)
            await websocket.send_json(payload)
            await asyncio.sleep(POLL_SECONDS)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        await websocket.close()


# Serve the built React SPA at "/" when it exists; otherwise a hint. Mount LAST so the
# API/WS routes above take precedence.
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
else:
    @app.get("/")
    def _no_build() -> PlainTextResponse:
        return PlainTextResponse("Frontend not built yet. Run: cd ui/web && npm run build", status_code=503)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
