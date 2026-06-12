# CLAUDE.md — operating rules for this project (auto-loaded each session)

> These are my standing instructions for the **Syntony** project. I read and obey them
> every session. **I keep this file and the other living docs up to date** — see the
> Maintenance protocol at the bottom. This is the rules layer; status lives in `STATE.md`.

## 0. Start-of-session ritual
1. Read **`STATE.md`** (where we are, blockers, next steps).
2. Read this file (rules) + skim `PLAN.md` (roadmap/backlog).
3. Only then act.

## 1. Hard rules (never break)
- **Never invent or guess Band APIs.** Band is niche; my prior knowledge is unreliable.
  Confirm against the installed `band-sdk` (inspect sources) and/or docs before writing
  Band code. Confirmed facts go in `NOTES_BAND.md`; unconfirmed ones are marked UNCONFIRMED.
  If something can't be confirmed → STOP and ask, don't fabricate names.
- **Secrets only in `.env`** (gitignored). Never hardcode or commit keys.
- **Python 3.11+, venv (`.venv`), license MIT.**
- **LLM keys never go to Band** — called inside our adapter from `.env`.
- **Meaningful agent names** (not "Assistant"/"Bot") — Band routes on them.
- **Commit/push only when the user asks.** No Co-Authored-By trailer (user is sole author).

## 2. Working style
- Small, verifiable steps. Show commands and their output. Ask before destructive/overwriting actions.
- Don't build ahead of scope (no engine/domain/UI logic until the relevant day & a "go").
- Recommend, don't survey: when a decision is mine to make sensibly, pick and say why.

## 3. Document map (keep roles distinct — don't duplicate, cross-link instead)
| Doc | Role | I update it… |
|---|---|---|
| `CLAUDE.md` (this) | Standing rules / working agreement | whenever a rule/convention/decision is added or changes |
| `STATE.md` | Resume anchor: current status, blockers, next steps, devlog | after every finished step/day |
| `PLAN.md` | 6-day roadmap, milestones, backlog/parking-lot for incoming ideas | when scope/plan shifts or new ideas arrive |
| `NOTES_BAND.md` | Confirmed Band API facts (+ UNCONFIRMED list) | on every new Band finding |
| `README.md` | Public-facing overview (repo/judges) | rarely, on substance changes |

## 4. Maintenance protocol (the meta-rule — DO THIS CONTINUOUSLY)
**When the user sends information, I immediately route it to the right doc and confirm what I changed.** Mapping:
- A **rule / preference / "from now on…"** → add/edit in **§1–§2 of this file**.
- A **decision** (naming, tech choice, trade-off) → `STATE.md` "Key decisions" (one line, dated).
- A **confirmed Band fact** → `NOTES_BAND.md`. An unconfirmed one → its UNCONFIRMED list.
- A **plan/scope change or a new idea/observation to evaluate** → `PLAN.md` (Backlog if not yet decided).
- **Status/progress** → `STATE.md` (Status + Devlog).

Rules for keeping this trustworthy:
- Edit in place; don't append duplicates. If new info contradicts an old entry, **replace** it and note the change in the dated devlog.
- Keep entries terse (one line where possible). These docs are context, not prose.
- After folding something in, tell the user in one line: *"recorded X in <doc>"*.
- If incoming info is ambiguous or conflicts with a hard rule, ask before recording.
- Treat AI-derived observations the user forwards as **inputs to evaluate**, not ground truth:
  park them in `PLAN.md` Backlog, and verify (esp. anything about Band) before promoting to a rule/fact.
