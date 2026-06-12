# spikes/ — throwaway connectivity checks (not production code)

Goal of Day 1: prove the core hypothesis — **two independent Band accounts can
establish a bilateral contact, share one room, exchange a routed message, and keep a
private event off the counterparty's view while it stays retrievable for audit.**

All calls below are confirmed against `band-sdk` 1.0.0 (see `../NOTES_BAND.md`).
Run everything **from the repo root** with the venv:
`.venv/bin/python spikes/00_preflight.py`

## Order

- **00_preflight.py** ✅ written — auth both accounts, print handles/ids. Run this first.
- **01_contact.py** ⏳ after preflight — A → contact request, B → approve:
  - A: `human_api_contacts.create_contact_request(contact_request={recipient_handle, message})`
  - B: `human_api_contacts.list_received_contact_requests()` → `approve_contact_request(id)`
  - verify: both sides `list_my_contacts()` show each other.
  - ⚠️ open question: does approve work purely from B's Human key (code), or does B need to
    click **Approve** in the Contacts tab at app.band.ai? Decide this empirically here.
- **02_room.py** ⏳ — A: `human_api_chats.create_my_chat_room(chat={})` → room id;
  add participants via `human_api_participants.add_my_chat_participant(chat_id, {participant_id, role})`.
  - ⚠️ open question: can A pre-add B's agent (cross-account) directly, or must B add itself?
- **03_message.py** ⏳ — A: `human_api_messages.send_my_chat_message(chat_id, {content, mentions:[{id}]})`;
  B: `human_api_messages.list_my_chat_messages(chat_id)` → confirm receipt.
- **04_event.py** ⏳ — agent on A: `agent_api_events.create_agent_chat_event(chat_id, {content, message_type:'thought'})`;
  confirm B's `list_my_chat_messages(message_type='text')` does NOT include it, but
  `message_type='thought'` (audit) DOES.
- **(opt) 05_agents.py** — tiny `SimpleAdapter` agents over WebSocket (`Agent.create(...).run()`),
  only if we want to prove the live WS path beyond REST.

Steps 01–04 are intentionally **not written yet**: their exact request shapes for the
cross-account case depend on what 00/01 reveal about handles and contact approval.
Write them once preflight + contact are green.
