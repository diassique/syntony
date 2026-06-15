"""Live negotiation launcher for the in-product "Run a case" button.

Where ``run_all.py`` is the CLI launcher (run a case, then persist the whole transcript),
this is the server-side path: it creates the audit ``Run`` up front (so the console can open
its Case Theater immediately) and then **streams** each turn into the org-scoped audit trail
as the negotiation unfolds, so a logged-in org watches the cross-org exchange appear live.

The Band mesh is used for real when its two agent keys are present; if Band is unreachable
the negotiation still runs and streams to the audit trail (degraded, never broken — the live
theater must not depend on an external service being up at click time).

Two entry points:
- ``open_live_run(case_name)`` — synchronous; seed + create the RUNNING ``Run``; returns its id.
- ``execute_live_run(run_id, case_name)`` — async; run the negotiation, streaming per turn,
  then finish the run. Always finishes the run (SUCCEEDED/FAILED) so the console stops polling.
"""

from __future__ import annotations

import asyncio
import os

from control import ingest, seed, service
from control.db import session as open_session
from control.models import Run, RunStatus
from domains.authbridge.cases import ALL_CASES
from domains.authbridge.roles import ROLES
from domains.authbridge.runner import llm_narrator, run_authbridge
from domains.authbridge.schema import Urgency
from engine.agent_base import Side
from protocol import Envelope, Kind, State, Visibility

#: Default demo scenario: the deny→appeal→overturn golden case.
DEFAULT_CASE = "humira_step_therapy_denied"


def _author_side(author: str) -> str:
    spec = ROLES.get(author)
    return spec.side.value if spec else "neutral"


def open_live_run(case_name: str) -> str:
    """Seed the demo orgs and create a RUNNING audit ``Run``; return its id.

    Raises ``KeyError`` for an unknown case (the caller should reject before scheduling work).
    """
    if case_name not in ALL_CASES:
        raise KeyError(f"unknown case {case_name!r}; have {sorted(ALL_CASES)}")
    urgency = "expedited" if ALL_CASES[case_name]().urgency is Urgency.URGENT else "standard"
    with open_session() as sess:
        seed.seed_demo(sess)  # idempotent
        side_to_org = seed.demo_side_orgs(sess)
        org_ids = list(dict.fromkeys(side_to_org.values()))
        if not org_ids:
            raise RuntimeError("demo orgs not seeded — cannot attribute the run")
        run = service.start_run(sess, org_id=org_ids[0], case_name=case_name)
        run.urgency = urgency
        sess.add(run)
        sess.commit()
        sess.refresh(run)
        return run.id


def _build_tools_for(case_id: str):
    """Best-effort Band transport router (provider→clinic account, payer→payer account).

    Returns ``(tools_for, room_id)`` or ``(None, None)`` if Band can't be wired (missing keys
    or unreachable) — the negotiation then runs without posting to Band but still streams to
    the audit trail.
    """
    try:
        from engine.band_room import RestRoomTools, agent_client, ensure_room

        rest_url = os.environ.get("BAND_REST_URL", "https://app.band.ai")
        clinic_id = os.environ["CLINIC_AGENT_ID"]
        payer_id = os.environ["PAYER_AGENT_ID"]
        clinic = agent_client(os.environ["CLINIC_AGENT_API_KEY"], rest_url)
        payer = agent_client(os.environ["PAYER_AGENT_API_KEY"], rest_url)
        room = ensure_room(clinic, payer_id, room_id=None)  # a fresh room per live run

        mention_map = {rid: (payer_id if spec.side is Side.PAYER else clinic_id)
                       for rid, spec in ROLES.items()}
        clinic_tools = RestRoomTools(clinic, room, mention_map=mention_map,
                                     self_id=clinic_id, default_mention=payer_id)
        payer_tools = RestRoomTools(payer, room, mention_map=mention_map,
                                    self_id=payer_id, default_mention=clinic_id)

        def tools_for(env: Envelope):
            spec = ROLES.get(env.author)
            return payer_tools if (spec and spec.side is Side.PAYER) else clinic_tools

        return tools_for, room
    except Exception as e:  # noqa: BLE001 — Band is optional for the live theater
        print(f"live_run: Band transport unavailable ({type(e).__name__}: {str(e)[:120]}) — streaming to audit only")
        return None, None


def open_document_run(req, label: str = "document_intake") -> str:
    """Create a RUNNING audit run for a request extracted from a document (not a named case)."""
    urgency = "expedited" if req.urgency is Urgency.URGENT else "standard"
    with open_session() as sess:
        seed.seed_demo(sess)
        side_to_org = seed.demo_side_orgs(sess)
        org_ids = list(dict.fromkeys(side_to_org.values()))
        if not org_ids:
            raise RuntimeError("demo orgs not seeded — cannot attribute the run")
        run = service.start_run(sess, org_id=org_ids[0], case_name=label)
        run.urgency = urgency
        sess.add(run)
        sess.commit()
        sess.refresh(run)
        return run.id


