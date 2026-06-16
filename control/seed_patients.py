"""Seed a curated roster of synthetic patients onto the clinic org.

Every value is fabricated — **no real PHI/PII**. ICD-10/CPT/HCPCS codes are real and valid, but
patients are fictional. The roster is hand-curated (not a Synthea import) so each chart drives a
distinct prior-auth path through our policy table — a provider can pick a patient, order the
suggested service, and watch the real workflow play out (clean approve, missing-doc pend,
step-therapy deny→appeal→overturn, urgent red-flag, borderline→Medical Director).

``doc_token`` on a treatment record maps to a PA ``supporting_docs`` token, so the chart literally
drives the request's document checklist (mirrors a DTR pulling documentation from the EHR).
"""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Condition, Coverage, Patient, TreatmentRecord

#: side note in `_order` = the service the demo user should order to exercise that path (not stored).
ROSTER: list[dict] = [
    {
        "mrn": "NS-100001", "given": "Maria", "family": "Alvarez", "dob": "1968-03-14", "sex": "female",
        "address": "482 Cedar St", "city": "Portland", "state": "OR", "postal": "97201", "phone": "503-555-0142",
        "coverage": ("Meridian Health Plan", "Medicare Advantage", "MA1029384701", "MAPD-014", "active"),
        "conditions": [("M54.5", "Low back pain"), ("M51.16", "Intervertebral disc disorder w/ radiculopathy, lumbar")],
        "treatments": [
            ("conservative_therapy", "conservative_therapy_notes", "8 weeks PT + NSAIDs; persistent radiculopathy, positive SLR", "2026-04-10", "no improvement"),
            ("imaging", "imaging_order", "Lumbar MRI order, signed", "2026-06-01", ""),
        ],
        "_order": "CPT 72148 (MRI lumbar) → clean APPROVE",
    },
    {
        "mrn": "NS-100002", "given": "James", "family": "Carter", "dob": "1981-09-02", "sex": "male",
        "address": "77 Birch Ave", "city": "Salem", "state": "OR", "postal": "97301", "phone": "503-555-0188",
        "coverage": ("BlueCross BlueShield", "Commercial", "BCB774102993", "GRP-5521", "active"),
        "conditions": [("M54.50", "Low back pain, unspecified")],
        "treatments": [("imaging", "imaging_order", "Lumbar MRI order, signed", "2026-06-05", "")],
        "_order": "CPT 72148 → PEND (conservative care not documented)",
    },
    {
        "mrn": "NS-100003", "given": "Diane", "family": "Foster", "dob": "1987-11-23", "sex": "female",
        "address": "1209 Maple Dr", "city": "Eugene", "state": "OR", "postal": "97401", "phone": "541-555-0119",
        "coverage": ("BlueCross BlueShield", "Commercial", "BCB330918844", "GRP-2210", "active"),
        "conditions": [("M06.9", "Rheumatoid arthritis, unspecified")],
        "treatments": [
            ("diagnosis", "diagnosis_confirmation", "Seropositive RA confirmed (anti-CCP, RF)", "2026-02-12", ""),
            ("step_therapy", "step_therapy_record", "Methotrexate 3 months, inadequate disease control", "2026-05-20", "failed"),
            ("screening", "tb_hepb_screening", "TB (IGRA) and Hep B screening negative", "2026-05-25", "cleared"),
        ],
        "_order": "HCPCS J0135 (Humira) → DENY step-therapy (if record not attached) → APPEAL → OVERTURN",
    },
    {
        "mrn": "NS-100004", "given": "Robert", "family": "Nguyen", "dob": "1956-06-30", "sex": "male",
        "address": "55 Spruce Ln", "city": "Bend", "state": "OR", "postal": "97701", "phone": "541-555-0173",
        "coverage": ("Meridian Health Plan", "Medicare Advantage", "MA8847120093", "MAPD-014", "active"),
        "conditions": [("G83.4", "Cauda equina syndrome")],
        "treatments": [
            ("exam", "neuro_exam", "Saddle anesthesia, acute urinary retention, bilateral leg weakness", "2026-06-14", "red flag"),
            ("imaging", "imaging_order", "Emergent lumbar MRI order, signed", "2026-06-14", ""),
        ],
        "_order": "CPT 72148 URGENT → expedited 72h, red-flag APPROVE",
    },
    {
        "mrn": "NS-100005", "given": "Walter", "family": "Brooks", "dob": "1963-01-08", "sex": "male",
        "address": "330 Oak St", "city": "Portland", "state": "OR", "postal": "97214", "phone": "503-555-0150",
        "coverage": ("Meridian Health Plan", "Medicare Advantage", "MA5521900471", "MAPD-009", "active"),
        "conditions": [("M79.1", "Myalgia")],
        "treatments": [
            ("conservative_therapy", "conservative_therapy_notes", "6 weeks PT; diffuse myalgia, no radiculopathy", "2026-05-02", "minimal change"),
            ("imaging", "imaging_order", "Lumbar MRI order, signed", "2026-06-03", ""),
        ],
        "_order": "CPT 72148 → borderline dx mismatch → ESCALATE to Medical Director",
    },
    {
        "mrn": "NS-100006", "given": "Susan", "family": "Park", "dob": "1974-07-19", "sex": "female",
        "address": "908 Willow Way", "city": "Hillsboro", "state": "OR", "postal": "97123", "phone": "503-555-0166",
        "coverage": ("Pacific Source", "Commercial", "PS660219338", "GRP-8841", "active"),
        "conditions": [("M23.205", "Derangement of medial meniscus, knee"), ("M17.0", "Bilateral primary osteoarthritis of knee")],
        "treatments": [
            ("conservative_therapy", "conservative_therapy_notes", "6 weeks PT + bracing; mechanical locking persists", "2026-04-28", "no improvement"),
            ("imaging", "imaging_order", "Knee MRI order, signed", "2026-06-02", ""),
        ],
        "_order": "CPT 73721 (MRI knee) → APPROVE",
    },
    {
        "mrn": "NS-100007", "given": "Henry", "family": "Adams", "dob": "1959-10-05", "sex": "male",
        "address": "12 Aspen Ct", "city": "Medford", "state": "OR", "postal": "97501", "phone": "541-555-0102",
        "coverage": ("Meridian Health Plan", "Medicare Advantage", "MA7711205590", "MAPD-009", "active"),
        "conditions": [("R51.9", "Headache, unspecified"), ("G43.909", "Migraine, unspecified, not intractable")],
        "treatments": [("imaging", "imaging_order", "Brain MRI order, signed", "2026-06-04", "")],
        "_order": "CPT 70551 (MRI brain) → auto-APPROVE under policy",
    },
    {
        "mrn": "NS-100008", "given": "Olivia", "family": "Bennett", "dob": "1990-02-17", "sex": "female",
        "address": "640 Fir St", "city": "Corvallis", "state": "OR", "postal": "97330", "phone": "541-555-0194",
        "coverage": ("BlueCross BlueShield", "Commercial", "BCB118840027", "GRP-2210", "active"),
        "conditions": [("M54.16", "Radiculopathy, lumbar region"), ("M51.16", "Intervertebral disc disorder w/ radiculopathy, lumbar")],
        "treatments": [
            ("conservative_therapy", "conservative_therapy_notes", "10 weeks PT + epidural steroid injection", "2026-03-30", "no improvement"),
            ("imaging", "imaging_report", "Prior radiograph: disc space narrowing L4-L5", "2026-03-15", ""),
            ("imaging", "imaging_order", "Lumbar MRI order, signed", "2026-06-06", ""),
        ],
        "_order": "CPT 72148 → clean APPROVE (well-documented)",
    },
]


