"""Composition root for the interactive (two-sided, form-driven) prior-auth workflow.

This is the real-platform counterpart to ``live_run.py`` (which auto-drives both sides for the
"Sample run"). Here a provider human submits a form and a payer human acts from a worklist;
each action resumes the SAME L1 FSM from where it paused, with the working state parked on the
``Run.workflow`` column between requests.

It wires three layers together (none of which know about each other):
- **domain** (``domains/authbridge/workflow.py``): build/validate the request, precheck,
  (de)serialize the working state, advance one FSM segment;
- **control plane** (``control``): create/persist/resume the ``Run``, stream each turn into the
  org-scoped audit trail, meter on completion;
- **Band + AI/ML** (via ``live_run`` helpers + ``runner.llm_narrator``): post turns to the mesh
  and narrate them — best-effort, the flow still runs (and audits) if Band is down.

Each public coroutine maps to one API action. State preconditions raise ``ValueError`` (the API
turns those into 409s).
"""

from __future__ import annotations

import asyncio
import logging
import os

from control import ingest, seed, service
from control.db import session as open_session
from control.models import Run, RunMode, RunStatus
from domains.authbridge import workflow as wf
from domains.authbridge.runner import llm_narrator
from domains.authbridge.schema import Urgency
from engine.llm import BALANCED_MODEL
from protocol import Envelope, Kind, State, Visibility
from live_run import _author_side, _build_tools_for

log = logging.getLogger(__name__)

# Map the segment outcome (stop reason + final FSM state + working-state flags) → run status.
_TERMINAL = {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value}


def _status_for(result, st) -> str:
    """Derive the parked run status from how the segment stopped and whose turn it now is."""
    if result.stopped == "terminal":
        return RunStatus.SUCCEEDED.value
    if result.stopped == "paused" and result.final_state is State.ARBITER:
        return RunStatus.AWAITING_HUMAN.value
    if result.stopped == "no_move":
        fs = result.final_state
        if fs is State.REVIEW and not st.payer_review_started:
            return RunStatus.AWAITING_PAYER.value
        if fs is State.REVIEW:  # consults done, payer_action not yet committed
            return RunStatus.AWAITING_PAYER_DECISION.value
        if fs in (State.INFO, State.REVISE):  # pended / appealable denial → provider's move
            return RunStatus.AWAITING_PROVIDER.value
    return RunStatus.FAILED.value


def _case_label(req) -> str:
    return f"{req.procedure.system} {req.procedure.code} — {req.procedure.display}".strip()


async def _retrieve_criteria(req) -> str:
    try:
        from domains.authbridge.criteria import retrieve
        with open_session() as sess:
            corpus = service.criteria_corpus(sess) or None  # DB-backed; None → built-in fallback
        query = (f"{req.procedure.display} (code {req.procedure.code}); "
                 f"diagnoses {[d.code for d in req.diagnoses]}")
        hits = await asyncio.to_thread(retrieve, query, 1, corpus)
        return hits[0][1] if hits else ""
    except Exception as e:  # noqa: BLE001 — RAG is optional
        log.info("pa_workflow: criteria retrieval skipped (%s: %s)", type(e).__name__, str(e)[:100])
        return ""


def _history_from_events(sess, run_id: str, org_id: str) -> list[Envelope]:
    """Rehydrate a lightweight transcript (room messages, this org's view) for narration
    context when resuming a parked case. Best-effort; never raises into the caller."""
    from sqlmodel import select
    from control.models import Event
    out: list[Envelope] = []
    try:
        rows = sess.exec(
            select(Event).where(Event.run_id == run_id, Event.org_id == org_id,
                                Event.visibility == "room").order_by(Event.turn, Event.created_at)
        ).all()
        for ev in rows:
            try:
                out.append(Envelope(case_id=f"pa-{run_id}", turn=ev.turn, author=ev.author,
                                    kind=Kind(ev.kind), visibility=Visibility.ROOM, payload=ev.payload or {}))
            except Exception:  # noqa: BLE001 — skip an un-reconstructable row
                continue
    except Exception as e:  # noqa: BLE001
        log.info("pa_workflow: history rehydrate skipped (%s)", type(e).__name__)
    return out


# ---- the segment runner (load → advance → persist) -----------------------------

