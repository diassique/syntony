"""L1 protocol — the **envelope**: the single typed unit every Syntony agent exchanges.

Pure data, no behavior and no domain knowledge. An ``Envelope`` wraps a domain
``payload`` (an opaque ``dict`` at this layer) with the routing/coordination metadata
the engine and state machine need: which case, which turn, who authored it, what kind
of move it is, and whether it is visible in the room or kept on the private event
(audit) channel.

Domain packs (L3) define and validate the *contents* of ``payload``; this layer only
guarantees the envelope around it is well-formed and serializable.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Kind(str, Enum):
    """The kind of coordination move an envelope carries (domain-independent)."""

    CASE_OPEN = "CASE_OPEN"            # a new case is framed and opened
    PROPOSAL = "PROPOSAL"             # a structured proposal toward resolution
    VERDICT = "VERDICT"              # a reviewer's assessment of a proposal
    INFO_REQUEST = "INFO_REQUEST"         # a request for missing information
    INFO_RESPONSE = "INFO_RESPONSE"        # a response supplying requested information
    RECRUIT_REQUEST = "RECRUIT_REQUEST"      # ask to pull in another specialist agent
    ESCALATION = "ESCALATION"           # hand a borderline case to a human/arbiter
    DECISION = "DECISION"             # the final, binding outcome of the case


class Visibility(str, Enum):
    """Where an envelope is delivered.

    ``room`` — posted as a normal message, routed by ``@mention`` to participants.
    ``private_event`` — written to the private event/audit channel; the counterparty
    does not receive it as chat (used for one side's internal strategy + audit trail).
    """

    ROOM = "room"
    PRIVATE_EVENT = "private_event"


class Envelope(BaseModel):
    """A single coordination message. Pure data — see module docstring."""

    case_id: str = Field(..., description="Stable id grouping all envelopes of one case.")
    turn: int = Field(..., ge=0, description="Monotonic turn counter within the case.")
    author: str = Field(..., description="Logical role/agent id that produced this envelope.")
    kind: Kind = Field(..., description="The coordination move this envelope represents.")
    visibility: Visibility = Field(
        default=Visibility.ROOM,
        description="room (mentioned chat) or private_event (audit channel).",
    )
    payload: dict = Field(
        default_factory=dict,
        description="Opaque domain data; shape validated by the domain pack (L3), not here.",
    )
