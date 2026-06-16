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
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from band.client.rest import RestClient

# Run as a script (`python ui/server.py`) puts ui/ on sys.path, not the repo root —
# prepend the root so the local `control` package imports under systemd too.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control.api import current_org_id, current_user, router as auth_router, runs_router

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


@app.get("/api/agents")
def list_agents(_user=Depends(current_user)) -> JSONResponse:
    """The agent roster (the mesh cast): each role's side, framework, model and the protocol
    states it acts in. Static domain data — what the console's Agents view renders."""
    from domains.authbridge.roles import ROLES

    roster = [
        {
            "id": s.id,
            "name": s.display_name,
            "side": s.side.value,
            "framework": s.framework.value,
            "model": s.model,
            "acts_in": [st.value for st in s.acts_in],
            "human": s.is_human,
        }
        for s in ROLES.values()
    ]
    return JSONResponse({"agents": roster})


# ---- live "Run a case" -----------------------------------------------------------
# Trigger a real cross-org negotiation from the console and stream it into the org's audit
# trail. This lives in the composition root (it wires the domain + Band + control plane),
# not the control-plane API, which knows nothing about domains.
_MAX_CONCURRENT_LIVE = 3
_live_inflight: set[str] = set()


class StartRunIn(BaseModel):
    case_name: str | None = None


@app.post("/api/runs/start", status_code=202)
async def start_live_run(
    body: StartRunIn | None = None,
    org_id: str = Depends(current_org_id),
) -> JSONResponse:
    """Kick off a live negotiation in the background; return its run id at once so the
    console can open the Case Theater and poll it as each turn lands."""
    from control import seed
    from control.db import session as open_session
    import live_run

    with open_session() as sess:
        demo_orgs = set(seed.demo_side_orgs(sess).values())
    if org_id not in demo_orgs:
        raise HTTPException(403, "live demo runs are available to the demo organizations")
    if len(_live_inflight) >= _MAX_CONCURRENT_LIVE:
        raise HTTPException(429, "too many live runs in progress — try again shortly")

    case_name = ((body.case_name if body else None) or live_run.DEFAULT_CASE).strip()
    try:
        run_id = live_run.open_live_run(case_name)
    except KeyError as e:
        raise HTTPException(400, str(e))

    _live_inflight.add(run_id)

    async def _go() -> None:
        try:
            await live_run.execute_live_run(run_id, case_name)
        finally:
            _live_inflight.discard(run_id)

    asyncio.create_task(_go())
    return JSONResponse({"run_id": run_id, "case_name": case_name, "status": "running"}, status_code=202)


class IntakeIn(BaseModel):
    image: str | None = None         # data URI (png/jpg, base64) — vision path
    document_url: str | None = None  # public PDF/image URL — OCR path
    sample: bool = False             # use a built-in synthetic form (vision path)


@app.post("/api/runs/intake", status_code=202)
async def intake_run(body: IntakeIn | None = None, org_id: str = Depends(current_org_id)) -> JSONResponse:
    """The flagship AI/ML use-case: read an uploaded clinical document (vision or OCR), extract a
    structured prior-auth request, and kick off the live negotiation from it."""
    from control import seed
    from control.db import session as open_session
    from domains.authbridge import intake
    import live_run

    with open_session() as sess:
        demo_orgs = set(seed.demo_side_orgs(sess).values())
    if org_id not in demo_orgs:
        raise HTTPException(403, "live demo runs are available to the demo organizations")
    if len(_live_inflight) >= _MAX_CONCURRENT_LIVE:
        raise HTTPException(429, "too many live runs in progress — try again shortly")

    body = body or IntakeIn()
    try:
        if body.sample:
            req = await asyncio.to_thread(intake.extract_request_from_image, intake.sample_document_data_uri())
        elif body.image:
            req = await asyncio.to_thread(intake.extract_request_from_image, body.image)
        elif body.document_url:
            req = await asyncio.to_thread(intake.extract_request_from_pdf, body.document_url)
        else:
            raise HTTPException(400, "provide an image, a document_url, or sample=true")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"document extraction failed: {type(e).__name__}: {str(e)[:120]}")

    run_id = live_run.open_document_run(req)
    _live_inflight.add(run_id)

    async def _go() -> None:
        try:
            await live_run.execute_live_run(run_id, "document_intake", request=req)
        finally:
            _live_inflight.discard(run_id)

    asyncio.create_task(_go())
    extracted = {
        "procedure": req.procedure.display,
        "code": f"{req.procedure.system} {req.procedure.code}".strip(),
        "diagnoses": [d.code for d in req.diagnoses],
        "urgent": req.urgency.value == "urgent",
    }
    return JSONResponse({"run_id": run_id, "status": "running", "extracted": extracted}, status_code=202)


class DecisionIn(BaseModel):
    outcome: str  # "APPROVE" | "DENY"


