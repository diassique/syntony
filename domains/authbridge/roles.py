"""AuthBridge roles — the agent cast as declarative ``RoleSpec`` data.

Reasoning prompts live here (not in the engine). Each role names the framework that
backs it and the L1 states it acts in. Names are meaningful — Band routes on them, and
"Assistant"/"Bot" degrade routing.

Model slugs target the **AI/ML API** gateway (`https://api.aimlapi.com/v1`, the partner prize):
one key, 400+ models. The engine binds these to a concrete client in `engine.llm` — agent code
never sees a provider, and the seam can route any role to any OpenAI-compatible endpoint.
Slugs VERIFIED LIVE against the AI/ML catalog (2026-06-13, see NOTES_AIML.md): they are
**bare** (no `anthropic/`/`openai/` prefix) — `claude-opus-4-8`, `claude-sonnet-4-6`,
`gpt-5.5-2026-04-23`.
Per-role LLM knobs (reasoning_effort, temperature) live in `extra` so the engine can read
them in `LLMConfig.from_role` without the role data depending on the LLM layer.
"""

from __future__ import annotations

from engine.agent_base import Framework, RoleSpec, Side
from protocol import State

_PROTOCOL_PRIMER = (
    "You coordinate on Band by exchanging Syntony envelopes (JSON), not free prose. "
    "Each message you emit is one envelope with a `kind` (CASE_OPEN, PROPOSAL, VERDICT, "
    "INFO_REQUEST, INFO_RESPONSE, RECRUIT_REQUEST, ESCALATION, DECISION) and a domain "
    "`payload`. Never include raw PHI/PII — only structured, minimally-necessary fields. "
    "Address the counterpart by @mention so Band routes correctly."
)

