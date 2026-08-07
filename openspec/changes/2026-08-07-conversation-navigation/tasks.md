## 1. Schema and migrations

- [ ] 1.1 Add `title` (nullable) and `origin` (non-null, default `operator`) to `Conversation` in `hub/hub/db/models.py`, with a check constraint restricting `origin` to `operator|peer|handoff|spec|job`
- [ ] 1.2 Migration `0035_add_conversation_title_and_origin.py`, guarding for a missing `conversations` table the way `0033`/`0034` do
- [ ] 1.3 Add `conversation_id` (nullable, indexed) to `Question`, `PermissionRequest` and `UnaskedQuestion`
- [ ] 1.4 Migration `0036_add_conversation_id_to_blocking_tables.py`, with the same missing-table guard
- [ ] 1.5 Add the project-level title-generation setting to the project settings model
- [ ] 1.6 Migration `0037_add_project_title_generation_setting.py`, defaulting to truncation
- [ ] 1.7 Move the head assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py` to `0037`
- [ ] 1.8 Run each migration against a real database from `0031` forward and confirm no `NoSuchTableError`

## 2. Conversation lifecycle — backend

- [ ] 2.1 `new_conversation()` in `hub/hub/conversations.py` takes a required `origin`; update every call site, passing `peer` from `hub/hub/api/v1/messages.py`
- [ ] 2.2 Pure `title_from_message(text) -> str` helper: truncate at a word boundary within the limit, no partial words; unit-tested with no database
- [ ] 2.3 Set the title when the first message of a conversation is recorded; leave an existing title untouched
- [ ] 2.4 Add `title_set_by_operator` so a generated title can never overwrite an operator's
- [ ] 2.5 `PATCH /projects/{id}/agent/{agent}/conversations/{cid}` for rename — reject empty and over-length with a stated reason
- [ ] 2.6 `archivable(conversation) -> Optional[str]` returning the obstruction reason: unfinished run, or undelivered `InboundQueueEntry` rows
- [ ] 2.7 `POST .../conversations/{cid}/archive` and `.../unarchive`, refusing with 409 and the reason from 2.6
- [ ] 2.8 Conversation listing excludes `archived` by default; `?lifecycle=archived` returns them with a count
- [ ] 2.9 `hub/hub/api/v1/messages.py` refuses a send whose recipient conversation is archived, returning the cause, the instruction to start a new conversation, and the submitted content restated verbatim
- [ ] 2.10 Mirror that refusal through the MCP `send_message` adapter and assert both paths carry the same three parts
- [ ] 2.11 Record `conversation_id` when creating `Question`, `PermissionRequest` and `UnaskedQuestion`, taken from the opening run
- [ ] 2.12 Expose per-conversation attention state on the conversation listing: `running`, `waiting`, or `idle`

## 3. Conversation lifecycle — tests

- [ ] 3.1 `test_conversation_titles.py` — truncation at a word boundary, first-message titling, operator title never overwritten, empty/over-length rename rejected
- [ ] 3.2 `test_conversation_origin.py` — operator vs peer at creation, immutability across rename/archive/unarchive
- [ ] 3.3 `test_conversation_archive.py` — archive/unarchive round trip, listing exclusion, archived conversation still readable
- [ ] 3.4 `test_conversation_archive_refusal.py` — live run refuses, undelivered queue entry refuses, neither is mutated, success once cleared
- [ ] 3.5 `test_archived_send_refusal.py` — HTTP and MCP both fail with cause + instruction + verbatim content; no message, no queue entry, no rehoming
- [ ] 3.6 `test_conversation_attention.py` — each of question, permission request and unasked question raises `waiting`; answering clears it; running and waiting are distinct
- [ ] 3.7 Extend `test_bola.py` for the new routes — cross-project access refused

## 4. Title generation

- [ ] 4.1 One-shot titling spawn: reuse an existing project runner, bound to no conversation, no session resume, bounded timeout
- [ ] 4.2 Trigger it after the agent's first response is recorded, only when the setting is on and the title is not operator-set
- [ ] 4.3 Failure and timeout are no-ops — the truncated title stands and the agent's run is untouched
- [ ] 4.4 Bound concurrent titling spawns so many simultaneous conversation starts cannot fan out unboundedly
- [ ] 4.5 `test_title_generation.py` — off by default; on, replaces the truncated title; never overwrites an operator title; no timeline entry; no change to agent context usage; failure leaves the truncated title

## 5. Navigation — the tree gains a level

- [ ] 5.1 `useAgentConversations` becomes usable per-agent from the rail, or add a project-wide conversation listing if per-agent fetches prove too chatty — decide from a measured render, not in advance
- [ ] 5.2 `Sidebar.tsx`: agent rows gain an expander and a name button as separate controls, matching the project row's existing split
- [ ] 5.3 Render an agent's open conversations as children, newest activity first, labelled by title
- [ ] 5.4 Cap the list at a fixed number with an expander stating how many remain
- [ ] 5.5 Per-conversation attention indicator, with running and waiting visually distinct
- [ ] 5.6 Persist agent expansion alongside the existing `aw.projectRailCollapsed` state

## 6. Navigation — the recency view

- [ ] 6.1 View toggle in the rail; agent tree is the default; the choice persists to localStorage
- [ ] 6.2 Recency list of the project's conversations across agents, most recent activity first
- [ ] 6.3 A persistent 2px leading edge in the owning agent's colour, matching `agentColorVars` — no hover tint
- [ ] 6.4 The same attention indicator as the tree

## 7. Row menus and the new-conversation surface

- [ ] 7.1 Shared row-menu component on `@radix-ui/react-dropdown-menu`, opened from a visible control on the row, keyboard-reachable, returning focus on dismiss
- [ ] 7.2 Conversation menu: rename (inline edit or dialog), archive
- [ ] 7.3 Agent menu: new conversation, agent settings, show archived (N)
- [ ] 7.4 Agent settings opens `AgentInfoTab` in a dialog without unmounting the open conversation
- [ ] 7.5 New-conversation surface: composer-primary, agent pre-bound when started from an agent row
- [ ] 7.6 Started from the recency view, the surface requires an agent to be chosen before sending
- [ ] 7.7 Navigating away without sending leaves no conversation record

## 8. Selection lifts into the destination

- [ ] 8.1 Remove `selectedConversationId` from `AgentOutputPanel`; the conversation arrives as a prop
- [ ] 8.2 Move the auto-select-most-recent behaviour into destination resolution, and make it not fire when the destination is deliberately the new-conversation surface
- [ ] 8.3 Remove `onConversationChange`'s round trip; navigation writes the destination directly
- [ ] 8.4 Confirm the existing effect that seeds runtime overrides still fires on conversation change
- [ ] 8.5 Existing frontend suites green at each step — do not land 8.1–8.3 as one commit

## 9. Controls rehoused, dead surfaces removed

- [ ] 9.1 Durable handoff becomes a labelled control on the conversation header beside "Fold all turns", disabled with its reason when unavailable
- [ ] 9.2 Remove "New conversation", the conversation entries, "Handoff" and "Agent details" from `ConversationControls.tsx`
- [ ] 9.3 Delete the now-empty conversation-actions overflow menu
- [ ] 9.4 Delete `AgentsPage.tsx` and `AgentDetailPanel.tsx` and their tests; confirm nothing imports them
- [ ] 9.5 Update any frontend suite that mocked the overflow menu

## 10. Frontend tests

- [ ] 10.1 `conversationTree.test.tsx` — conversations listed under an agent, newest first, titled; expander toggles without navigating; agent name opens the most recent conversation
- [ ] 10.2 `conversationCap.test.tsx` — the remainder is behind an expander stating the count, never silently dropped
- [ ] 10.3 `recencyView.test.tsx` — toggle, persistence, cross-agent ordering, persistent agent colour with no hover dependency
- [ ] 10.4 `conversationAttention.test.tsx` — a question in one conversation shows as waiting while a different conversation is open
- [ ] 10.5 `rowMenus.test.tsx` — both menus keyboard-operable, focus returns to trigger, agent settings do not unmount the conversation
- [ ] 10.6 `newConversationSurface.test.tsx` — agent pre-bound from the tree; agent required from recency; abandonment creates nothing
- [ ] 10.7 `handoffPlacement.test.tsx` — handoff present and labelled on the header at rest; disabled with reason when unavailable
- [ ] 10.8 Assert no conversation identifier appears as a label anywhere in the rail

## 11. Verification

- [ ] 11.1 `pytest hub/tests/ -q` green; `pytest tests/ -q` green
- [ ] 11.2 `cd hub/ui && npx vitest run` green; `npx tsc --noEmit` clean
- [ ] 11.3 `ruff check hub/hub/` introduces no new errors beyond the 3 pre-existing
- [ ] 11.4 `npx openspec validate --specs --strict` passes
- [ ] 11.5 `npm run build`, copy `hub/ui/dist` over `hub/hub/static/ui`, confirm with `diff -rq`
- [ ] 11.6 Live: three agents, several conversations each — expand, rename, archive, unarchive, and confirm a blocked question in a background conversation is visible in the rail without opening it
- [ ] 11.7 Live: archiving is refused for a running conversation and for one holding an undelivered queue entry, each with its reason
- [ ] 11.8 Live: an agent messaging an archived conversation receives the cause, the instruction, and its own content back
- [ ] 11.9 Live: enable title generation and confirm the title upgrades with no timeline entry and no change to the agent's context usage
- [ ] 11.10 Check light mode for every new surface — it was not checked in the previous change