async def _advance(run_id: str, *, full: bool = False) -> dict:
    """Resume the parked run, run one FSM segment, stream turns, and persist the new state."""
    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        data = dict(run.workflow or {})
        provider_org = data["side_to_org"]["provider"]
        history = _history_from_events(sess, run_id, provider_org)
        room_id = run.room_id

    side_to_org = data["side_to_org"]
    org_ids = list(dict.fromkeys(side_to_org.values()))
    st = wf.load_state(data["state"])
    start = State(data["fsm_state"])
    case_id = f"pa-{run_id}"
    base_turn = st.committed_turns

    def on_turn(env: Envelope, _state) -> None:
        rec = env.model_copy(update={"turn": base_turn + env.turn})  # monotonic audit ordering
        with open_session() as s2:
            r2 = s2.get(Run, run_id)
            if r2 is not None:
                ingest.record_envelope(s2, run=r2, env=rec, org_ids=org_ids,
                                       side_to_org=side_to_org, author_side=_author_side)

    tools_for, new_room = _build_tools_for(case_id, room_id=room_id)
    # Narrate via the AI/ML gateway when a key is present; otherwise run deterministically (no
    # network) so the flow never blocks on the gateway — same graceful-degradation rule as live_run.
    if os.environ.get("AIML_API_KEY"):
        narrate = llm_narrator() if full else llm_narrator(downshift=BALANCED_MODEL)
    else:
        narrate = None
    try:
        result = await wf.run_segment(st, start_state=start, case_id=case_id, narrate=narrate,
                                      tools_for=tools_for, on_turn=on_turn, history=history)
        st.committed_turns = base_turn + result.turns
        status = _status_for(result, st)
        final_state = result.final_state.value
    except Exception as e:  # noqa: BLE001 — settle the run so the console stops polling
        log.warning("pa_workflow: segment failed (%s: %s)", type(e).__name__, str(e)[:160])
        status, final_state = RunStatus.FAILED.value, start.value

    outcome = (st.payer_action if status in _TERMINAL and st.payer_action else None)
    if status == RunStatus.SUCCEEDED.value and st.decision and not outcome:
        outcome = st.recommendation.get("outcome") or (st.decision.outcome.value if st.decision else None)

    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        run.workflow = {**data, "state": wf.dump_state(st), "fsm_state": final_state}
        run.room_id = new_room or run.room_id
        run.turns = st.committed_turns
        run.final_state = final_state
        if status in _TERMINAL:
            for org_id in org_ids:
                service.record_usage(sess, org_id=org_id, run_id=run_id, kind="run", units=1)
            service.finish_run(sess, run=run, status=status, final_state=final_state,
                               turns=st.committed_turns, outcome=outcome)
        else:
            run.status = status
            sess.add(run)
            sess.commit()
    return {"run_id": run_id, "status": status, "final_state": final_state}


# ---- side resolution -----------------------------------------------------------

def _resolve_sides(sess, submitter_org: str) -> dict[str, str]:
    """Provider org = the submitter; payer org = the (single) demo payer. Falls back so a run
    is never attributed to one org on both sides."""
    seed.seed_demo(sess)
    demo = seed.demo_side_orgs(sess)
    payer_org = demo.get("payer")
    if not payer_org:
        raise RuntimeError("payer org not seeded — cannot route the request")
    provider_org = submitter_org if submitter_org != payer_org else demo.get("provider")
    if not provider_org:
        raise RuntimeError("provider org not resolved")
    return {"provider": provider_org, "payer": payer_org}


# ---- public actions (one per API endpoint) -------------------------------------

async def submit_request(form: dict, *, submitter_org: str, patient_id: str | None = None,
                         full: bool = False) -> dict:
    """Provider submits a PA request: build + validate, open the interactive run, and run the
    provider-side segment (intake → eligibility → Counsel completeness → submit) which parks
    the case in the payer's worklist (AWAITING_PAYER).

    When ``patient_id`` is given (the request was assembled from a chart), the run is linked to
    the patient and the eligibility step cites the patient's real Coverage."""
    req = wf.build_request(form)
    criteria = await _retrieve_criteria(req)
    with open_session() as sess:
        sides = _resolve_sides(sess, submitter_org)
        cover = ""
        if patient_id:
            patient = service.get_patient(sess, org_id=sides["provider"], patient_id=patient_id)
            if patient is None:
                raise ValueError("patient not found on this organization's roster")
            cover = service.coverage_summary(service.patient_coverage(sess, patient_id))
        # Gold carding: a trusted provider+service is exempt → auto-approve, skip payer review.
        gc = service.active_gold_card(sess, org_id=sides["provider"],
                                      npi=req.ordering_provider.npi, code=req.procedure.code)
        if gc is not None:
            return _gold_card_autoapprove(sess, sides=sides, req=req, patient_id=patient_id, gc=gc)
        st = wf.new_state(req, criteria=criteria, coverage_summary=cover)
        run = service.start_run(sess, org_id=sides["provider"], case_name=_case_label(req))
        run.mode = RunMode.INTERACTIVE.value
        run.patient_id = patient_id
        run.urgency = "expedited" if req.urgency is Urgency.URGENT else "standard"
        run.workflow = {"side_to_org": sides, "state": wf.dump_state(st), "fsm_state": State.FRAME.value}
        sess.add(run)
        sess.commit()
        sess.refresh(run)
        run_id = run.id
    return await _advance(run_id, full=full)


