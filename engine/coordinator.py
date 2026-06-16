"""L2 — ``Coordinator``: the simple loop that walks a case through the L1 state machine.

Per our standing decision (Anthropic "keep agents simple"), this is a **plain loop with
explicit stop conditions**, not a heavyweight orchestrator. It is deliberately
*domain-independent* and *LLM-agnostic*: it knows nothing about roles, prompts, or models.
All it does each turn is

1. ask an injected ``runner`` for the next coordination ``Move`` given the current context,
2. **validate** that the move's transition is legal in the L1 FSM (``protocol.is_allowed``),
3. **emit** the move's envelope over Band via the ``band_io`` seam (honoring visibility), and
4. advance state + turn, appending the envelope to the case transcript.

It stops on a terminal state (``DECIDE``), when the runner returns ``None`` (nothing left to
do / stuck), or when ``max_turns`` is hit — a hard guard against runaway loops/budget. A
move proposing an illegal transition raises ``IllegalTransition`` (a protocol violation must
surface loudly, never be silently coerced).

The intelligence — which role acts, what it reasons, which model powers it — lives in the
``runner`` a domain pack supplies. That keeps this file small, auditable, and reusable across
domains. ``tools`` is any Band ``AgentToolsProtocol`` (real ``AgentTools`` or
``FakeAgentTools`` in tests); pass ``None`` to drive the FSM without touching Band.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from engine import band_io
from protocol import Envelope, State, TERMINAL, is_allowed


@dataclass
class CaseContext:
    """Everything the runner needs to decide the next move; mutated by the coordinator.

    ``domain`` is an opaque per-case object the runner owns (e.g. the working
    ``PriorAuthRequest`` plus any accumulated decision) — the engine never inspects it.
    """

    case_id: str
    state: State
    turn: int = 0
    history: list[Envelope] = field(default_factory=list)
    domain: Any = None


@dataclass(frozen=True)
class Move:
    """One coordination step proposed by the runner: an envelope + where the FSM goes next.

    ``mentions`` are participant ids to @mention (room messages only; ignored for
    private-event/audit envelopes). Routing is the runner's call, not the envelope's.
    """

    envelope: Envelope
    next_state: State
    mentions: tuple[str, ...] = ()


@dataclass
class CoordinatorResult:
    """Outcome of a run: where it ended, how many turns, the full transcript, and why it stopped."""

    final_state: State
    turns: int
    history: list[Envelope]
    stopped: str  # "terminal" | "no_move" | "max_turns"


class IllegalTransition(RuntimeError):
    """Raised when a runner proposes a transition the L1 state machine forbids."""


#: A runner produces the next ``Move`` for the current context, or ``None`` to stop.
#: Async because real runners call the LLM (via ``engine.llm``) and/or Band.
Runner = Callable[[CaseContext], Awaitable["Move | None"]]


async def run_case(
    *,
    case_id: str,
    start: State,
    runner: Runner,
    tools: Any | None = None,
    tools_for: Callable[[Envelope], Any] | None = None,
    domain: Any = None,
    max_turns: int = 24,
    on_turn: Callable[[Envelope, State], Any] | None = None,
    pause_states: frozenset[State] | set[State] | None = None,
    history: list[Envelope] | None = None,
) -> CoordinatorResult:
    """Drive one case from ``start`` until terminal / stuck / ``max_turns``.

    Transport: pass ``tools`` (one Band ``AgentToolsProtocol`` for every envelope) **or**
    ``tools_for`` (a resolver picking the transport per envelope — e.g. post provider moves
    from the clinic account and payer moves from the payer account). ``tools_for`` takes
    precedence; if both are ``None`` the FSM runs without emitting (offline).

    ``on_turn(envelope, new_state)`` — if given — is invoked after each move is emitted and
    the state advanced (it may be sync or async); it lets a caller stream the negotiation as
    it happens (e.g. persist each turn to the live audit trail). It must not raise.

    ``pause_states`` — if a move lands the case in one of these states, the loop stops with
    ``stopped="paused"`` (used for human-in-the-loop: pause at the Medical Director and let a
    person decide, then continue out-of-band). The pausing move is still emitted and recorded.

    Returns a ``CoordinatorResult`` with the transcript and the stop reason. Raises
    ``IllegalTransition`` if the runner ever proposes a move the FSM forbids, and
    ``ValueError`` if a move's envelope is misrouted (wrong ``case_id``).
    """
    # ``history`` seeds prior transcript for narration context when resuming a parked case; it is
    # NOT re-emitted. ``turn`` still starts at 0 — callers offset audit turns across segments.
    ctx = CaseContext(case_id=case_id, state=start, turn=0, history=list(history or []), domain=domain)

    while True:
        if ctx.state in TERMINAL:
            return CoordinatorResult(ctx.state, ctx.turn, ctx.history, "terminal")
        if ctx.turn >= max_turns:
            return CoordinatorResult(ctx.state, ctx.turn, ctx.history, "max_turns")

        move = await runner(ctx)
        if move is None:
            return CoordinatorResult(ctx.state, ctx.turn, ctx.history, "no_move")

        if not is_allowed(ctx.state, move.next_state):
            raise IllegalTransition(
                f"{ctx.state.value} -> {move.next_state.value} is not a legal transition "
                f"(case {case_id}, turn {ctx.turn})"
            )
        if move.envelope.case_id != case_id:
            raise ValueError(
                f"move envelope case_id {move.envelope.case_id!r} != coordinator case {case_id!r}"
            )

        transport = tools_for(move.envelope) if tools_for is not None else tools
        if transport is not None:
            await band_io.emit(transport, move.envelope, mentions=list(move.mentions))

        ctx.history.append(move.envelope)
        ctx.state = move.next_state
        ctx.turn += 1

        if on_turn is not None:
            result = on_turn(move.envelope, ctx.state)
            if inspect.isawaitable(result):
                await result

        if pause_states and ctx.state in pause_states:
            return CoordinatorResult(ctx.state, ctx.turn, ctx.history, "paused")
