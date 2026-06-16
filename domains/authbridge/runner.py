"""AuthBridge agent runner — the brain the coordinator drives.

The coordinator (L2) is a dumb loop; this is where the *agents* live. For each FSM state
it decides **which role acts, what move it makes, and where the case goes next** — then
turns that into a coordination ``Move`` (envelope + next_state) the coordinator validates
and ships over Band.

Design invariant (see ``policy.py``): **policy is the deterministic ground truth; the LLM
reasons _around_ it, never overrides it.** So this module is a hybrid:

- ``plan(state, st)`` — a *pure* function: completeness checks + medical-necessity policy
  decide the move (role, kind, next_state) and mutate the working request deterministically.
  Fully testable offline; drives every FSM branch (approve / request-info / deny→escalate→HITL).
- a **narrator** — optionally calls the LLM (via ``engine.llm``, the AI/ML gateway) to phrase
  the room-facing ``message`` + ``reasoning`` that ride in the envelope payload, using the
  role's system prompt and structured outputs. It cannot change the decision or any code.

With ``narrate=None`` the runner is fully deterministic (offline tests, no key). With the
real ``llm_narrator()`` it produces a live, model-narrated clinic↔payer negotiation — the
demo on https://syntony.live and the AI/ML-prize showcase. Human (HITL) roles are never sent
to an LLM; their decision is rendered locally and clearly labelled as simulated until a real
Medical Director participant is wired.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable

log = logging.getLogger(__name__)

from engine.coordinator import CaseContext, Move
from engine.frameworks import turn_fn
from engine.llm import LLMConfig, completion_kwargs, looks_like_blob, make_client
from protocol import Envelope, Kind, State, Visibility

from .policy import (
    POLICY_TABLE,
    Decision,
    DenialReason,
    Outcome,
    completeness_issues,
    necessity_decision,
)

#: Denials a provider can cure by supplying documentation → route to appeal, don't terminate.
_APPEALABLE = {
    DenialReason.STEP_THERAPY_NOT_MET,
    DenialReason.CONSERVATIVE_CARE_NOT_MET,
    DenialReason.MISSING_DOCUMENTATION,
}
from .roles import ROLES
from .schema import Code, OrderingProvider, PriorAuthRequest

# Structured-output schema (an AI/ML feature we lean on): typed agent I/O, no free-text drift.
# NB: not every gateway model enforces json_schema strictly (Haiku doesn't) — we parse defensively.
AGENT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "agent_turn",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["message", "reasoning"],
            "additionalProperties": False,
        },
    },
}

# Counsel's repair knowledge: map a procedure's display to its CPT, for filling a blank code.
_DISPLAY_TO_CPT = {
    "MRI lumbar spine w/o contrast": "72148",
    "MRI knee w/o contrast": "73721",
    "MRI brain": "70551",
}


@dataclass
class AuthBridgeState:
    """Per-case working state the runner owns (lives in ``CaseContext.domain``)."""

    req: PriorAuthRequest
    decision: Decision | None = None
    pending_docs: tuple[str, ...] = ()
    info_satisfied: bool = False
    appealed: bool = False  # set once Provider Appeals has cured a denial and resubmitted
    # multi-agent pipeline progress (each gates a real specialist turn; see plan())
    eligibility_checked: bool = False  # provider Eligibility & Benefits ran (pre-submit)
    submitted: bool = False            # provider Counsel has submitted the request to the payer
    guidelines_done: bool = False      # payer Clinical Guidelines consulted
    compliance_done: bool = False      # payer Compliance & Audit consulted
    pharmacy_done: bool = False        # payer Pharmacy & Formulary consulted (drug cases)
    notified: bool = False             # Member Notification drafted before a terminal decision
    pending_consult: str | None = None  # which specialist the Reviewer is currently consulting
    retrieved_criteria: str = ""       # RAG: medical-necessity criterion the Guidelines agent cites

    # --- interactive workflow (the real two-sided flow; autoplay leaves these untouched) ---
    #: When True, plan() pauses (returns None) at every court-change so a real human on the
    #: matching side acts via the API. When False the runner auto-drives (the "Sample run").
    interactive: bool = False
    payer_review_started: bool = False  # the payer opened the case and kicked off UM review
    #: The action a payer human committed: "APPROVE" | "DENY" | "REQUEST_INFO" | "ESCALATE".
    payer_action: str | None = None
    payer_action_reason: str | None = None  # DenialReason code chosen by the payer (deny/info)
    payer_note: str = ""               # the payer human's free-text rationale (optional)
    provider_response_ready: bool = False  # provider supplied docs answering a payer info request
    provider_appeal_ready: bool = False    # provider chose to appeal an appealable denial
    new_docs: tuple[str, ...] = ()     # docs the provider just attached (pend response / appeal)
    committed_turns: int = 0           # audit turn offset across resumed segments
    recommendation: dict = field(default_factory=dict)  # UM recommendation surfaced to the payer
    auth_number: str = ""              # issued on APPROVE (HCR02 analogue)
    coverage_summary: str = ""         # real Coverage (plan + member id), cited by the eligibility step
    #: The payer policy ({code: PolicyRule}) this case is decided against — DB-loaded at runtime,
    #: defaults to the built-in table. NOT serialized (reference data; reloaded from the DB on resume).
    policy: dict = field(default_factory=lambda: POLICY_TABLE)


@dataclass(frozen=True)
class _Plan:
    """A deterministic move decision before any narration is attached."""

    role_id: str
    kind: Kind
    next_state: State
    facts: str
    mentions: tuple[str, ...]
    visibility: Visibility = Visibility.ROOM
    pa_event: str = ""                 # PA audit-trail event type (see DOMAIN_PA.md)
    denial_reason: str | None = None   # canonical DenialReason on a deny/info
    payload_extra: dict[str, Any] = field(default_factory=dict)


def _fix_request(req: PriorAuthRequest) -> list[str]:
    """Provider Counsel's pre-submit repair: fill a blank CPT, obtain the signature.
    Mutates ``req`` in place; returns a list of human-readable fixes applied."""
    fixes: list[str] = []
    if not req.procedure.code.strip():
        code = _DISPLAY_TO_CPT.get(req.procedure.display.strip())
        if code:
            req.procedure = Code(system="CPT", code=code, display=req.procedure.display)
            fixes.append(f"filled the missing CPT code ({code})")
    if not req.ordering_provider.signed:
        req.ordering_provider = OrderingProvider(
            npi=req.ordering_provider.npi, name=req.ordering_provider.name, signed=True
        )
        fixes.append("obtained the ordering-provider signature")
    return fixes


def _missing_docs(req: PriorAuthRequest, policy: dict | None = None) -> list[str]:
    rule = (policy or POLICY_TABLE).get(req.procedure.code)
    if rule is None:
        return []
    return [d for d in rule.required_docs if d not in req.supporting_docs]


def _is_drug(req: PriorAuthRequest) -> bool:
    """Drug requests (HCPCS J-codes) get a pharmacy/formulary consult."""
    return req.procedure.system.upper() == "HCPCS"


#: Appealable denial reason codes (string form) — a provider can cure these and resubmit.
_APPEALABLE_CODES = frozenset(r.value for r in _APPEALABLE)


def _auth_number(req: PriorAuthRequest) -> str:
    """A deterministic synthetic authorization/certification number (the HCR02 analogue).
    Stable per request so a resumed segment re-derives the same number. Synthetic only."""
    digest = hashlib.sha1(f"{req.procedure.code}|{req.patient_ref}".encode()).hexdigest()
    return "AUTH-" + str(int(digest[:8], 16) % 10_000_000).zfill(7)


def _reset_payer_review(st: AuthBridgeState) -> None:
    """Hand the case back to the payer for a fresh review (after a pend response or an appeal)."""
    st.payer_review_started = False
    st.payer_action = None
    st.payer_action_reason = None
    st.payer_note = ""
    st.recommendation = {}


def _suggested_action(d: Decision) -> str:
    """Map a policy recommendation to the payer action the console pre-selects."""
    if d.outcome is Outcome.APPROVE:
        return "APPROVE"
    if d.outcome is Outcome.REQUEST_INFO:
        return "REQUEST_INFO"
    return "ESCALATE" if d.escalate else "DENY"


def _resolve_determination(st: AuthBridgeState, d: Decision) -> tuple[str, str | None, str]:
    """Resolve (action, reason_code, reasons_text) for the payer determination.

    Interactive: the payer human's committed action wins (policy is advisory, surfaced as a
    recommendation). Autoplay: derive the action straight from policy (unchanged behavior)."""
    reasons = "; ".join(d.reasons)
    if st.interactive and st.payer_action:
        reason_code = st.payer_action_reason or (d.reason_code.value if d.reason_code else None)
        return st.payer_action, reason_code, (st.payer_note.strip() or reasons)
    return _suggested_action(d), (d.reason_code.value if d.reason_code else None), reasons


def _emit_determination(st: AuthBridgeState, action: str, reason_code: str | None, reasons: str) -> _Plan:
    """Emit the move for a resolved payer determination — shared by autoplay and the live flow."""
    if action == "APPROVE":
        if not st.notified:
            st.pending_consult = "notify"
            return _Plan("payer.reviewer", Kind.RECRUIT_REQUEST, State.RECRUIT,
                         "Approval reached — preparing the determination notice.",
                         mentions=("payer.notification",), pa_event="CONSULT_NOTIFY")
        if not st.auth_number:
            st.auth_number = _auth_number(st.req)
        overturned = st.appealed
        verb = "APPROVE on reconsideration (overturned)" if overturned else "APPROVE"
        return _Plan(
            "payer.reviewer", Kind.DECISION, State.DECIDE,
            f"{verb} — {reasons}. Authorization #{st.auth_number}.", mentions=("provider.counsel",),
            pa_event="DECISION_OVERTURNED" if overturned else "DECISION_APPROVED",
            payload_extra={"outcome": "APPROVE", "auth_number": st.auth_number,
                           **({"overturned": True} if overturned else {})},
        )
    if action == "REQUEST_INFO":
        st.pending_docs = tuple(_missing_docs(st.req, st.policy))
        st.info_satisfied = False
        return _Plan(
            "payer.reviewer", Kind.INFO_REQUEST, State.INFO,
            f"Recoverable gap — requesting information: {reasons}",
            mentions=("provider.counsel",),
            pa_event="PENDED_FOR_INFO", denial_reason=reason_code,
        )
    if action == "ESCALATE":
        return _Plan(
            "payer.reviewer", Kind.ESCALATION, State.ESCALATE,
            f"Borderline — not auto-denying; escalating to the Medical Director: {reasons}",
            mentions=("payer.medical_director",),
            pa_event="ESCALATED_TO_MD", denial_reason=reason_code,
        )
    # DENY: appealable → hand to Provider Appeals to cure & resubmit; else terminal.
    if not st.appealed and reason_code in _APPEALABLE_CODES:
        return _Plan(
            "payer.reviewer", Kind.DECISION, State.REVISE,
            f"DENY — {reasons}", mentions=("provider.appeals",),
            pa_event="DECISION_DENIED", denial_reason=reason_code,
            payload_extra={"outcome": "DENY", "appealable": True},
        )
    if not st.notified:
        st.pending_consult = "notify"
        return _Plan("payer.reviewer", Kind.RECRUIT_REQUEST, State.RECRUIT,
                     "Denial determined — preparing the determination notice and appeal rights.",
                     mentions=("payer.notification",), pa_event="CONSULT_NOTIFY")
    return _Plan(
        "payer.reviewer", Kind.DECISION, State.DECIDE,
        f"DENY — {reasons}", mentions=("provider.counsel",),
        pa_event="DECISION_DENIED", denial_reason=reason_code,
        payload_extra={"outcome": "DENY"},
    )


def _emit_appeal(st: AuthBridgeState) -> _Plan:
    """Provider Appeals cures the specific denial reason and resubmits for reconsideration.

    Interactive: cure with the documents the provider actually attached; autoplay: cure from
    the policy's required/step-therapy docs (unchanged behavior)."""
    rule = st.policy.get(st.req.procedure.code)
    candidate = (list(st.new_docs) if (st.interactive and st.new_docs)
                 else ([*rule.step_therapy_docs, *rule.required_docs] if rule else []))
    cured: list[str] = []
    for doc in candidate:
        if doc not in st.req.supporting_docs:
            st.req.supporting_docs = list(st.req.supporting_docs) + [doc]
            cured.append(doc)
    st.appealed = True
    code = st.decision.reason_code.value if (st.decision and st.decision.reason_code) else "the denial"
    facts = (f"Appeal: addressing {code} — supplied {cured} and requesting reconsideration."
             if cured else f"Appeal: contesting {code}; requesting reconsideration.")
    if st.interactive:
        st.provider_appeal_ready = False
        st.new_docs = ()
        _reset_payer_review(st)
    return _Plan(
        "provider.appeals", Kind.PROPOSAL, State.REVIEW, facts,
        mentions=("payer.reviewer",), pa_event="APPEAL_PACKET_ASSEMBLED",
    )