def _gold_card_autoapprove(sess, *, sides: dict[str, str], req, patient_id: str | None, gc) -> dict:
    """A gold-carded provider+service is authorized on submit, with no payer review — one
    GOLD_CARD_EXEMPTION decision recorded to the audit trail (the burden reduction PA reform wants)."""
    from domains.authbridge.runner import _auth_number
    org_ids = list(dict.fromkeys(sides.values()))
    st = wf.new_state(req)
    st.submitted = True
    st.auth_number = _auth_number(req)
    run = service.start_run(sess, org_id=sides["provider"], case_name=_case_label(req))
    run.mode = RunMode.INTERACTIVE.value
    run.patient_id = patient_id
    run.urgency = "expedited" if req.urgency is Urgency.URGENT else "standard"
    msg = (f"Gold-card exemption — {gc.provider_name} is gold-carded for {req.procedure.code} "
           f"({gc.basis}). Auto-approved without review. Authorization #{st.auth_number}.")
    env = Envelope(
        case_id=f"pa-{run.id}", turn=0, author="payer.reviewer", kind=Kind.DECISION,
        visibility=Visibility.ROOM,
        payload={"message": msg, "outcome": "APPROVE", "pa_event": "GOLD_CARD_EXEMPTION",
                 "auth_number": st.auth_number, "gold_card": True},
    )
    st.committed_turns = 1
    run.workflow = {"side_to_org": sides, "state": wf.dump_state(st), "fsm_state": State.DECIDE.value}
    sess.add(run)
    sess.commit()
    sess.refresh(run)
    ingest.record_envelope(sess, run=run, env=env, org_ids=org_ids,
                           side_to_org=sides, author_side=_author_side)
    for org_id in org_ids:
        service.record_usage(sess, org_id=org_id, run_id=run.id, kind="run", units=1)
    service.finish_run(sess, run=run, status=RunStatus.SUCCEEDED.value,
                       final_state=State.DECIDE.value, turns=1, outcome="APPROVE")
    return {"run_id": run.id, "status": RunStatus.SUCCEEDED.value, "outcome": "APPROVE", "gold_card": True}


def _require_status(run: Run, *expected: str) -> None:
    if run.status not in expected:
        raise ValueError(f"action not allowed while run is '{run.status}'")


async def _act(run_id: str, *, allowed: tuple[str, ...], mutate, full: bool = False) -> dict:
    """Load the parked state, apply ``mutate(st)``, persist, and advance one segment."""
    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        _require_status(run, *allowed)
        data = dict(run.workflow or {})
        st = wf.load_state(data["state"])
        mutate(st)
        run.workflow = {**data, "state": wf.dump_state(st)}
        sess.add(run)
        sess.commit()
    return await _advance(run_id, full=full)


async def start_review(run_id: str, *, full: bool = False) -> dict:
    """Payer opens the case and runs the UM review (consults → recommendation)."""
    def mutate(st):
        st.payer_review_started = True
    return await _act(run_id, allowed=(RunStatus.AWAITING_PAYER.value,), mutate=mutate, full=full)


async def decide(run_id: str, *, action: str, reason_code: str | None = None,
                 note: str = "", full: bool = False) -> dict:
    """Payer commits a determination: APPROVE / DENY / REQUEST_INFO / ESCALATE."""
    action = (action or "").upper()
    if action not in ("APPROVE", "DENY", "REQUEST_INFO", "ESCALATE"):
        raise ValueError(f"unknown payer action {action!r}")

    def mutate(st):
        st.payer_action = action
        st.payer_action_reason = reason_code
        st.payer_note = note or ""
    return await _act(run_id, allowed=(RunStatus.AWAITING_PAYER_DECISION.value,), mutate=mutate, full=full)