@app.post("/api/runs/{run_id}/decide")
async def decide_run(run_id: str, body: DecisionIn, org_id: str = Depends(current_org_id)) -> JSONResponse:
    """Human-in-the-loop: the payer-side Medical Director approves or denies a borderline case
    that paused for review, and the negotiation completes with that verdict."""
    from control import seed
    from control.db import session as open_session
    import live_run

    with open_session() as sess:
        payer_org = seed.demo_side_orgs(sess).get("payer")
    if not payer_org or org_id != payer_org:
        raise HTTPException(403, "only the payer's Medical Director can decide this case")

    try:
        outcome = await asyncio.to_thread(live_run.apply_human_decision, run_id, body.outcome)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return JSONResponse({"run_id": run_id, "outcome": outcome, "status": "succeeded"})


# ---- interactive PA workflow (the real two-sided, form-driven flow) --------------
# These are org-scoped via the auth dependency (NOT demo-gated). A provider org submits a
# request; the payer org acts from its worklist; each side sees only its own audit view.

def _run_sides(run: Any) -> dict:
    return (run.workflow or {}).get("side_to_org", {})


def _side_of(run: Any, org_id: str) -> str | None:
    for side, oid in _run_sides(run).items():
        if oid == org_id:
            return side
    return None


def _pa_actions(run: Any, side: str | None) -> list[str]:
    """Which actions this side may take now (drives the console's buttons)."""
    s = run.status
    fsm = (run.workflow or {}).get("fsm_state")
    if side == "payer":
        if s == "awaiting_payer":
            return ["review"]
        if s == "awaiting_payer_decision":
            return ["decide"]
        if s == "awaiting_human":
            return ["md_decide"]
    if side == "provider" and s == "awaiting_provider":
        return ["respond"] if fsm == "INFO" else ["appeal", "accept"]
    return []


def _pa_summary(run: Any, side: str | None) -> dict:
    from domains.authbridge import workflow as wf
    req = (run.workflow or {}).get("state", {}).get("req", {})
    proc = req.get("procedure", {})
    return {
        "run_id": run.id,
        "status": run.status,
        "mode": run.mode,
        "side": side,
        "case": f"{proc.get('system', '')} {proc.get('code', '')} — {proc.get('display', '')}".strip(" —"),
        "patient_ref": req.get("patient_ref", ""),
        "urgency": run.urgency,
        "outcome": run.outcome,
        "turns": run.turns,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "sla_deadline": wf.sla_deadline(run.started_at, run.urgency).isoformat() if run.started_at else None,
        "actions": _pa_actions(run, side),
    }


def _pa_detail(sess: Any, run: Any, org_id: str, side: str | None) -> dict:
    from sqlmodel import select
    from control.models import Event
    state = (run.workflow or {}).get("state", {})
    rows = sess.exec(
        select(Event).where(Event.run_id == run.id, Event.org_id == org_id)
        .order_by(Event.turn, Event.created_at)
    ).all()
    timeline = [{
        "turn": e.turn, "author": e.author, "kind": e.kind, "visibility": e.visibility,
        "message": (e.payload or {}).get("message", ""),
        "reasoning": (e.payload or {}).get("reasoning", ""),
        "pa_event": (e.payload or {}).get("pa_event"),
        "outcome": (e.payload or {}).get("outcome"),
        "denial_reason": (e.payload or {}).get("denial_reason"),
        "auth_number": (e.payload or {}).get("auth_number"),
        "overturned": (e.payload or {}).get("overturned"),
        "hitl": (e.payload or {}).get("hitl"),
        "via": (e.payload or {}).get("via"),
        "framework": (e.payload or {}).get("framework"),
    } for e in rows]
    detail = {
        **_pa_summary(run, side),
        "fsm_state": (run.workflow or {}).get("fsm_state"),
        "request": state.get("req", {}),
        "auth_number": state.get("auth_number", ""),
        "timeline": timeline,
    }
    if side == "payer":  # the payer's internal UM recommendation is payer-only
        detail["recommendation"] = state.get("recommendation", {})
    return detail


class PrecheckIn(BaseModel):
    form: dict


@app.post("/api/pa/options")
@app.get("/api/pa/options")
def pa_options(_user=Depends(current_user)) -> JSONResponse:
    """Form catalogs: supporting-doc types, known procedures, denial-reason enum."""
    from domains.authbridge import workflow as wf
    return JSONResponse(wf.doc_options())


@app.post("/api/pa/precheck")
def pa_precheck(body: PrecheckIn, _user=Depends(current_user)) -> JSONResponse:
    """Provider Counsel's live pre-submit check — flags gaps before the request is filed."""
    from domains.authbridge import workflow as wf
    try:
        req = wf.build_request(body.form)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return JSONResponse(wf.precheck(req))


class SubmitIn(BaseModel):
    form: dict


