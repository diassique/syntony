"""AuthBridge interactive workflow — the domain-pure half of the real two-sided flow.

Where the autoplay path (``run_all`` / ``live_run``) drives both sides end-to-end, the
*interactive* flow is asynchronous: a provider human fills a form and submits; a payer human
opens the case from a worklist, runs the UM review, and commits a verdict; the provider
responds to a pend or files an appeal. Each human action resumes the SAME L1 FSM from where
it last paused.

This module owns the **domain-pure** pieces (no Band, no DB, no LLM):

- ``build_request`` — turn a submitted form into a validated ``PriorAuthRequest``.
- ``precheck`` — Provider Counsel's pre-submit check (completeness + code-shape validation +
  the policy's documentation gaps), so the provider fixes problems *before* the payer ever
  sees them. This is the feature that kills the #1 real-world denial: missing documentation.
- ``dump_state`` / ``load_state`` — (de)serialize the working ``AuthBridgeState`` so a run can
  be parked on the ``Run`` row and resumed on the next request.
- ``run_segment`` — advance the FSM until the next court-change (a ``run_case`` wrapper).
- ``sla_deadline`` — the CMS-0057-F clock (72h expedited / 7d standard).

The control-plane wiring (create/persist/resume the ``Run``, stream to the audit trail, meter)
lives at the composition root in ``pa_workflow.py``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from protocol import State

from .policy import POLICY_TABLE, Decision, DenialReason, Outcome, completeness_issues
from .runner import AuthBridgeState, build_runner
from .schema import Code, OrderingProvider, PriorAuthRequest, Urgency

# ---- catalogs the request form offers (kept here so the API can serve them) ----

#: Supporting-document types a provider can attach. ``id`` is the machine token the policy
#: checks; ``label`` is the human description shown on the form's checklist.
SUPPORTING_DOC_TYPES: list[dict[str, str]] = [
    {"id": "conservative_therapy_notes", "label": "Conservative therapy notes (≥6 wks PT / NSAIDs)"},
    {"id": "step_therapy_record", "label": "Step-therapy record (preferred-agent trial & failure)"},
    {"id": "imaging_order", "label": "Imaging order"},
    {"id": "imaging_report", "label": "Prior imaging report"},
    {"id": "neuro_exam", "label": "Neurological exam findings"},
    {"id": "diagnosis_confirmation", "label": "Diagnosis confirmation"},
    {"id": "lab_results", "label": "Laboratory results"},
    {"id": "tb_hepb_screening", "label": "TB / Hep B screening (biologics)"},
]

#: Known procedures with a policy on file — the form suggests these (free entry still allowed).
KNOWN_PROCEDURES: list[dict[str, str]] = [
    {"system": "CPT", "code": "72148", "display": "MRI lumbar spine w/o contrast"},
    {"system": "CPT", "code": "73721", "display": "MRI knee w/o contrast"},
    {"system": "CPT", "code": "70551", "display": "MRI brain w/o contrast"},
    {"system": "HCPCS", "code": "J0135", "display": "Adalimumab (Humira), 20 mg"},
]

# CMS-0057-F decision windows (operational from 2026-01-01).
SLA_HOURS = {"expedited": 72, "standard": 7 * 24}

_CPT_RE = re.compile(r"^\d{5}$")               # 5 numeric digits
_HCPCS_RE = re.compile(r"^[A-Z]\d{4}$")        # one letter + 4 digits (Level II)
_ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$")  # e.g. M54.5, G83.4


# ---- building a request from a submitted form ----------------------------------

def build_request(form: dict) -> PriorAuthRequest:
    """Construct a ``PriorAuthRequest`` from the submission form. Raises ``ValueError`` on
    structurally invalid input (missing required fields); soft clinical gaps are surfaced by
    ``precheck`` rather than raised, so the provider can see and fix them."""
    proc = form.get("procedure") or {}
    code = str(proc.get("code", "")).strip().upper()
    system = (str(proc.get("system", "")).strip().upper() or _infer_system(code))
    display = str(proc.get("display", "")).strip() or _known_display(code)
    if not code:
        raise ValueError("A procedure code (CPT/HCPCS) is required.")

    diagnoses = []
    for d in form.get("diagnoses") or []:
        dc = str(d.get("code", "")).strip().upper()
        if not dc:
            continue
        diagnoses.append(Code(system=str(d.get("system") or "ICD-10-CM"), code=dc,
                              display=str(d.get("display") or "").strip()))

    op = form.get("ordering_provider") or {}
    provider = OrderingProvider(
        npi=str(op.get("npi", "")).strip(),
        name=str(op.get("name", "")).strip() or "Unknown provider",
        signed=bool(op.get("signed", False)),
    )

    urgency = Urgency.URGENT if str(form.get("urgency", "")).lower() in ("urgent", "expedited") else Urgency.ROUTINE

    return PriorAuthRequest(
        patient_ref=str(form.get("patient_ref", "")).strip() or "synthetic-patient",
        procedure=Code(system=system or "CPT", code=code, display=display or code),
        diagnoses=diagnoses,
        clinical_justification=str(form.get("clinical_justification", "")).strip(),
        supporting_docs=[str(x) for x in (form.get("supporting_docs") or [])],
        ordering_provider=provider,
        urgency=urgency,
        member_id=str(form.get("member_id", "")).strip(),
        health_plan=str(form.get("health_plan", "")).strip(),
        units=max(1, int(form.get("units", 1) or 1)),
        place_of_service=str(form.get("place_of_service", "")).strip(),
    )


def _infer_system(code: str) -> str:
    if _HCPCS_RE.match(code):
        return "HCPCS"
    return "CPT"


def _known_display(code: str) -> str:
    return next((p["display"] for p in KNOWN_PROCEDURES if p["code"] == code), "")


# ---- Counsel pre-submit check (the real value: catch denials before they happen) ----

def coding_issues(req: PriorAuthRequest) -> list[str]:
    """Validate code *shapes* (CPT 5-digit, HCPCS Level-II letter+4-digit, ICD-10 pattern).
    Replaces the old display→CPT lookup contrivance with genuine validation."""
    issues: list[str] = []
    sys_, code = req.procedure.system.upper(), req.procedure.code.strip().upper()
    if sys_ == "CPT" and not _CPT_RE.match(code):
        issues.append(f"CPT code {code or '(blank)'} is not a valid 5-digit code.")
    elif sys_ == "HCPCS" and not _HCPCS_RE.match(code):
        issues.append(f"HCPCS code {code or '(blank)'} is not a valid letter+4-digit Level-II code.")
    elif sys_ not in ("CPT", "HCPCS"):
        issues.append(f"Procedure coding system {sys_ or '(blank)'} must be CPT or HCPCS.")
    for d in req.diagnoses:
        if not _ICD10_RE.match(d.code.strip().upper()):
            issues.append(f"Diagnosis {d.code} is not a valid ICD-10-CM code.")
    return issues


def precheck(req: PriorAuthRequest, policy: dict | None = None) -> dict:
    """Provider Counsel's pre-submit review. Returns a structured report the form renders so
    the provider can fix gaps *before* submitting (the missing-doc / mismatched-code denials).
    ``policy`` is the DB-loaded ``{code: PolicyRule}`` map; defaults to the built-in table."""
    completeness = completeness_issues(req)
    coding = coding_issues(req)
    rule = (policy or POLICY_TABLE).get(req.procedure.code.strip().upper())
    missing_required = [d for d in rule.required_docs if d not in req.supporting_docs] if rule else []
    missing_step = [d for d in rule.step_therapy_docs if d not in req.supporting_docs] if rule else []
    blocking = completeness + coding
    return {
        "ready": not blocking,
        "blocking_issues": blocking,            # must fix before submit
        "completeness_issues": completeness,
        "coding_issues": coding,
        "policy_on_file": rule is not None,
        "missing_required_docs": missing_required,   # advisory → likely PEND if omitted
        "missing_step_therapy_docs": missing_step,   # advisory → likely DENY if omitted
        "advisories": _advisories(rule, missing_required, missing_step),
    }


def _advisories(rule, missing_required: list[str], missing_step: list[str]) -> list[str]:
    out: list[str] = []
    if rule is None:
        out.append("No policy on file for this code — the payer will review manually.")
    if missing_required:
        out.append(f"Likely pended for missing documentation: {', '.join(missing_required)}.")
    if missing_step:
        out.append(f"Likely denied for step therapy not met: {', '.join(missing_step)} not attached.")
    return out


def doc_options() -> dict:
    """Catalogs the request form needs (doc-type checklist + known procedures + reason enum)."""
    return {
        "supporting_doc_types": SUPPORTING_DOC_TYPES,
        "known_procedures": KNOWN_PROCEDURES,
        "denial_reasons": [r.value for r in DenialReason],
    }


# ---- the SLA clock (CMS-0057-F) ------------------------------------------------

def sla_deadline(started_at: datetime, urgency: str | None) -> datetime:
    hours = SLA_HOURS["expedited"] if (urgency or "").lower() == "expedited" else SLA_HOURS["standard"]
    return started_at + timedelta(hours=hours)


# ---- working-state (de)serialization -------------------------------------------

def new_state(req: PriorAuthRequest, *, criteria: str = "", coverage_summary: str = "",
              policy: dict | None = None) -> AuthBridgeState:
    """A fresh interactive working state for a just-submitted request. ``policy`` is the DB-loaded
    map (defaults to the built-in table); it is held on the state but never serialized."""
    from .policy import POLICY_TABLE
    return AuthBridgeState(req=req, interactive=True, retrieved_criteria=criteria,
                           coverage_summary=coverage_summary, policy=policy or POLICY_TABLE)


def dump_state(st: AuthBridgeState) -> dict:
    """Serialize the working state to a JSON-safe dict for the ``Run.workflow`` column."""
    d = st.decision
    return {
        "req": st.req.model_dump(mode="json"),
        "decision": None if d is None else {
            "outcome": d.outcome.value,
            "reasons": list(d.reasons),
            "reason_code": d.reason_code.value if d.reason_code else None,
            "escalate": d.escalate,
        },
        "pending_docs": list(st.pending_docs),
        "new_docs": list(st.new_docs),
        "info_satisfied": st.info_satisfied,
        "appealed": st.appealed,
        "eligibility_checked": st.eligibility_checked,
        "submitted": st.submitted,
        "guidelines_done": st.guidelines_done,
        "compliance_done": st.compliance_done,
        "pharmacy_done": st.pharmacy_done,
        "notified": st.notified,
        "pending_consult": st.pending_consult,
        "retrieved_criteria": st.retrieved_criteria,
        "interactive": st.interactive,
        "payer_review_started": st.payer_review_started,
        "payer_action": st.payer_action,
        "payer_action_reason": st.payer_action_reason,
        "payer_note": st.payer_note,
        "provider_response_ready": st.provider_response_ready,
        "provider_appeal_ready": st.provider_appeal_ready,
        "committed_turns": st.committed_turns,
        "recommendation": st.recommendation,
        "auth_number": st.auth_number,
        "coverage_summary": st.coverage_summary,
    }


def load_state(d: dict) -> AuthBridgeState:
    """Inverse of ``dump_state``."""
    dec = d.get("decision")
    decision = None
    if dec:
        decision = Decision(
            outcome=Outcome(dec["outcome"]),
            reasons=list(dec.get("reasons", [])),
            reason_code=DenialReason(dec["reason_code"]) if dec.get("reason_code") else None,
            escalate=bool(dec.get("escalate", False)),
        )
    return AuthBridgeState(
        req=PriorAuthRequest.model_validate(d["req"]),
        decision=decision,
        pending_docs=tuple(d.get("pending_docs", [])),
        new_docs=tuple(d.get("new_docs", [])),
        info_satisfied=d.get("info_satisfied", False),
        appealed=d.get("appealed", False),
        eligibility_checked=d.get("eligibility_checked", False),
        submitted=d.get("submitted", False),
        guidelines_done=d.get("guidelines_done", False),
        compliance_done=d.get("compliance_done", False),
        pharmacy_done=d.get("pharmacy_done", False),
        notified=d.get("notified", False),
        pending_consult=d.get("pending_consult"),
        retrieved_criteria=d.get("retrieved_criteria", ""),
        interactive=d.get("interactive", True),
        payer_review_started=d.get("payer_review_started", False),
        payer_action=d.get("payer_action"),
        payer_action_reason=d.get("payer_action_reason"),
        payer_note=d.get("payer_note", ""),
        provider_response_ready=d.get("provider_response_ready", False),
        provider_appeal_ready=d.get("provider_appeal_ready", False),
        committed_turns=d.get("committed_turns", 0),
        recommendation=d.get("recommendation", {}),
        auth_number=d.get("auth_number", ""),
        coverage_summary=d.get("coverage_summary", ""),
    )


# ---- the segment driver --------------------------------------------------------

async def run_segment(
    st: AuthBridgeState,
    *,
    start_state: State,
    case_id: str,
    narrate=None,
    tools_for=None,
    on_turn=None,
    history=None,
    max_turns: int = 24,
):
    """Advance the FSM from ``start_state`` until the next court-change.

    Pauses at ``ARBITER`` (the human Medical Director) via ``pause_states``; the other
    court-changes surface as ``stopped == "no_move"`` because ``plan()`` returns ``None`` when
    it is a human's turn (see ``runner.plan``). Returns the ``CoordinatorResult``."""
    from engine.coordinator import run_case

    return await run_case(
        case_id=case_id,
        start=start_state,
        runner=build_runner(narrate=narrate),
        tools_for=tools_for,
        domain=st,
        on_turn=on_turn,
        history=history,
        max_turns=max_turns,
        pause_states={State.ARBITER},
    )