async def execute_live_run(run_id: str, case_name: str, *, request=None, full: bool = False) -> None:
    """Run the negotiation, streaming each turn into the audit trail, then finish the run.

    Pass ``request`` to run a document-extracted PriorAuthRequest instead of a named case."""
    with open_session() as sess:
        side_to_org = seed.demo_side_orgs(sess)
    org_ids = list(dict.fromkeys(side_to_org.values()))

    def on_turn(env: Envelope, _state) -> None:
        with open_session() as sess:
            run = sess.get(Run, run_id)
            if run is not None:
                ingest.record_envelope(sess, run=run, env=env, org_ids=org_ids,
                                       side_to_org=side_to_org, author_side=_author_side)

    # RAG (best-effort): retrieve the governing medical-necessity criterion via embeddings so the
    # Guidelines agent cites real policy text. Off-loaded (network I/O); failure → generic line.
    criteria = ""
    try:
        from domains.authbridge.criteria import retrieve
        src = request if request is not None else ALL_CASES[case_name]()
        query = f"{src.procedure.display} (code {src.procedure.code}); diagnoses {[d.code for d in src.diagnoses]}"
        hits = await asyncio.to_thread(retrieve, query, 1)
        criteria = hits[0][1] if hits else ""
    except Exception as e:  # noqa: BLE001 — retrieval is optional
        print(f"live_run: criteria retrieval skipped ({type(e).__name__}: {str(e)[:100]})")

    tools_for, room_id = _build_tools_for(f"live-{case_name}")
    paused = False
    try:
        res = await run_authbridge(
            case_name, tools_for=tools_for, narrate=llm_narrator(debug=not full),
            case_id=f"live-{case_name}", on_turn=on_turn, request=request, criteria=criteria,
            pause_states={State.ARBITER},  # a borderline case pauses for the human Medical Director
        )
        paused = res.stopped == "paused"
        final_state = res.final_state.value if hasattr(res.final_state, "value") else str(res.final_state)
        outcome = next((e.payload.get("outcome") for e in reversed(res.history) if e.payload.get("outcome")), None)
        turns = res.turns
        status = (RunStatus.AWAITING_HUMAN.value if paused
                  else RunStatus.SUCCEEDED.value if res.stopped == "terminal"
                  else RunStatus.FAILED.value)
    except Exception as e:  # noqa: BLE001 — always settle the run so the console stops polling
        print(f"live_run: negotiation failed ({type(e).__name__}: {str(e)[:160]})")
        status, final_state, outcome, turns = RunStatus.FAILED.value, None, None, 0

    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            return
        run.room_id = room_id or run.room_id
        if paused:
            # leave the run open (no ended_at) awaiting the human decision; meter on completion.
            run.status = status
            run.final_state = final_state
            run.turns = turns
            sess.add(run)
            sess.commit()
            return
        for org_id in org_ids:
            service.record_usage(sess, org_id=org_id, run_id=run_id, kind="run", units=1)
        service.finish_run(sess, run=run, status=status, final_state=final_state,
                           turns=turns, outcome=outcome)


def apply_human_decision(run_id: str, outcome: str) -> str:
    """Resolve a paused (AWAITING_HUMAN) run with the human Medical Director's verdict: append
    the decision to the audit trail and complete the run. ``outcome`` is "APPROVE" or "DENY".
    Returns a short status string. Raises ValueError if the run isn't awaiting a decision."""
    outcome = outcome.upper()
    if outcome not in ("APPROVE", "DENY"):
        raise ValueError(f"outcome must be APPROVE or DENY, got {outcome!r}")

    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        if run.status != RunStatus.AWAITING_HUMAN.value:
            raise ValueError("run is not awaiting a human decision")

        side_to_org = seed.demo_side_orgs(sess)
        org_ids = list(dict.fromkeys(side_to_org.values()))

        approved = outcome == "APPROVE"
        message = ("Medical Director review: approved on clinical discretion; the borderline policy "
                   "gap is documented for audit." if approved else
                   "Medical Director review: the denial is upheld after clinical assessment.")
        env = Envelope(
            case_id=f"live-{run.case_name}",
            turn=run.turns,
            author="payer.medical_director",
            kind=Kind.DECISION,
            visibility=Visibility.ROOM,
            payload={
                "message": message,
                "reasoning": f"Human Medical Director decided {outcome} (HITL).",
                "outcome": outcome,
                "pa_event": "DECISION_APPROVED" if approved else "DECISION_DENIED",
                "hitl": True,
            },
        )
        ingest.record_envelope(sess, run=run, env=env, org_ids=org_ids,
                               side_to_org=side_to_org, author_side=_author_side)
        for org_id in org_ids:
            service.record_usage(sess, org_id=org_id, run_id=run_id, kind="run", units=1)
        service.finish_run(sess, run=run, status=RunStatus.SUCCEEDED.value,
                           final_state="DECIDE", turns=run.turns + 1, outcome=outcome)
    return outcome
