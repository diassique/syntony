# Syntony

**Prior authorization, settled in minutes — between providers and payers.**

Prior authorization is the back-and-forth a clinic and an insurer go through before a
procedure is approved: forms, faxes, phone queues, and denials over missing codes or
documents. Syntony automates that exchange. It puts an AI agent on the **provider's side**
and one on the **payer's side**; they negotiate a single case in a shared, audited room —
fixing the errors that cause most denials, looping in a human on the borderline cases, and
recording every step.

Two organizations, two sets of agents, one decision — without raw PHI passing between them,
and with a private audit trail each side can trust.

## How a case flows

1. **Intake** assembles a structured request from the order (no raw PHI leaves the provider).
2. **Counsel** validates codes, signatures and documents, repairing the mismatches that cause
   most denials *before* submission.
3. The **payer's reviewer** checks medical-necessity policy and asks only for what's missing.
4. Borderline cases **escalate to a human** medical director; every move is audited.

Sign in to the console as a provider org or a payer org and you see the same negotiation from
each side — but each side sees only its own agents' internal reasoning, never the
counterparty's. That privacy boundary is enforced by construction.

## How it's built

Syntony is a small, auditable stack on top of [Band](https://band.ai), the agentic mesh that
provides the transport (accounts, rooms, `@mention` routing, bilateral cross-org contacts, an
event journal, REST/WS APIs):

```
L0  Band            transport: rooms, mentions, cross-org contacts, events — external
L1  protocol/       typed envelopes + a conversation state machine
L2  engine/         a base agent + a coordinator (runs the FSM, recruits, escalates) + LLM seam
L3  domains/        the prior-authorization logic: schema + medical-necessity policy + roles
L4  ui/             the live dashboard + the per-organization audit console
control/            multi-tenant control plane (orgs, auth, encrypted credentials, runs, audit)
```

Closed models are routed through the [AI/ML API](https://aimlapi.com) gateway; the agent code
never names a provider. Schema is managed with Alembic.

## Getting started

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your Band + model + database credentials
alembic upgrade head          # create the control-plane schema
pytest -q                     # run the test suite
```

## License

MIT — see [LICENSE](LICENSE).