def plan(state: State, st: AuthBridgeState) -> _Plan | None:
    """Decide the next move purely from policy + the working request. No LLM, no I/O.

    The pipeline weaves specialist agents onto the generic L1 states (no new states):
    Intake → Eligibility (pre-submit) → Counsel submits → the Reviewer consults Clinical
    Guidelines, Compliance, and (for drugs) Pharmacy via RECRUIT round-trips → Member
    Notification drafts the notice → the terminal DECISION. Borderline cases escalate to
    the human Medical Director instead of an auto-deny.
    """
    if state is State.FRAME:
        return _Plan(
            "provider.intake", Kind.CASE_OPEN, State.PROPOSE,
            f"Opening a prior-authorization case for {st.req.procedure.display} "
            f"(patient {st.req.patient_ref}).",
            mentions=("provider.eligibility",), pa_event="PA_INITIATED",
        )

    if state is State.PROPOSE:
        # Provider Eligibility & Benefits verifies coverage before anything goes to the payer.
        if not st.eligibility_checked:
            st.eligibility_checked = True
            facts = (f"Verified eligibility — {st.coverage_summary}. The service is a covered benefit "
                     "requiring prior authorization; no eligibility blocks."
                     if st.coverage_summary else
                     "Verified active coverage and that the service is a covered benefit requiring prior "
                     "authorization — no eligibility blocks.")
            return _Plan(
                "provider.eligibility", Kind.INFO_RESPONSE, State.INFO, facts,
                mentions=("provider.counsel",), pa_event="ELIGIBILITY_VERIFIED",
            )
        return None  # PROPOSE is transient; Counsel submits from INFO

    if state is State.INFO:
        # First pass: Counsel runs the completeness check and submits.
        if not st.submitted:
            issues = completeness_issues(st.req)
            if issues:
                fixes = _fix_request(st.req)
                fixed = ". Corrected before submission: " + "; ".join(fixes) + "." if fixes else "."
                facts = "Pre-submit completeness check found: " + "; ".join(issues) + fixed
            else:
                facts = "Pre-submit completeness check passed; submitting the request to the payer."
            st.submitted = True
            return _Plan("provider.counsel", Kind.PROPOSAL, State.REVIEW, facts,
                         mentions=("payer.reviewer",), pa_event="REQUEST_SUBMITTED")
        # Later passes: Counsel answers a payer information request.
        if st.pending_docs and not st.info_satisfied:
            # Interactive: the provider must supply the documents — pause until they do.
            if st.interactive and not st.provider_response_ready:
                return None
            # Which docs went in: provider-attached set (interactive) or the requested set (autoplay).
            added = list(st.new_docs) if st.interactive else list(st.pending_docs)
            st.req.supporting_docs = list(st.req.supporting_docs) + [
                d for d in added if d not in st.req.supporting_docs
            ]
            st.info_satisfied = True
            if st.interactive:  # the cured request goes back to the payer for re-review
                st.provider_response_ready = False
                st.new_docs = ()
                _reset_payer_review(st)
            return _Plan(
                "provider.counsel", Kind.INFO_RESPONSE, State.REVIEW,
                "Supplied the requested documentation: " + (", ".join(added) or "no new documents") + ".",
                mentions=("payer.reviewer",), pa_event="DOCUMENTATION_COLLECTED",
            )
        return _Plan(
            "provider.counsel", Kind.INFO_RESPONSE, State.REVIEW,
            "No additional documentation is available for this request.",
            mentions=("payer.reviewer",), pa_event="DOCUMENTATION_COLLECTED",
        )

    if state is State.REVIEW:
        # Interactive: nothing happens on the payer side until a payer human opens the case.
        if st.interactive and not st.payer_review_started:
            return None

        # The Reviewer consults its specialists (each a RECRUIT round-trip) before deciding.
        if not st.guidelines_done:
            st.pending_consult = "guidelines"
            return _Plan("payer.reviewer", Kind.RECRUIT_REQUEST, State.RECRUIT,
                         "Consulting Clinical Guidelines on medical necessity.",
                         mentions=("payer.guidelines",), pa_event="CONSULT_GUIDELINES")
        if not st.compliance_done:
            st.pending_consult = "compliance"
            return _Plan("payer.reviewer", Kind.RECRUIT_REQUEST, State.RECRUIT,
                         "Routing to Compliance & Audit for HIPAA and specific-reason review.",
                         mentions=("payer.compliance",), pa_event="CONSULT_COMPLIANCE")
        if _is_drug(st.req) and not st.pharmacy_done:
            st.pending_consult = "pharmacy"
            return _Plan("payer.reviewer", Kind.RECRUIT_REQUEST, State.RECRUIT,
                         "Consulting Pharmacy & Formulary on the drug policy.",
                         mentions=("payer.pharmacy",), pa_event="CONSULT_PHARMACY")

        d = necessity_decision(st.req, st.policy)
        st.decision = d
        st.recommendation = {
            "outcome": d.outcome.value,
            "reason_code": d.reason_code.value if d.reason_code else None,
            "reasons": list(d.reasons),
            "escalate": d.escalate,
            "suggested_action": _suggested_action(d),
        }

        # Interactive: the consults are in; the payer human now commits the determination.
        if st.interactive and st.payer_action is None:
            return None

        action, reason_code, reasons = _resolve_determination(st, d)
        return _emit_determination(st, action, reason_code, reasons)  # _missing_docs uses st.policy

    if state is State.REVISE:
        # Interactive: the provider decides whether to appeal — pause until they do.
        if st.interactive and not st.provider_appeal_ready:
            return None
        return _emit_appeal(st)

    if state is State.RECRUIT:
        c = st.pending_consult
        st.pending_consult = None
        if c == "guidelines":
            st.guidelines_done = True
            facts = (f"Retrieved the governing criterion — “{st.retrieved_criteria}” — and "
                     "assessed the request against it." if st.retrieved_criteria else
                     "Applied evidence-based criteria (MCG/InterQual-style); reported which "
                     "medical-necessity criteria are met for the requested service.")
            return _Plan("payer.guidelines", Kind.PROPOSAL, State.REVIEW, facts,
                         mentions=("payer.reviewer",), pa_event="GUIDELINES_APPLIED")
        if c == "compliance":
            st.compliance_done = True
            return _Plan("payer.compliance", Kind.INFO_RESPONSE, State.REVIEW,
                         "Compliance check passed: minimum-necessary PHI, and any adverse "
                         "determination will carry a specific reason per CMS-0057-F.",
                         mentions=("payer.reviewer",), pa_event="COMPLIANCE_VERIFIED")
        if c == "pharmacy":
            st.pharmacy_done = True
            return _Plan("payer.pharmacy", Kind.PROPOSAL, State.REVIEW,
                         "Pharmacy review: checked formulary tier and step-therapy requirements "
                         "for the requested agent.",
                         mentions=("payer.reviewer",), pa_event="FORMULARY_CHECKED")
        if c == "notify":
            st.notified = True
            return _Plan("payer.notification", Kind.INFO_RESPONSE, State.REVIEW,
                         "Drafted the determination notice (member + provider copy) with the "
                         "decision rationale and, on a denial, the appeal rights and deadline.",
                         mentions=("payer.reviewer",), pa_event="NOTICE_DRAFTED")
        return None

    if state is State.ESCALATE:
        return _Plan(
            "payer.reviewer", Kind.RECRUIT_REQUEST, State.ARBITER,
            "Recruiting the Payer Medical Director to adjudicate the borderline case.",
            mentions=("payer.medical_director",), pa_event="P2P_SCHEDULED",
        )

    if state is State.ARBITER:
        # HITL: a human exercises discretion the automated policy may not. Simulated until a
        # real Medical Director participant is wired (no Human API key yet — see STATE.md).
        return _Plan(
            "payer.medical_director", Kind.DECISION, State.DECIDE,
            "Medical Director review: on clinical discretion the borderline case is approved; "
            "the automated policy gap is documented for audit.",
            mentions=("provider.counsel",),
            pa_event="DECISION_APPROVED",
            payload_extra={"outcome": "APPROVE", "note": "simulated Medical Director (HITL wiring pending)"},
        )

    # RECRUIT or any unmodelled state: nothing to do.
    return None


