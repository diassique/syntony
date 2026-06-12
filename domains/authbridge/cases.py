"""Synthetic prior-auth cases for AuthBridge. **No real PHI/PII** — every value is fabricated.

Each factory returns a fresh ``PriorAuthRequest`` so tests/demos can mutate freely. These
cases are chosen to exercise each policy path and to drive the demo storyline:
intake (incomplete) → Counsel fixes code+signature → Reviewer disputes necessity →
borderline → recruit human Medical Director.
"""

from __future__ import annotations

from .schema import Code, OrderingProvider, PriorAuthRequest, Urgency

_PROVIDER = OrderingProvider(npi="1000000007", name="Dr. Rivera (synthetic)", signed=True)


def mri_lumbar_complete() -> PriorAuthRequest:
    """72148 with matching dx + conservative-therapy notes → should APPROVE."""
    return PriorAuthRequest(
        patient_ref="synthetic-patient-001",
        procedure=Code(system="CPT", code="72148", display="MRI lumbar spine w/o contrast"),
        diagnoses=[Code(system="ICD-10-CM", code="M54.5", display="Low back pain")],
        clinical_justification="6 weeks of failed conservative therapy; persistent radiculopathy.",
        supporting_docs=["conservative_therapy_notes", "imaging_order"],
        ordering_provider=_PROVIDER,
        urgency=Urgency.ROUTINE,
    )


def mri_lumbar_raw_intake() -> PriorAuthRequest:
    """As first assembled by Intake: blank CPT code + UNSIGNED order.

    This is what Provider Counsel must catch and fix BEFORE submission (the demo's
    "caught a missing code before it went out" moment)."""
    req = mri_lumbar_complete()
    req.procedure = Code(system="CPT", code="", display="MRI lumbar spine w/o contrast")
    req.ordering_provider = OrderingProvider(npi="1000000007", name="Dr. Rivera (synthetic)", signed=False)
    return req


def mri_lumbar_missing_docs() -> PriorAuthRequest:
    """Matching dx but no conservative-therapy notes → REQUEST_INFO (recoverable)."""
    req = mri_lumbar_complete()
    req.supporting_docs = ["imaging_order"]
    return req


def mri_lumbar_dx_mismatch() -> PriorAuthRequest:
    """Diagnosis doesn't meet necessity criteria → DENY but borderline → escalate to a human."""
    req = mri_lumbar_complete()
    req.diagnoses = [Code(system="ICD-10-CM", code="M79.1", display="Myalgia")]
    return req


ALL_CASES = {
    "mri_lumbar_complete": mri_lumbar_complete,
    "mri_lumbar_raw_intake": mri_lumbar_raw_intake,
    "mri_lumbar_missing_docs": mri_lumbar_missing_docs,
    "mri_lumbar_dx_mismatch": mri_lumbar_dx_mismatch,
}
