"""L3 domain pack — **AuthBridge**: cross-org prior authorization.

Clinic and payer accounts negotiate a prior-auth case in a shared Band room. This
pack supplies the FHIR-shaped payload schema, medical-necessity policy + thresholds,
and the agent roles (Provider Intake, Provider Counsel/Coder, Payer Policy Reviewer,
Payer Medical Director (HITL), Appeals/Audit). Reference application for Syntony.
Uses only SYNTHETIC data — never real PHI.
"""
