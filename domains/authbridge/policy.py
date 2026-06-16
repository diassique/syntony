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


class DenialReason(str, Enum):
    """Canonical, machine-typed denial/info reasons. CMS-0057-F (from 2026) requires payers to
    state a *specific* reason — this enum is that contract, and it's what the Appeals agent acts
    on. Mirrors the industry taxonomy (see DOMAIN_PA.md)."""

    MISSING_DOCUMENTATION = "MISSING_DOCUMENTATION"
    NOT_MEDICALLY_NECESSARY = "NOT_MEDICALLY_NECESSARY"
    STEP_THERAPY_NOT_MET = "STEP_THERAPY_NOT_MET"
    OUT_OF_NETWORK = "OUT_OF_NETWORK"
    ELIGIBILITY_FAILED = "ELIGIBILITY_FAILED"
    CODING_MISMATCH = "CODING_MISMATCH"
    EXPERIMENTAL_INVESTIGATIONAL = "EXPERIMENTAL_INVESTIGATIONAL"
    CONSERVATIVE_CARE_NOT_MET = "CONSERVATIVE_CARE_NOT_MET"
    FREQUENCY_LIMIT_EXCEEDED = "FREQUENCY_LIMIT_EXCEEDED"
    SITE_OF_CARE_NOT_APPROVED = "SITE_OF_CARE_NOT_APPROVED"


@dataclass(frozen=True)
class PolicyRule:
    """Medical-necessity rule for one procedure code (synthetic, illustrative)."""

    required_diagnosis_prefixes: tuple[str, ...] = ()       # e.g. ('M54',) low back pain
    required_docs: tuple[str, ...] = ()                     # missing → REQUEST_INFO (recoverable)
    step_therapy_docs: tuple[str, ...] = ()                 # missing → hard DENY (appealable)
    red_flag_prefixes: tuple[str, ...] = ()                 # emergent dx → necessity met, docs waived
    auto_approve: bool = False                              # trivially-approved low-cost items


#: Synthetic policy table. 72148 = MRI lumbar spine w/o contrast.
POLICY_TABLE: dict[str, PolicyRule] = {
    "72148": PolicyRule(
        required_diagnosis_prefixes=("M54", "M51"),         # low back pain / disc disorder
        required_docs=("conservative_therapy_notes",),      # 6 wks conservative care first
        red_flag_prefixes=("G83.4", "G82"),                 # cauda equina / cord compression → emergent
    ),
    "73721": PolicyRule(                                    # MRI knee w/o contrast
        required_diagnosis_prefixes=("M23", "M17", "S83"),
        required_docs=("conservative_therapy_notes",),
    ),
    "70551": PolicyRule(auto_approve=True),                 # MRI brain — auto-approve (synthetic)
    "J0135": PolicyRule(                                    # adalimumab (Humira) — specialty drug
        required_diagnosis_prefixes=("M05", "M06", "L40", "K50"),  # RA / psoriasis / Crohn
        step_therapy_docs=("step_therapy_record",),         # must try preferred agents first
    ),
}


@dataclass
class Decision:
    outcome: Outcome
    reasons: list[str] = field(default_factory=list)
    #: Machine-typed reason for a DENY/REQUEST_INFO (CMS-0057-F "specific reason"); drives Appeals.
    reason_code: DenialReason | None = None
    #: True when the request technically fails but sits close enough to the line that a human
    #: Medical Director should make the call rather than an automatic DENY.
    escalate: bool = False


def completeness_issues(req: PriorAuthRequest) -> list[str]:
    """Provider-side pre-submit checks. Empty list == ready to submit."""
    issues: list[str] = []
    if req.procedure.system.upper() not in ("CPT", "HCPCS") or not req.procedure.code.strip():
        issues.append("Procedure must carry a valid CPT/HCPCS code.")
    if not req.diagnoses:
        issues.append("At least one ICD-10 diagnosis is required.")
    if not req.ordering_provider.signed:
        issues.append("Ordering provider signature is missing.")
    if not req.clinical_justification.strip():
        issues.append("Clinical justification is empty.")
    return issues


def necessity_decision(req: PriorAuthRequest, policy: dict | None = None) -> Decision:
    """Payer-side medical-necessity decision against the policy table.

    ``policy`` is a ``{code: PolicyRule}`` map (DB-loaded at runtime); defaults to the built-in
    ``POLICY_TABLE`` for offline use."""
    rule = (policy or POLICY_TABLE).get(req.procedure.code)
    if rule is None:
        return Decision(Outcome.REQUEST_INFO, [f"No policy on file for CPT {req.procedure.code}; manual review."])
    if rule.auto_approve:
        return Decision(Outcome.APPROVE, ["Procedure is auto-approved under policy."])

    dx_codes = [d.code for d in req.diagnoses]

    # Red-flag presentation (e.g. cauda equina) → emergent; necessity is met on clinical urgency
    # and documentation prerequisites are waived. Checked first so an emergency is never pended.
    if any(c.startswith(p) for c in dx_codes for p in rule.red_flag_prefixes):
        return Decision(Outcome.APPROVE, ["Red-flag presentation — emergent imaging is medically "
                                          "necessary; conservative-care prerequisites waived."])

    dx_ok = any(c.startswith(p) for c in dx_codes for p in rule.required_diagnosis_prefixes)

    # Diagnosis mismatch → fails, but borderline cases go to a human, not an auto-deny.
    if not dx_ok:
        reason = (f"Diagnosis {dx_codes or '[]'} does not match medical-necessity criteria "
                  f"(expected one of {list(rule.required_diagnosis_prefixes)}).")
        return Decision(Outcome.DENY, [reason], reason_code=DenialReason.NOT_MEDICALLY_NECESSARY, escalate=True)

    # Step therapy not met → a hard DENY, but appealable (provider can supply the trial record).
    missing_step = [d for d in rule.step_therapy_docs if d not in req.supporting_docs]
    if missing_step:
        return Decision(
            Outcome.DENY,
            [f"Step therapy not met: preferred-agent trial undocumented (missing {missing_step})."],
            reason_code=DenialReason.STEP_THERAPY_NOT_MET,
        )

    # Diagnosis matches but supporting docs are missing → recoverable, ask for info.
    missing_docs = [d for d in rule.required_docs if d not in req.supporting_docs]
    if missing_docs:
        code = (DenialReason.CONSERVATIVE_CARE_NOT_MET
                if "conservative_therapy_notes" in missing_docs
                else DenialReason.MISSING_DOCUMENTATION)
        return Decision(Outcome.REQUEST_INFO, [f"Missing required documentation: {missing_docs}."], reason_code=code)

    return Decision(Outcome.APPROVE, ["Meets medical-necessity criteria."])
