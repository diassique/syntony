# STATE — project resume anchor

> **Read this first** at the start of every session. It's the living "where we are" doc.
> Companions: `CLAUDE.md` (standing rules), `PLAN.md` (roadmap + backlog),
> `NOTES_BAND.md` (confirmed Band API facts), `README.md` (public overview).
> Keep it short; update the **Status** + **Devlog** whenever a step finishes.

**Last updated:** 2026-06-13 (Day 2)
**Phase:** Day 2 — offline engine/domain built & tested. Live runs blocked on Band creds + AIML key.
**⏰ Hard deadline:** 2026-06-19 20:30 IST (build window 12–19 Jun).
**Submission requirements (lablab.ai):** public GitHub repo · MIT open source · live demo URL (deploy)
· pitch video ≤5 min · PDF slides · 16:9 cover · ≥3 agents collaborating via Band.

---

## What this is (10-second version)
**Syntony** = domain-independent agent-coordination protocol + engine, built on **Band**
(band.ai agentic mesh). **AuthBridge** = first reference app (cross-org healthcare prior
authorization). Layers built bottom-up: L1 protocol → L2 engine → L3 domains → L4 ui.

## Environment / how to run
- VPS: Ubuntu, Python 3.12, no GPU (all model calls are remote). Repo: `/root/syntony`.
- Venv: `.venv` (pip 24.0). Activate-free usage: `.venv/bin/python ...`.
- Tests: `.venv/bin/python -m pytest -q`  → currently **4 passed**.
- Connectivity spike (needs `.env`): `.venv/bin/python spikes/00_preflight.py`.
- Secrets live in `.env` (gitignored). Template: `.env.example`.

## Status by layer
| Layer | Path | State |
|---|---|---|
| L1 protocol | `protocol/` | ✅ done — `Envelope` + FSM (data only), tested |
| L2 engine | `engine/` | 🟡 `band_io` done (envelope↔Band, tested w/ FakeAgentTools); `agent_base` = `RoleSpec`/`Framework` + lazy `build_adapter` (framework wiring TODO); `coordinator` still stub |
| L3 domains | `domains/authbridge` | 🟡 `schema` (FHIR-ish) + `cases` (synthetic) + `policy` (completeness + necessity) + `roles` (cast w/ prompts) done & tested; `contracts` still placeholder |
| L4 ui | `ui/` | ⬜ empty (Day 5) |
| spikes | `spikes/` | 🟡 `00_preflight` + `_common` ready; contact-dance planned in `spikes/README.md` |

**Tests: 18 passed** (`protocol`, `authbridge`, `band_io`, `roles`).

## Key decisions (don't relitigate)
- Names: engine/project = **`syntony`** (renamed from working name "concord" on 2026-06-12),
  prior-auth reference domain = **`authbridge`**. Tagline: *agents tuning to the same frequency*.
- **Agent frameworks (2026-06-13, research-backed):** 3 frameworks for heterogeneity —
  LangGraph (Intake, stateful+HITL), Pydantic AI (Counsel + Reviewer, typed, model-agnostic),
  Letta/CrewAI (Appeals, open model). Prefer Pydantic AI/LangGraph over native AnthropicAdapter
  because they accept a `base_url` client → route all closed models via **AI/ML API**
  (`https://api.aimlapi.com/v1`, partner prize); Featherless for the open model (2nd prize).
- **Coordinator = simple loop** (Anthropic "keep agents simple"): explicit stop conditions +
  max-turns/budget guards, not a heavy orchestrator.
- Demo "live thoughts" stream = `AdapterFeatures(emit={Emit.EXECUTION, Emit.THOUGHTS})`.
- Band tools are **`band_*`** prefixed, NOT `thenvoi_*` (old pre-rebrand name). See NOTES_BAND.
- pip package is **`band-sdk`**, import `band`. Heavy framework extras (crewai etc.) deferred to Day 2+.
- LLM keys never go to Band — called inside our adapter from `.env`.

## Open questions / risks (verify live)
- [ ] Does contact **approve** work from B's Human key in code, or require a manual UI click? ← Day-1 spike's core unknown.
- [ ] Can the room creator pre-add a **cross-account** participant, or must each side add itself?
- [ ] Auto-emit-thoughts flag for the demo stream (`AdapterFeatures`/`Emit`/`SessionConfig`) — Day 2.

## ⛔ Current blocker (live runs only)
Offline engine/domain work can continue freely (FakeAgentTools). What needs credentials:
1. **Two Band accounts** in `.env` (clinic + payer): Human/User key + a registered External
   Agent (UUID + key) + public handle each. → connectivity spike + live agents.
2. **`AIML_API_KEY`** (AI/ML API) for the first live LLM call. Featherless key later (Appeals).
Registration steps: see `.env.example` comments.

## Next steps (in order)
Offline (no creds needed):
1. `engine/llm.py` — provider factory: build OpenAI-compatible client at AI/ML API base_url
   (for PydanticAI/LangGraph adapters). Code + light tests.
2. `engine/coordinator.py` — simple FSM-driving loop (max-turns/stop guards), tested w/ FakeAgentTools.
Needs creds:
3. User registers 2 Band accounts + AIML key → fills `.env`.
4. `spikes/00_preflight.py`, then contact-dance spikes (01 contact → 02 room → 03 message → 04 event).
5. `pip install 'band-sdk[pydantic-ai,langgraph]'` → wire `build_adapter` → first live agent (PydanticAI).
6. (Housekeeping) First git commit once the user asks (exclude `.env`).

## Devlog
- **2026-06-12 (Day 1):** Env + venv + repo scaffold. Installed & inspected `band-sdk` 1.0.0;
  Band prod reachable. Wrote L1 protocol (Envelope + FSM) + tests (4 pass). Filled NOTES_BAND.md.
  Wrote `.env.example` + preflight spike. Paused before live two-account test (no creds yet).
- **2026-06-12 (Day 1, later):** Renamed project `concord` → **`syntony`** (dir `/root/syntony`,
  all docs/docstrings/LICENSE/memory). Venv kept (symlink-based). Tests still green.
- **2026-06-12 (Day 1, docs):** Added `CLAUDE.md` (standing rules + living-docs maintenance
  protocol) and `PLAN.md` (6-day roadmap + backlog). Established doc routing (CLAUDE.md §4).
- **2026-06-13 (Day 2):** Web-researched agent frameworks → fixed framework decision (see Key
  decisions). Built offline-testable L2/L3: `band_io`, `agent_base` (RoleSpec/Framework/build_adapter),
  authbridge `schema`/`cases`/`policy`/`roles`. Confirmed `Emit.{EXECUTION,THOUGHTS}` + AI/ML API
  base_url routing in NOTES_BAND. Tests 4 → 18. Live agent run still blocked on Band creds; framework
  adapter wiring (PydanticAI/LangGraph) deferred until extras+keys present (build_adapter raises NotImplementedError).