@app.post("/api/pa/submit", status_code=202)
async def pa_submit(body: SubmitIn, org_id: str = Depends(current_org_id)) -> JSONResponse:
    """Provider files the PA request → opens the interactive run and parks it in the payer worklist."""
    import pa_workflow
    from domains.authbridge import workflow as wf
    try:
        req = wf.build_request(body.form)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    report = wf.precheck(req)
    if not report["ready"]:
        raise HTTPException(400, {"message": "request is not ready to submit", "precheck": report})
    try:
        res = await pa_workflow.submit_request(body.form, submitter_org=org_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    return JSONResponse(res, status_code=202)


@app.get("/api/pa/worklist")
def pa_worklist(org_id: str = Depends(current_org_id)) -> JSONResponse:
    """The org's interactive cases (provider: my submissions; payer: my review queue)."""
    from sqlmodel import select
    from control.db import session as open_session
    from control.models import Event, Run, RunMode
    with open_session() as sess:
        run_ids = {rid for rid in sess.exec(select(Event.run_id).where(Event.org_id == org_id)).all()}
        if not run_ids:
            return JSONResponse({"items": []})
        runs = sess.exec(
            select(Run).where(Run.id.in_(run_ids), Run.mode == RunMode.INTERACTIVE.value)
            .order_by(Run.started_at.desc())
        ).all()
        items = [_pa_summary(r, _side_of(r, org_id)) for r in runs]
    return JSONResponse({"items": items})


@app.get("/api/pa/{run_id}")
def pa_get(run_id: str, org_id: str = Depends(current_org_id)) -> JSONResponse:
    from control.db import session as open_session
    from control.models import Run
    with open_session() as sess:
        run = sess.get(Run, run_id)
        side = _side_of(run, org_id) if run else None
        if run is None or side is None:
            raise HTTPException(404, "case not found")
        return JSONResponse(_pa_detail(sess, run, org_id, side))


class DecideIn(BaseModel):
    action: str                      # APPROVE | DENY | REQUEST_INFO | ESCALATE
    reason_code: str | None = None
    note: str = ""


class DocsIn(BaseModel):
    docs: list[str] = []


class MdDecideIn(BaseModel):
    outcome: str                     # APPROVE | DENY
    note: str = ""


def _require_side(run: Any, org_id: str, want: str) -> None:
    if _side_of(run, org_id) != want:
        raise HTTPException(403, f"only the {want} on this case may take this action")


async def _load_run_for(org_id: str, run_id: str):
    from control.db import session as open_session
    from control.models import Run
    with open_session() as sess:
        run = sess.get(Run, run_id)
        side = _side_of(run, org_id) if run else None
    if run is None or side is None:
        raise HTTPException(404, "case not found")
    return run, side


@app.post("/api/pa/{run_id}/review", status_code=202)
async def pa_review(run_id: str, org_id: str = Depends(current_org_id)) -> JSONResponse:
    import pa_workflow
    run, _ = await _load_run_for(org_id, run_id)
    _require_side(run, org_id, "payer")
    try:
        return JSONResponse(await pa_workflow.start_review(run_id), status_code=202)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pa/{run_id}/decide", status_code=202)
async def pa_decide(run_id: str, body: DecideIn, org_id: str = Depends(current_org_id)) -> JSONResponse:
    import pa_workflow
    run, _ = await _load_run_for(org_id, run_id)
    _require_side(run, org_id, "payer")
    try:
        return JSONResponse(await pa_workflow.decide(
            run_id, action=body.action, reason_code=body.reason_code, note=body.note), status_code=202)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pa/{run_id}/respond", status_code=202)
async def pa_respond(run_id: str, body: DocsIn, org_id: str = Depends(current_org_id)) -> JSONResponse:
    import pa_workflow
    run, _ = await _load_run_for(org_id, run_id)
    _require_side(run, org_id, "provider")
    try:
        return JSONResponse(await pa_workflow.respond_to_pend(run_id, docs=body.docs), status_code=202)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pa/{run_id}/appeal", status_code=202)
async def pa_appeal(run_id: str, body: DocsIn, org_id: str = Depends(current_org_id)) -> JSONResponse:
    import pa_workflow
    run, _ = await _load_run_for(org_id, run_id)
    _require_side(run, org_id, "provider")
    try:
        return JSONResponse(await pa_workflow.file_appeal(run_id, docs=body.docs), status_code=202)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pa/{run_id}/accept")
async def pa_accept(run_id: str, org_id: str = Depends(current_org_id)) -> JSONResponse:
    import pa_workflow
    run, _ = await _load_run_for(org_id, run_id)
    _require_side(run, org_id, "provider")
    try:
        return JSONResponse(await pa_workflow.accept_denial(run_id))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pa/{run_id}/md-decide")
async def pa_md_decide(run_id: str, body: MdDecideIn, org_id: str = Depends(current_org_id)) -> JSONResponse:
    import pa_workflow
    run, _ = await _load_run_for(org_id, run_id)
    _require_side(run, org_id, "payer")
    try:
        return JSONResponse(await pa_workflow.md_decide(run_id, outcome=body.outcome, note=body.note))
    except ValueError as e:
        raise HTTPException(409, str(e))


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
