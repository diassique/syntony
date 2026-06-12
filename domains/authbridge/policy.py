"""AuthBridge policy — deterministic guardrails + medical-necessity ruleset.

Two jobs, both pure (no Band, no LLM, no I/O):

1. ``completeness_issues`` — the checks Provider Counsel runs *before* submitting, to catch
   the "mismatched code / missing signature / missing docs" rejections that plague manual
   prior auth.
2. ``necessity_decision`` — the payer-side policy: given a (complete) request, decide
   APPROVE / DENY / REQUEST_INFO, or flag the case as borderline → escalate to a human
   Medical Director. Encodes a small synthetic policy table keyed by procedure code.

These are the deterministic thresholds the LLM roles reason *around*; the model never gets
to silently override policy. Synthetic data only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .schema import PriorAuthRequest


class Outcome(str, Enum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    REQUEST_INFO = "REQUEST_INFO"


@dataclass(frozen=True)
class PolicyRule:
    """Medical-necessity rule for one procedure code (synthetic, illustrative)."""

    required_diagnosis_prefixes: tuple[str, ...] = ()       # e.g. ('M54',) low back pain
    required_docs: tuple[str, ...] = ()                     # docs that must be attached
    auto_approve: bool = False                              # trivially-approved low-cost items


#: Synthetic policy table. 72148 = MRI lumbar spine w/o contrast.
POLICY_TABLE: dict[str, PolicyRule] = {
    "72148": PolicyRule(
        required_diagnosis_prefixes=("M54", "M51"),         # low back pain / disc disorder
        required_docs=("conservative_therapy_notes",),      # 6 wks conservative care first
    ),
    "73721": PolicyRule(                                    # MRI knee w/o contrast
        required_diagnosis_prefixes=("M23", "M17", "S83"),
        required_docs=("conservative_therapy_notes",),
    ),
    "70551": PolicyRule(auto_approve=True),                 # MRI brain — auto-approve (synthetic)
}


@dataclass
class Decision:
    outcome: Outcome
    reasons: list[str] = field(default_factory=list)
    #: True when the request technically fails but sits close enough to the line that a human
    #: Medical Director should make the call rather than an automatic DENY.
    escalate: bool = False


def completeness_issues(req: PriorAuthRequest) -> list[str]:
    """Provider-side pre-submit checks. Empty list == ready to submit."""
    issues: list[str] = []
    if req.procedure.system.upper() != "CPT" or not req.procedure.code.strip():
        issues.append("Procedure must carry a valid CPT code.")
    if not req.diagnoses:
        issues.append("At least one ICD-10 diagnosis is required.")
    if not req.ordering_provider.signed:
        issues.append("Ordering provider signature is missing.")
    if not req.clinical_justification.strip():
        issues.append("Clinical justification is empty.")
    return issues


def necessity_decision(req: PriorAuthRequest) -> Decision:
    """Payer-side medical-necessity decision against the policy table."""
    rule = POLICY_TABLE.get(req.procedure.code)
    if rule is None:
        return Decision(Outcome.REQUEST_INFO, [f"No policy on file for CPT {req.procedure.code}; manual review."])
    if rule.auto_approve:
        return Decision(Outcome.APPROVE, ["Procedure is auto-approved under policy."])

    dx_codes = [d.code for d in req.diagnoses]
    dx_ok = any(c.startswith(p) for c in dx_codes for p in rule.required_diagnosis_prefixes)
    missing_docs = [d for d in rule.required_docs if d not in req.supporting_docs]

    reasons: list[str] = []
    if not dx_ok:
        reasons.append(
            f"Diagnosis {dx_codes or '[]'} does not match medical-necessity criteria "
            f"(expected one of {list(rule.required_diagnosis_prefixes)})."
        )
    if missing_docs:
        reasons.append(f"Missing required documentation: {missing_docs}.")

    if not reasons:
        return Decision(Outcome.APPROVE, ["Meets medical-necessity criteria."])
    # Diagnosis matches but docs are missing → recoverable, ask for info.
    if dx_ok and missing_docs:
        return Decision(Outcome.REQUEST_INFO, reasons)
    # Diagnosis mismatch → fails, but borderline cases go to a human, not an auto-deny.
    return Decision(Outcome.DENY, reasons, escalate=True)