async def respond_to_pend(run_id: str, *, docs: list[str], full: bool = False) -> dict:
    """Provider answers a payer information request by attaching documents; re-review follows."""
    def mutate(st):
        st.new_docs = tuple(docs or [])
        st.provider_response_ready = True
    return await _act(run_id, allowed=(RunStatus.AWAITING_PROVIDER.value,), mutate=mutate, full=full)


async def file_appeal(run_id: str, *, docs: list[str], full: bool = False) -> dict:
    """Provider appeals an appealable denial, supplying the curing documents; re-review follows."""
    def mutate(st):
        st.new_docs = tuple(docs or [])
        st.provider_appeal_ready = True
    return await _act(run_id, allowed=(RunStatus.AWAITING_PROVIDER.value,), mutate=mutate, full=full)


async def accept_denial(run_id: str) -> dict:
    """Provider accepts a denial without appealing — close the run as a terminal DENY."""
    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        _require_status(run, RunStatus.AWAITING_PROVIDER.value)
        data = dict(run.workflow or {})
        side_to_org = data["side_to_org"]
        org_ids = list(dict.fromkeys(side_to_org.values()))
        st = wf.load_state(data["state"])
        reason = st.decision.reason_code.value if (st.decision and st.decision.reason_code) else None
        env = Envelope(
            case_id=f"pa-{run_id}", turn=st.committed_turns, author="provider.counsel",
            kind=Kind.DECISION, visibility=Visibility.ROOM,
            payload={"message": "Provider accepts the determination; the case is closed without appeal.",
                     "outcome": "DENY", "pa_event": "DECISION_DENIED",
                     **({"denial_reason": reason} if reason else {})},
        )
        ingest.record_envelope(sess, run=run, env=env, org_ids=org_ids,
                               side_to_org=side_to_org, author_side=_author_side)
        st.committed_turns += 1
        run.workflow = {**data, "state": wf.dump_state(st), "fsm_state": State.DECIDE.value}
        for org_id in org_ids:
            service.record_usage(sess, org_id=org_id, run_id=run_id, kind="run", units=1)
        service.finish_run(sess, run=run, status=RunStatus.SUCCEEDED.value,
                           final_state=State.DECIDE.value, turns=st.committed_turns, outcome="DENY")
    return {"run_id": run_id, "status": RunStatus.SUCCEEDED.value, "outcome": "DENY"}


async def md_decide(run_id: str, *, outcome: str, note: str = "") -> dict:
    """Human Medical Director resolves a borderline (AWAITING_HUMAN) case — terminal verdict."""
    outcome = (outcome or "").upper()
    if outcome not in ("APPROVE", "DENY"):
        raise ValueError(f"outcome must be APPROVE or DENY, got {outcome!r}")
    with open_session() as sess:
        run = sess.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        _require_status(run, RunStatus.AWAITING_HUMAN.value)
        data = dict(run.workflow or {})
        side_to_org = data["side_to_org"]
        org_ids = list(dict.fromkeys(side_to_org.values()))
        st = wf.load_state(data["state"])
        approved = outcome == "APPROVE"
        if approved and not st.auth_number:
            from domains.authbridge.runner import _auth_number
            st.auth_number = _auth_number(st.req)
        msg = note.strip() or (
            "Medical Director review: approved on clinical discretion; the borderline policy gap "
            "is documented for audit." if approved else
            "Medical Director review: the denial is upheld after clinical assessment.")
        env = Envelope(
            case_id=f"pa-{run_id}", turn=st.committed_turns, author="payer.medical_director",
            kind=Kind.DECISION, visibility=Visibility.ROOM,
            payload={"message": msg, "outcome": outcome, "hitl": True,
                     "pa_event": "DECISION_APPROVED" if approved else "DECISION_DENIED",
                     **({"auth_number": st.auth_number} if approved else {})},
        )
        ingest.record_envelope(sess, run=run, env=env, org_ids=org_ids,
                               side_to_org=side_to_org, author_side=_author_side)
        st.committed_turns += 1
        run.workflow = {**data, "state": wf.dump_state(st), "fsm_state": State.DECIDE.value}
        for org_id in org_ids:
            service.record_usage(sess, org_id=org_id, run_id=run_id, kind="run", units=1)
        service.finish_run(sess, run=run, status=RunStatus.SUCCEEDED.value,
                           final_state=State.DECIDE.value, turns=st.committed_turns, outcome=outcome)
    return {"run_id": run_id, "status": RunStatus.SUCCEEDED.value, "outcome": outcome}