def seed_patients(sess: Session, *, clinic_org_id: str) -> int:
    """Create the curated roster on the clinic org (idempotent by MRN). Returns count created."""
    created = 0
    for r in ROSTER:
        exists = sess.exec(
            select(Patient).where(Patient.org_id == clinic_org_id, Patient.mrn == r["mrn"])
        ).first()
        if exists is not None:
            continue
        p = Patient(org_id=clinic_org_id, mrn=r["mrn"], given_name=r["given"], family_name=r["family"],
                    dob=r["dob"], sex=r["sex"], address_line=r["address"], city=r["city"],
                    state=r["state"], postal_code=r["postal"], phone=r["phone"])
        sess.add(p)
        sess.flush()  # populate p.id
        payer, plan_type, member_id, group, status = r["coverage"]
        sess.add(Coverage(patient_id=p.id, payer_name=payer, plan_type=plan_type, member_id=member_id,
                          group_number=group, status=status, period_start="2026-01-01", period_end="2026-12-31"))
        for code, disp in r["conditions"]:
            sess.add(Condition(patient_id=p.id, code=code, display=disp))
        for kind, token, desc, date, outcome in r["treatments"]:
            sess.add(TreatmentRecord(patient_id=p.id, kind=kind, doc_token=token,
                                     description=desc, date=date, outcome=outcome))
        created += 1
    sess.commit()
    return created
