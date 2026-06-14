"""L2 — concrete Band transport: an ``AgentToolsProtocol`` backed by the REST client.

``band_io.emit`` is generic over a ``tools`` object exposing ``send_message`` / ``send_event``.
Inside a running WS adapter that object is Band's ``AgentTools``; but we drive the negotiation
from a script over REST (exactly as the live spikes did — see NOTES_BAND "VERIFIED LIVE"). This
module provides ``RestRoomTools``: a thin async shim that fulfils that protocol by calling the
confirmed ``agent_api_messages`` / ``agent_api_events`` REST methods on a ``RestClient`` bound to
one account + one room. Sync REST calls run off the event loop via ``asyncio.to_thread``.

It also maps our logical mention ids (role ids like ``payer.reviewer``) to the Band agent UUIDs
that actually route — we have two Band agents (clinic, payer) playing several logical roles each.
"""

from __future__ import annotations

import asyncio
from typing import Any

from band.client.rest import (  # confirmed imports — see spikes 03/04 + NOTES_BAND
    ChatEventRequest,
    ChatMessageRequest,
    ChatMessageRequestMentionsItem,
    ChatRoomRequest,
    ParticipantRequest,
    RestClient,
)


def agent_client(api_key: str, base_url: str = "https://app.band.ai") -> RestClient:
    """A REST client authenticated with a Band **agent** key (agent_api_* surface)."""
    return RestClient(api_key=api_key, base_url=base_url)


def ensure_room(creator: RestClient, *participant_agent_ids: str, room_id: str | None = None) -> str:
    """Return ``room_id`` if given, else create a fresh chat (as ``creator``) and add the
    given external agent ids as participants. Mirrors spike 03/04 exactly."""
    if room_id:
        return room_id
    created = creator.agent_api_chats.create_agent_chat(chat=ChatRoomRequest())
    rid = created.data.id
    for pid in participant_agent_ids:
        creator.agent_api_participants.add_agent_chat_participant(
            chat_id=rid, participant=ParticipantRequest(participant_id=pid, role="member")
        )
    return rid


class RestRoomTools:
    """Fulfils Band's AgentToolsProtocol (the parts ``band_io.emit`` uses) over REST.

    Bound to one ``RestClient`` (one account) and one ``room_id``. ``mention_map`` translates
    logical role ids → Band agent UUIDs so @mentions actually route across accounts.
    """

    def __init__(
        self,
        client: RestClient,
        room_id: str,
        *,
        mention_map: dict[str, str] | None = None,
        self_id: str | None = None,
        default_mention: str | None = None,
    ):
        self._client = client
        self._room = room_id
        self._mention_map = mention_map or {}
        self._self_id = self_id  # this account's agent uuid; Band rejects self-mentions
        self._default_mention = default_mention  # counterparty uuid; Band requires >=1 mention

    async def send_message(self, content: str, mentions: list[Any] | None = None) -> Any:
        ids: list[str] = []
        for m in mentions or []:
            raw = m.get("id") if isinstance(m, dict) else m
            target = self._mention_map.get(raw, raw)
            if target and target != self._self_id and target not in ids:
                ids.append(target)  # drop self-mentions (Band: cannot_mention_self)
        # Band requires >=1 mention; if all targets were same-account, address the counterparty
        # (every message in this shared room is cross-org anyway).
        if not ids and self._default_mention:
            ids = [self._default_mention]
        items = [ChatMessageRequestMentionsItem(id=i) for i in ids]
        message = ChatMessageRequest(content=content, mentions=items)

        def _do():
            return self._client.agent_api_messages.create_agent_chat_message(chat_id=self._room, message=message)

        return await asyncio.to_thread(_do)

    async def send_event(self, content: str, message_type: str, metadata: dict | None = None) -> Any:
        def _do():
            return self._client.agent_api_events.create_agent_chat_event(
                chat_id=self._room,
                event=ChatEventRequest(content=content, message_type=message_type, metadata=metadata or {}),
            )

        return await asyncio.to_thread(_do)
