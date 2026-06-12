"""AuthBridge payload schema — the structured prior-auth request exchanged in
``Envelope.payload``. FHIR-aligned but deliberately minimal, and **synthetic only**
(no real PHI, no real PII). Domain packs own payload validation; the L1 protocol
treats this as an opaque dict.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Urgency(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"


class Code(BaseModel):
    """A coded concept (e.g. a CPT procedure code or an ICD-10 diagnosis)."""

    system: str = Field(..., description="Coding system, e.g. 'CPT' or 'ICD-10-CM'.")
    code: str = Field(..., description="The code value, e.g. '72148'.")
    display: str = Field(..., description="Human-readable label.")


class OrderingProvider(BaseModel):
    npi: str = Field(..., description="Synthetic 10-digit NPI.")
    name: str
    signed: bool = Field(False, description="Whether the order carries the provider's signature.")


class PriorAuthRequest(BaseModel):
    """A prior-authorization request. The unit of clinical work AuthBridge negotiates."""

    patient_ref: str = Field(..., description="Synthetic patient reference (NOT real PII).")
    procedure: Code = Field(..., description="The requested procedure (CPT).")
    diagnoses: list[Code] = Field(default_factory=list, description="Supporting diagnoses (ICD-10).")
    clinical_justification: str = Field("", description="Free-text medical rationale.")
    supporting_docs: list[str] = Field(
        default_factory=list,
        description="Document types attached, e.g. ['conservative_therapy_notes', 'imaging_report'].",
    )
    ordering_provider: OrderingProvider
    urgency: Urgency = Urgency.ROUTINE
