"""L1 protocol — the conversation **state machine**, expressed as *data only*.

This module declares the coordination states a case moves through and the table of
allowed transitions between them. It deliberately contains **no executor**: nothing
here drives an agent, calls Band, or mutates anything. The engine (L2) reads this
table to decide what is legal; keeping it as inert data makes the protocol auditable
and trivial to test.

States are domain-independent. A domain pack (L3) maps its roles/policies onto these
states but does not add new ones here.
"""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    """Coordination states of a case."""

    FRAME = "FRAME"        # case is being framed/opened
    PROPOSE = "PROPOSE"      # a party assembles a structured proposal
    REVIEW = "REVIEW"       # the counterparty reviews the proposal
    REVISE = "REVISE"       # proposer revises after a verdict/feedback
    INFO = "INFO"         # a clarification request/response is outstanding
    RECRUIT = "RECRUIT"      # another specialist is being pulled in
    ESCALATE = "ESCALATE"     # case routed toward a human/arbiter
    ARBITER = "ARBITER"      # human/arbiter is deciding
    DECIDE = "DECIDE"       # terminal: a binding decision has been recorded


#: Allowed transitions as plain data: ``state -> set of states reachable in one step``.
#: ``DECIDE`` is terminal (no outgoing edges). This is intentionally permissive about
#: detours (INFO / RECRUIT / ESCALATE can interrupt the main PROPOSE→REVIEW→REVISE loop)
#: but never lets a case skip straight to a decision without passing through REVIEW or
#: ARBITER.
TRANSITIONS: dict[State, frozenset[State]] = {
    State.FRAME: frozenset({State.PROPOSE}),
    State.PROPOSE: frozenset({State.REVIEW, State.INFO}),
    State.REVIEW: frozenset({State.REVISE, State.INFO, State.RECRUIT, State.ESCALATE, State.DECIDE}),
    State.REVISE: frozenset({State.REVIEW, State.INFO}),
    State.INFO: frozenset({State.PROPOSE, State.REVIEW, State.REVISE}),
    State.RECRUIT: frozenset({State.REVIEW, State.ESCALATE}),
    State.ESCALATE: frozenset({State.ARBITER}),
    State.ARBITER: frozenset({State.DECIDE}),
    State.DECIDE: frozenset(),
}

#: The single terminal state.
TERMINAL: frozenset[State] = frozenset({State.DECIDE})


def is_allowed(src: State, dst: State) -> bool:
    """Return whether ``src -> dst`` is a declared legal transition. Pure lookup."""

    return dst in TRANSITIONS.get(src, frozenset())
