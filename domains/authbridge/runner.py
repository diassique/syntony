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
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from engine.coordinator import CaseContext, Move
from engine.llm import LLMConfig, completion_kwargs, make_client
from protocol import Envelope, Kind, State, Visibility

from .policy import (
    POLICY_TABLE,
    Decision,
    Outcome,
    completeness_issues,
    necessity_decision,
)
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


@dataclass(frozen=True)
class _Plan:
    """A deterministic move decision before any narration is attached."""

    role_id: str
    kind: Kind
    next_state: State
    facts: str
    mentions: tuple[str, ...]
    visibility: Visibility = Visibility.ROOM
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


def _missing_docs(req: PriorAuthRequest) -> list[str]:
    rule = POLICY_TABLE.get(req.procedure.code)
    if rule is None:
        return []
    return [d for d in rule.required_docs if d not in req.supporting_docs]


def plan(state: State, st: AuthBridgeState) -> _Plan | None:
    """Decide the next move purely from policy + the working request. No LLM, no I/O."""
    if state is State.FRAME:
        return _Plan(
            "provider.intake",
            Kind.CASE_OPEN,
            State.PROPOSE,
            f"Opening a prior-authorization case for {st.req.procedure.display} "
            f"(patient {st.req.patient_ref}).",
            mentions=("provider.counsel",),
        )

    if state is State.PROPOSE:
        issues = completeness_issues(st.req)
        if issues:
            fixes = _fix_request(st.req)
            facts = (
                "Pre-submit completeness check found: " + "; ".join(issues) + ". "
                "Corrected before submission: " + "; ".join(fixes) + "."
            )
        else:
            facts = "Pre-submit completeness check passed; submitting the request to the payer."
        return _Plan("provider.counsel", Kind.PROPOSAL, State.REVIEW, facts, mentions=("payer.reviewer",))

    if state is State.REVIEW:
        d = necessity_decision(st.req)
        st.decision = d
        reasons = "; ".join(d.reasons)
        if d.outcome is Outcome.APPROVE:
            return _Plan(
                "payer.reviewer", Kind.DECISION, State.DECIDE,
                f"APPROVE — {reasons}", mentions=("provider.counsel",),
                payload_extra={"outcome": "APPROVE"},
            )
        if d.outcome is Outcome.REQUEST_INFO:
            st.pending_docs = tuple(_missing_docs(st.req))
            st.info_satisfied = False
            return _Plan(
                "payer.reviewer", Kind.INFO_REQUEST, State.INFO,
                f"Recoverable gap — requesting information: {reasons}",
                mentions=("provider.counsel",),
            )
        # DENY
        if d.escalate:
            return _Plan(
                "payer.reviewer", Kind.ESCALATION, State.ESCALATE,
                f"Borderline denial — not auto-denying; escalating to the Medical Director: {reasons}",
                mentions=("payer.medical_director",),
            )
        return _Plan(
            "payer.reviewer", Kind.DECISION, State.DECIDE,
            f"DENY — {reasons}", mentions=("provider.counsel",),
            payload_extra={"outcome": "DENY"},
        )

    if state is State.INFO:
        if st.pending_docs and not st.info_satisfied:
            st.req.supporting_docs = list(st.req.supporting_docs) + [
                d for d in st.pending_docs if d not in st.req.supporting_docs
            ]
            st.info_satisfied = True
            return _Plan(
                "provider.counsel", Kind.INFO_RESPONSE, State.REVIEW,
                "Supplied the requested documentation: " + ", ".join(st.pending_docs) + ".",
                mentions=("payer.reviewer",),
            )
        return _Plan(
            "provider.counsel", Kind.INFO_RESPONSE, State.REVIEW,
            "No additional documentation is available for this request.",
            mentions=("payer.reviewer",),
        )

    if state is State.ESCALATE:
        return _Plan(
            "payer.reviewer", Kind.RECRUIT_REQUEST, State.ARBITER,
            "Recruiting the Payer Medical Director to adjudicate the borderline case.",
            mentions=("payer.medical_director",),
        )

    if state is State.ARBITER:
        # HITL: a human exercises discretion the automated policy may not. Simulated until a
        # real Medical Director participant is wired (no Human API key yet — see STATE.md).
        return _Plan(
            "payer.medical_director", Kind.DECISION, State.DECIDE,
            "Medical Director review: on clinical discretion the borderline case is approved; "
            "the automated policy gap is documented for audit.",
            mentions=("provider.counsel",),
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


def _parse_turn(text: str, *, fallback: str) -> dict:
    """Extract {message, reasoning} from a model turn, robust to weaker models.

    Handles strict json_schema output AND the common Haiku-tier deviations: markdown
    ```json fences, prose around the object, and extra keys (we read only message/reasoning).
    Falls back to the raw text as the message if no usable JSON is present."""
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
        if isinstance(obj, dict) and isinstance(obj.get("message"), str) and obj["message"].strip():
            return {"message": obj["message"].strip(), "reasoning": str(obj.get("reasoning") or fallback)}
    return {"message": s or fallback, "reasoning": fallback}


def llm_narrator(*, debug: bool = True) -> Narrator:
    """Build a narrator backed by the AI/ML gateway (via ``engine.llm``).

    ``debug=True`` runs reasoning roles on the cheap Haiku tier (and drops reasoning_effort).
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
        cfg = replace(LLMConfig.from_role(spec, debug=debug), response_format=AGENT_SCHEMA)
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
        kwargs = completion_kwargs(
            cfg, [{"role": "system", "content": spec.system_prompt}, {"role": "user", "content": user}]
        )
        kwargs["max_tokens"] = 400
        resp = _client(cfg).chat.completions.create(**kwargs)
        return _parse_turn(resp.choices[0].message.content or "", fallback=facts)

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
):
    """Run one synthetic AuthBridge case end-to-end through the coordinator.

    ``tools=None`` drives the FSM without touching Band; pass real ``AgentTools`` /
    ``FakeAgentTools`` to emit through one transport, or ``tools_for`` to route per side
    (provider→clinic account, payer→payer account). ``narrate=llm_narrator()`` for a live run.
    Returns the ``CoordinatorResult`` (final state + full transcript + stop reason).
    """
    from engine.coordinator import run_case  # local import keeps engine deps lazy

    from .cases import ALL_CASES

    if case_name not in ALL_CASES:
        raise KeyError(f"unknown case {case_name!r}; have {sorted(ALL_CASES)}")
    st = AuthBridgeState(req=ALL_CASES[case_name]())
    return await run_case(
        case_id=case_id or f"authbridge-{case_name}",
        start=State.FRAME,
        runner=build_runner(narrate=narrate),
        tools=tools,
        tools_for=tools_for,
        domain=st,
        max_turns=max_turns,
    )
