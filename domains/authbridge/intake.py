"""Document intake — turn a real clinical document into a structured PriorAuthRequest.

The flagship AI/ML use-case: prior auth drowns in faxes, scans and PDFs. Here an AI/ML
vision model reads an uploaded form image (or OCR extracts a PDF's text, then a model
structures it) and returns a typed request — which kicks off the live cross-org negotiation.

No raw PHI is retained: we keep only the structured, minimally-necessary fields.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from .schema import Code, OrderingProvider, PriorAuthRequest, Urgency

# json_schema the vision/text model must return (an AI/ML structured-output contract).
EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "prior_auth_intake",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "procedure_code": {"type": "string", "description": "CPT or HCPCS code"},
                "procedure_display": {"type": "string"},
                "icd10_codes": {"type": "array", "items": {"type": "string"}},
                "clinical_justification": {"type": "string"},
                "ordering_npi": {"type": "string"},
                "provider_signed": {"type": "boolean"},
                "supporting_documents": {"type": "array", "items": {"type": "string"}},
                "urgent": {"type": "boolean", "description": "marked STAT/urgent/expedited"},
            },
            "required": ["procedure_code", "procedure_display", "icd10_codes",
                         "clinical_justification", "ordering_npi", "provider_signed",
                         "supporting_documents", "urgent"],
            "additionalProperties": False,
        },
    },
}

INSTRUCTION = (
    "You are a prior-authorization intake assistant at a clinic. From this clinical document, "
    "extract the prior-authorization fields. Use the procedure's CPT or HCPCS code, the ICD-10 "
    "diagnosis codes, the clinical justification, the ordering provider's NPI and whether they "
    "signed, any attached supporting documents, and whether it is marked urgent/STAT. Do not "
    "invent values that are not present; leave a field empty/false if unknown."
)


def _to_request(d: dict[str, Any]) -> PriorAuthRequest:
    """Map the extracted JSON onto a typed PriorAuthRequest (defensive about missing fields)."""
    code = (d.get("procedure_code") or "").strip().upper()
    system = "HCPCS" if code[:1].isalpha() else "CPT"
    diagnoses = [Code(system="ICD-10-CM", code=c.strip().upper(), display="")
                 for c in (d.get("icd10_codes") or []) if isinstance(c, str) and c.strip()]
    docs = [s.strip() for s in (d.get("supporting_documents") or []) if isinstance(s, str) and s.strip()]
    return PriorAuthRequest(
        patient_ref="document-intake",  # no PHI retained
        procedure=Code(system=system, code=code, display=d.get("procedure_display") or "Requested procedure"),
        diagnoses=diagnoses,
        clinical_justification=(d.get("clinical_justification") or "Extracted from clinical document.").strip(),
        supporting_docs=docs,
        ordering_provider=OrderingProvider(
            npi=(d.get("ordering_npi") or "0000000000").strip(),
            name="Ordering provider (from document)",
            signed=bool(d.get("provider_signed")),
        ),
        urgency=Urgency.URGENT if d.get("urgent") else Urgency.ROUTINE,
    )


def extract_request_from_image(image_data_uri: str) -> PriorAuthRequest:
    """Read a document image with an AI/ML vision model → typed request."""
    from engine.llm import vision_extract

    return _to_request(vision_extract(image_data_uri, schema=EXTRACT_SCHEMA, instruction=INSTRUCTION))


def extract_request_from_pdf(document_url: str) -> PriorAuthRequest:
    """OCR a PDF at a URL (AI/ML /v1/ocr) → markdown → structure it → typed request."""
    from engine.llm import extract_from_text, ocr

    markdown = ocr(document_url)
    return _to_request(extract_from_text(markdown, schema=EXTRACT_SCHEMA, instruction=INSTRUCTION))


def sample_document_data_uri() -> str:
    """A synthetic prior-auth form image (no real PHI) for the demo's 'use a sample' path."""
    from PIL import Image, ImageDraw

    lines = (
        "PRIOR AUTHORIZATION REQUEST\n"
        "Patient: (synthetic)   DOB: 1980-02-02\n"
        "Procedure: MRI lumbar spine without contrast  (CPT 72148)\n"
        "Diagnosis: M54.5  Low back pain\n"
        "Ordering provider: Dr. A. Rivera   NPI 1000000007   [SIGNED]\n"
        "Attached: 6 weeks conservative therapy notes\n"
        "Priority: routine\n"
    )
    img = Image.new("RGB", (780, 260), "white")
    ImageDraw.Draw(img).multiline_text((16, 16), lines, fill="black", spacing=6)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
