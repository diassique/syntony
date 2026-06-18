<p align="center">
  <img src="ui/web/public/syntony-logo.svg" alt="Syntony" height="60">
</p>

<p align="center">
  <strong>Prior authorization, settled in minutes — by a consent-gated mesh of AI agents that cross the org boundary.</strong>
</p>

<p align="center">
  <em>agents tuning to the same frequency</em>
</p>

<p align="center">
  <a href="https://syntony.live"><img alt="Live demo" src="https://img.shields.io/badge/demo-syntony.live-0b5e4f"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-0b5e4f"></a>
  <a href="https://band.ai"><img alt="Built on Band" src="https://img.shields.io/badge/built%20on-Band-0e1311"></a>
  <a href="https://aimlapi.com"><img alt="Models via AI/ML API" src="https://img.shields.io/badge/models-AI%2FML%20API-0e1311"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-0e1311">
  <img alt="React 19" src="https://img.shields.io/badge/react-19-0e1311">
</p>

---

Prior authorization is the back-and-forth a clinic and an insurer go through before a procedure is
approved: forms, faxes, phone queues, and denials over missing codes or documents. The AMA finds
**94% of physicians say it delays care**, and practices burn **~13 hours per physician per week** on
it. It's slow because it's fundamentally **cross-organizational** — two parties, two systems — and no
single-company app can fix a two-sided problem.

**Syntony** settles prior authorization as a live, consent-gated negotiation between AI agents that
actually cross the organizational boundary. It puts a team of agents on the **provider's side** and
another on the **payer's side**; they negotiate one case in a shared, audited room on
[Band](https://band.ai) — repairing the errors that cause most denials, looping in a human on the
borderline cases, and recording every step.

Two organizations, two sets of agents, one decision — **without raw PHI passing between them**, and
with a private audit trail each side can trust.

## What makes it different

- **Real cross-org mesh** — actual provider *and* payer agents, each posting under its own registered
  Band identity across two real accounts. Not one app pretending to be both sides.
- **Privacy moat** — room messages are shared, but each side's private agent reasoning stays on its
  own audit channel. The asymmetry is structural, not a policy promise: no raw PHI crosses the line.
- **Deny → appeal → overturn** — the loop that turns abandoned claims back into paid care, with a
  specific denial reason on every determination (as CMS-0057-F requires) and a human Medical Director
  in the loop on borderline cases.
- **No black box** — a protocol you can audit, an engine that's a plain coordinator loop, and a
  compliance-grade event trail (PDF/JSON export) on each side.

## How a case flows

1. **Intake** assembles a structured, FHIR-shaped request from the order — no raw PHI leaves the provider.
2. **Counsel** validates codes, signatures and documents, repairing the mismatches that cause most
   denials *before* submission; **Eligibility** verifies coverage.
3. The payer's **Reviewer** checks medical-necessity policy and asks only for what's missing, consulting
   **Clinical Guidelines / Pharmacy / Compliance** as needed.
4. On denial, **Appeals** cures the specific reason and resubmits → reconsideration → **overturn**.
5. Borderline cases **escalate to a human Medical Director**; every move is appended to the audit trail.

Sign in to the console as a provider org or a payer org and you see the *same* negotiation from each
side — but each side sees only its own agents' internal reasoning, never the counterparty's.

## The mesh — 9 agents across 2 organizations (+ 1 human)

| Provider organization | Payer organization | Governance |
|---|---|---|
| Intake · Counsel · Eligibility · Appeals | Reviewer · Clinical Guidelines · Pharmacy · Compliance · Notification | Medical Director *(human, HITL)* |

Heterogeneous by design: each role runs on a real framework (**Pydantic AI** for typed/reasoning roles,
**LangGraph** for stateful/pipeline roles) with a model picked per role — one protocol underneath.

## How it's built

Syntony is a small, auditable stack on top of [Band](https://band.ai), the agentic mesh that provides
the transport (accounts, rooms, `@mention` routing, bilateral cross-org contacts, an event journal,
REST/WS APIs):

```
L0  Band            transport: rooms, mentions, cross-org contacts, events — external
L1  protocol/       typed envelopes + a conversation state machine (data only)
L2  engine/         a base agent + a coordinator (runs the FSM, recruits, escalates) + one LLM seam
L3  domains/        the prior-authorization pack: schema + medical-necessity policy + roles
L4  ui/             the live dashboard + the per-organization audit console
control/            multi-tenant control plane (orgs, auth, encrypted credentials, runs, audit)
```

Every model call is routed through the [AI/ML API](https://aimlapi.com) gateway — one OpenAI-compatible
key, many models (Claude Opus 4.8 · Sonnet 4.6 · GPT-5.5), plus structured outputs, `reasoning_effort`,
vision, OCR, speech-to-text and embeddings. The agent code never names a provider; swap a slug to
re-route a role. Schema changes are managed with Alembic.

## App URLs

The web app is a single-page app with real, shareable URLs (deep-link and refresh-safe):

| Path | Page |
|---|---|
| `/` · `/login` · `/signup` | landing & auth |
| `/live` | public two-lane "what each account sees" dashboard |
| `/app` | console overview (sign-in required) |
| `/app/agents` · `/app/aiml` · `/app/insights` | the mesh roster · AI/ML telemetry · analytics |
| `/app/prior-auth` · `/app/prior-auth/:id` | review queue · a case |
| `/app/cases` · `/app/cases/:id` | negotiations · the live Theater for one run |
| `/app/patients` · `/app/new-request` · `/app/config` | provider / payer tooling |

## Tech stack

- **Mesh:** Band (cross-account agents, `@mention` routing, room + private events)
- **Models:** AI/ML API gateway (Claude Opus 4.8 / Sonnet 4.6 / GPT-5.5, `text-embedding-3-small`) via the OpenAI SDK
- **Agent frameworks:** Pydantic AI · LangGraph (+ langchain-openai)
- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLModel + PostgreSQL, Alembic, Argon2, PyJWT, ReportLab
- **Frontend:** React 19 + TypeScript, Vite, Tailwind CSS v4, a zero-dependency path router

## Getting started

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your Band + model (AI/ML API) + database credentials
alembic upgrade head          # create the control-plane schema
pytest -q                     # run the test suite

# build + serve the app (FastAPI serves the built SPA)
cd ui/web && npm install && npm run build && cd ../..
python ui/server.py           # → http://localhost:8000
```

## License

MIT — see [LICENSE](LICENSE).