# ---- narration (LLM, optional) --------------------------------------------------

#: A narrator turns deterministic facts into a room-facing {message, reasoning}.
Narrator = Callable[..., dict]


def _summarize(history: list[Envelope], limit: int = 6) -> str:
    if not history:
        return "(no prior messages)"
    lines = []
    for e in history[-limit:]:
        msg = e.payload.get("message") or e.payload.get("facts") or ""
        lines.append(f"- {e.author} [{e.kind.value}]: {msg}")
    return "\n".join(lines)


def _find_str(obj: Any, key: str) -> str | None:
    """Depth-first search for a non-empty string under ``key`` (handles nested envelopes
    like ``{"payload": {"message": ...}}`` some models emit)."""
    if isinstance(obj, dict):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        for vv in obj.values():
            r = _find_str(vv, key)
            if r:
                return r
    elif isinstance(obj, list):
        for vv in obj:
            r = _find_str(vv, key)
            if r:
                return r
    return None


def _parse_turn(text: str, *, fallback: str) -> dict:
    """Extract {message, reasoning} from a model turn, robust to weaker/verbose models.

    Handles strict json_schema output AND common deviations: ```json fences, prose around
    the object, a leading @mention, and over-structured envelopes that bury ``message`` under
    another key. If nothing usable is found, falls back to the clean deterministic ``facts``
    (never dumps a raw JSON blob into the room)."""
    s = text.strip()
    if s.startswith("```"):  # strip a ```json ... ``` fence
        s = re.sub(r"^```[a-zA-Z0-9]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    candidates = [s]
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        candidates.append(s[i : j + 1])  # the {...} slice, in case prose wraps it
    for c in candidates:
        try:
            obj = json.loads(c)
        except (ValueError, TypeError):
            continue
        msg = _find_str(obj, "message")
        if msg:
            msg = re.sub(r"^@[\w.]+:\s*", "", msg).strip()  # drop a leading "@role:" prefix
            if msg and not msg.startswith(("{", "[")):  # a message that is itself JSON → unusable
                return {"message": msg, "reasoning": _find_str(obj, "reasoning") or fallback}
    # No usable message: keep short plain prose, else use the clean facts (never a blob).
    plain = s if (s and not s.lstrip().startswith(("{", "[")) and len(s) <= 400) else fallback
    return {"message": plain, "reasoning": fallback}


def llm_narrator(*, debug: bool = True, downshift: str | None = None) -> Narrator:
    """Build a narrator backed by the AI/ML gateway (via ``engine.llm``).

    ``debug``/``downshift`` set the model tier (see ``LLMConfig.from_role``): debug → Haiku,
    ``downshift="claude-sonnet-4-6"`` → Sonnet (the live default), neither → declared models.
    Clients are cached per provider (base_url + key env), not per model.
    """
    clients: dict[tuple[str, str], Any] = {}

    def _client(cfg: LLMConfig):
        key = (cfg.base_url, cfg.api_key_env)
        if key not in clients:
            clients[key] = make_client(cfg)
        return clients[key]

    def narrate(role_id: str, facts: str, kind: Kind, history: list[Envelope]) -> dict:
        spec = ROLES[role_id]
        user = (
            "You are taking your turn in a prior-authorization negotiation on Band.\n"
            f"AUTHORITATIVE FACTS (decided by policy — do NOT contradict, soften, or change any "
            f"code/decision): {facts}\n"
            f"Your move kind: {kind.value}.\n"
            f"Recent transcript:\n{_summarize(history)}\n\n"
            "Reply with ONLY a JSON object — no markdown, no code fences, no extra keys — "
            "with exactly two string fields: `message` (1–2 sentences addressing the counterpart "
            "by role, no PHI) and `reasoning` (one brief sentence). Phrase the facts; never override them."
        )
        cfg = LLMConfig.from_role(spec, debug=debug, downshift=downshift)
        # Roles backed by a wired framework (Pydantic AI / LangGraph) run their turn THROUGH it;
        # the model is served via the AI/ML gateway. Best-effort: fall through on any failure.
        fw = turn_fn(spec.framework.value)
        if fw is not None:
            try:
                out = fw(cfg=cfg, system_prompt=spec.system_prompt, user=user)
                # The framework message is already cleaned; reject only an actual JSON blob (a weak
                # model occasionally packs an envelope into the field) — no length cap on clean prose.
                msg = (out.get("message") or "").strip()
                if msg and not looks_like_blob(msg):
                    # `via` records the path that actually produced this turn (provenance).
                    return {"message": msg, "reasoning": out.get("reasoning") or msg, "via": spec.framework.value}
                log.warning("narrator: %s %s output unusable → gateway", role_id, spec.framework.value)
            except Exception as e:  # noqa: BLE001 — framework hiccup → fall back to the gateway
                log.warning("narrator: %s %s failed → gateway: %s: %s",
                            role_id, spec.framework.value, type(e).__name__, str(e)[:150])
        try:
            cfg = replace(cfg, response_format=AGENT_SCHEMA)
            kwargs = completion_kwargs(
                cfg, [{"role": "system", "content": spec.system_prompt}, {"role": "user", "content": user}]
            )
            kwargs["max_tokens"] = 400
            resp = _client(cfg).chat.completions.create(**kwargs)
            return {**_parse_turn(resp.choices[0].message.content or "", fallback=facts), "via": "aiml-gateway"}
        except Exception:  # noqa: BLE001 — a provider/key/slug failure must never break the run
            # Graceful degradation: phrase deterministically (e.g. the LLM gateway is unavailable).
            return {"message": facts, "reasoning": facts, "via": "fallback"}

    return narrate


# ---- the runner ----------------------------------------------------------------

def build_runner(*, narrate: Narrator | None = None):
    """Build the coordinator ``Runner`` for AuthBridge.

    ``narrate=None`` → deterministic text (offline, no key). Pass ``llm_narrator()`` for the
    live, model-narrated negotiation. Human roles are never narrated by an LLM.
    """

    async def runner(ctx: CaseContext) -> Move | None:
        st: AuthBridgeState = ctx.domain
        p = plan(ctx.state, st)
        if p is None:
            return None

        spec = ROLES[p.role_id]
        if narrate is not None and not spec.is_human:
            content = await asyncio.to_thread(narrate, p.role_id, p.facts, p.kind, ctx.history)
        else:
            content = {"message": p.facts, "reasoning": p.facts}

        payload = {"message": content["message"], "reasoning": content["reasoning"], "facts": p.facts}
        payload["framework"] = spec.framework.value          # the role's declared framework
        if content.get("via"):
            payload["via"] = content["via"]                  # the path that actually produced the turn
        if p.pa_event:
            payload["pa_event"] = p.pa_event
        if p.denial_reason:
            payload["denial_reason"] = p.denial_reason
        payload.update(p.payload_extra)
        env = Envelope(
            case_id=ctx.case_id,
            turn=ctx.turn,
            author=p.role_id,
            kind=p.kind,
            visibility=p.visibility,
            payload=payload,
        )
        return Move(env, next_state=p.next_state, mentions=p.mentions)

    return runner


async def run_authbridge(
    case_name: str,
    *,
    tools: Any | None = None,
    tools_for: Callable[[Envelope], Any] | None = None,
    narrate: Narrator | None = None,
    case_id: str | None = None,
    max_turns: int = 24,
    on_turn: Callable[..., Any] | None = None,
    pause_states: Any = None,
    request: PriorAuthRequest | None = None,
    criteria: str = "",
    policy: dict | None = None,
):
    """Run one AuthBridge case end-to-end through the coordinator.

    Drive a named synthetic case (``case_name`` ∈ ALL_CASES) or a **prebuilt ``request``**
    (e.g. one extracted from an uploaded document — ``case_name`` is then just a label).
    ``tools=None`` drives the FSM without touching Band; ``tools_for`` routes per side;
    ``narrate=llm_narrator()`` for a live run; ``on_turn`` streams each turn (see ``run_case``).
    """
    from engine.coordinator import run_case  # local import keeps engine deps lazy

    from .cases import ALL_CASES

    pol = policy or POLICY_TABLE
    if request is not None:
        st = AuthBridgeState(req=request, retrieved_criteria=criteria, policy=pol)
    else:
        if case_name not in ALL_CASES:
            raise KeyError(f"unknown case {case_name!r}; have {sorted(ALL_CASES)}")
        st = AuthBridgeState(req=ALL_CASES[case_name](), retrieved_criteria=criteria, policy=pol)
    return await run_case(
        case_id=case_id or f"authbridge-{case_name}",
        start=State.FRAME,
        runner=build_runner(narrate=narrate),
        tools=tools,
        tools_for=tools_for,
        domain=st,
        max_turns=max_turns,
        on_turn=on_turn,
        pause_states=pause_states,
    )