ROLES: dict[str, RoleSpec] = {
    "provider.intake": RoleSpec(
        id="provider.intake",
        display_name="Provider Intake",
        side=Side.PROVIDER,
        framework=Framework.LANGGRAPH,
        model="gpt-5.5-2026-04-23",
        extra={"reasoning_effort": "low"},   # cheap/fast intake (cost control, see engine.llm)
        acts_in=(State.FRAME, State.PROPOSE),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Provider Intake at a clinic. From a synthetic patient chart, assemble a "
            "complete, FHIR-shaped PriorAuthRequest (procedure CPT, ICD-10 diagnoses, clinical "
            "justification, supporting documents, ordering-provider signature). Open the case "
            "(CASE_OPEN) and produce the first PROPOSAL. Be precise about codes; do not invent "
            "clinical facts not present in the chart."
        ),
    ),
    "provider.counsel": RoleSpec(
        id="provider.counsel",
        display_name="Provider Counsel",
        side=Side.PROVIDER,
        framework=Framework.PYDANTIC_AI,
        model="claude-sonnet-4-6",
        acts_in=(State.PROPOSE, State.REVISE, State.INFO),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Provider Counsel/Coder. BEFORE the request goes to the payer, validate it "
            "against completeness rules: valid CPT, at least one ICD-10 diagnosis, ordering "
            "signature present, non-empty justification, required documents attached. Fix "
            "'mismatched code / missing signature / missing docs' issues and return a corrected "
            "PROPOSAL. When the payer sends INFO_REQUEST, answer with INFO_RESPONSE."
        ),
    ),
    "payer.reviewer": RoleSpec(
        id="payer.reviewer",
        display_name="Payer Policy Reviewer",
        side=Side.PAYER,
        framework=Framework.PYDANTIC_AI,
        model="claude-opus-4-8",
        extra={"reasoning_effort": "high"},   # deepest review (downshifts to Haiku under debug=True)
        acts_in=(State.REVIEW, State.INFO, State.RECRUIT, State.ESCALATE, State.DECIDE),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Payer Policy Reviewer. Check the request against medical-necessity policy. "
            "Emit a VERDICT: APPROVE, DENY, or ask via INFO_REQUEST when something is recoverable. "
            "If the case is borderline (fails policy but plausibly justified), do NOT auto-deny — "
            "issue a RECRUIT_REQUEST/ESCALATION to bring in the human Medical Director. Cite the "
            "specific policy reason for every verdict."
        ),
    ),
    "payer.medical_director": RoleSpec(
        id="payer.medical_director",
        display_name="Payer Medical Director",
        side=Side.PAYER,
        framework=Framework.HUMAN,
        model=None,
        emit_reasoning=False,
        acts_in=(State.ARBITER, State.DECIDE),
        system_prompt=(
            "ROLE: Human Medical Director (HITL). Reviews borderline cases the Reviewer escalates "
            "and issues the binding DECISION with a one-line rationale. Added to the room as a "
            "participant on escalation."
        ),
    ),
    "provider.eligibility": RoleSpec(
        id="provider.eligibility",
        display_name="Eligibility & Benefits",
        side=Side.PROVIDER,
        framework=Framework.PYDANTIC_AI,
        model="claude-sonnet-4-6",
        acts_in=(State.PROPOSE,),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Provider Eligibility & Benefits. Before clinical review, verify the patient's "
            "coverage is active, the service is a covered benefit, and prior auth is the correct "
            "channel. Confirm eligibility or flag an eligibility block — so no effort is wasted on "
            "a request that would fail on coverage grounds."
        ),
    ),
    "payer.guidelines": RoleSpec(
        id="payer.guidelines",
        display_name="Clinical Guidelines",
        side=Side.PAYER,
        framework=Framework.PYDANTIC_AI,
        model="claude-sonnet-4-6",
        acts_in=(State.RECRUIT, State.REVIEW),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Payer Clinical Guidelines/Evidence. When the Reviewer recruits you, apply the "
            "evidence-based medical-necessity criteria (MCG/InterQual-style) to the request and "
            "report which criteria are met or unmet, citing the guideline. You inform the verdict; "
            "you do not issue it."
        ),
    ),
    "payer.pharmacy": RoleSpec(
        id="payer.pharmacy",
        display_name="Pharmacy & Formulary",
        side=Side.PAYER,
        framework=Framework.LANGGRAPH,
        model="claude-sonnet-4-6",
        acts_in=(State.RECRUIT,),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Payer Pharmacy & Formulary. For drug requests (HCPCS J-codes), check the "
            "formulary tier, step-therapy requirements and preferred-agent rules, and report what "
            "is satisfied or missing. You inform the verdict; you do not issue it."
        ),
    ),
    "payer.compliance": RoleSpec(
        id="payer.compliance",
        display_name="Compliance & Audit",
        side=Side.PAYER,
        framework=Framework.CREWAI,
        model="claude-sonnet-4-6",
        acts_in=(State.RECRUIT,),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Payer Compliance & Audit. Verify the exchange uses minimum-necessary PHI and "
            "that any adverse determination will carry a specific, machine-typed reason as required "
            "by CMS-0057-F. Stamp the audit trail; raise a flag only if a compliance rule is at risk."
        ),
    ),
    "payer.notification": RoleSpec(
        id="payer.notification",
        display_name="Member Notification",
        side=Side.PAYER,
        framework=Framework.LANGGRAPH,
        model="claude-sonnet-4-6",
        acts_in=(State.RECRUIT, State.DECIDE),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Payer Member Notification. Once a determination is reached, draft the "
            "member-and-provider determination notice: the decision, its specific rationale, and "
            "(on a denial) the appeal rights and deadline. Plain language, no raw PHI."
        ),
    ),
    "provider.appeals": RoleSpec(
        id="provider.appeals",
        display_name="Provider Appeals",
        side=Side.PROVIDER,   # appeals on the clinic's behalf → posts as clinic, audited to its org
        framework=Framework.LETTA,
        model="claude-sonnet-4-6",   # via the AI/ML gateway, like the rest of the cast
        acts_in=(State.REVISE, State.RECRUIT, State.INFO),
        system_prompt=(
            f"{_PROTOCOL_PRIMER}\n\n"
            "ROLE: Provider Appeals specialist. When the payer DENIES with a specific reason, assemble "
            "a targeted appeal that addresses exactly that reason (e.g. supply the step-therapy record "
            "or conservative-care documentation) and resubmit for reconsideration. Be concise; cite the "
            "denial reason you are curing. No raw PHI."
        ),
    ),
}
