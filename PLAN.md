# PLAN — Syntony roadmap & backlog

> Forward-looking plan for the ~6-day hackathon build. `STATE.md` holds the *current*
> snapshot + immediate next steps; this file holds the *whole arc* + a backlog where new
> ideas/observations land before they're scheduled. Updated when scope shifts (see CLAUDE.md §4).

**North star:** prove a cross-organization, consent-gated agent mesh for healthcare prior
auth — clinic ↔ payer negotiate in one Band room, structured (no raw PHI), private audit
channel, human-in-the-loop on borderline cases. *"13 hours → 4 minutes."*
**Moat:** cross-account consented channel + mention-scoped privacy + unified audit — what a
single linear pipeline can't give. Remove Band → consent/privacy/audit collapse.

## Milestones (by day)
- **D1 — Foundation** ✅ (mostly): env, repo scaffold, L1 protocol + tests, NOTES_BAND.
  🔲 remaining: live two-account Band connectivity spike (contact → room → message → private event). **Blocked on creds.**
- **D2 — Provider side (L2 engine + first roles):** `ProtocolAgent` base + `band_io` seam +
  `Coordinator` skeleton. Provider Intake (LangGraph) builds a FHIR request from a synthetic chart;
  Provider Counsel/Coder (Pydantic AI) catches mismatched code / missing signature pre-submit.
- **D3 — Payer side + audit:** Payer Policy Reviewer (Anthropic SDK) checks medical necessity,
  asks clarifications. Wire the private **events** audit channel (`band_send_event`) + transcript retrieval.
- **D4 — Mesh magic (riskiest):** dynamic recruiting (`lookup_peers` + `add_participant`) and
  HITL escalation (add the Medical Director as a participant). Hardening: cross-account contact
  reliability + participant ordering. ← biggest unknown, budget extra time.
- **D5 — UI + deploy:** domain-independent two-column dashboard (Clinic | Payer) + live audit
  stream over WebSocket. Deploy (Render/Railway/Fly).
- **D6 — Submission:** demo video (2–3 min), slides, cover image, README polish, MIT, partner-prize tie-ins.

## Architecture targets (layers)
- L1 `protocol/` ✅ envelopes + FSM (done).
- L2 `engine/` — `agent_base`, `coordinator`, `band_io` (D2–D4).
- L3 `domains/authbridge/` — `schema` (FHIR-shaped, synthetic), `policy` (necessity + thresholds), `roles` (the cast) (D2–D4).
- L4 `ui/` — dashboard + stream (D5).

## Submission requirements (lablab.ai — HARD gates, deadline 2026-06-19 20:30 IST)
- **Public GitHub repo** + **MIT** open source (mandatory submission fields).
- **Live demo accessible by URL** (deploy — D5, not optional).
- Pitch video ≤5 min (MP4), slide deck (PDF), 16:9 cover image (D6).
- ≥3 agents collaborating through Band (we have 5 roles).

## Cross-cutting / must-not-forget
- Synthetic data only — never real PHI.
- Partner prizes: closed models via **AI/ML API** (GPT-5.5, Claude) + one open model via **Featherless** (Appeals agent).
- Keep the demo legible in 30s (the judging "Presentation" criterion).

## Known risks
- Cross-account contact/approval flow (D1 spike de-risks this early). Fallback if needed: two
  "orgs" as roles inside one account — core (protocol/engine) unaffected; user decides.
- 8 GB VPS, no GPU — heavy extras (crewai) only when needed; all model calls remote.
- Auto-emit-thoughts flag for the demo stream is UNCONFIRMED (see NOTES_BAND).

## Backlog / parking-lot (unscheduled ideas & observations to evaluate)
> New observations the user forwards land here first (CLAUDE.md §4). Each: capture → evaluate
> (verify Band claims!) → promote to a milestone/rule/fact, or drop. Don't treat as ground truth on arrival.

- _(empty — awaiting the AI-derived observations you mentioned)_
