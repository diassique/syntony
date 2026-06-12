# Syntony

**A domain-independent coordination protocol and engine for AI agents.**

Syntony is a thin protocol (typed envelopes + a conversation state machine) and a
reusable engine (a base agent + a coordinator that runs the state machine, recruits
specialists, and escalates to humans). It is built on top of [Band](https://band.ai)
— the agentic mesh that provides the transport: accounts, rooms, `@mention` routing,
bilateral contacts, an event journal, and REST/WebSocket APIs.

Domains plug in as **packs**: each pack supplies its own payload schema, policies,
agent roles, and thresholds. The protocol and engine never hard-code domain logic.

## Reference application: AuthBridge

**AuthBridge** is the first reference application built on Syntony — cross-organization
**prior authorization** for healthcare. A clinic account and a payer account negotiate
a prior-auth case in a shared room: specialized agents exchange structured requests
without passing raw PHI, a human medical director is looped in on borderline cases,
and every step lands in a private audit channel.

Future packs (e.g. `contracts/`) attach the same way — no engine changes required.

## Layers

```
L0  Band            transport (rooms, mentions, contacts, events, REST/WS) — external
L1  protocol/       typed envelopes + conversation state machine (domain-independent)
L2  engine/         ProtocolAgent base + Coordinator (FSM), recruit / escalate
L3  domains/        domain packs: schema + policies + roles + thresholds
L4  ui/             domain-independent dashboard + live audit stream
```

## Getting started

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your Band + provider credentials
pytest -q                     # run the test suite
```

## License

MIT — see [LICENSE](LICENSE).
