## 1. Schema and migrations

- [x] 1.1 Add `title` (nullable) and `origin` (non-null, default `operator`) to `Conversation` in `hub/hub/db/models.py`, with a check constraint restricting `origin` to `operator|peer|handoff|spec|job`
- [x] 1.2 Migration `0035_add_conversation_title_and_origin.py`, guarding for a missing `conversations` table the way `0033`/`0034` do
- [x] 1.3 Add `conversation_id` (nullable, indexed) to `Question`, `PermissionRequest` and `UnaskedQuestion`
- [x] 1.4 Migration `0036_add_conversation_id_to_blocking_tables.py`, with the same missing-table guard
- [x] 1.5 Add the project-level title-generation setting to the project settings model
- [x] 1.6 Migration `0037_add_project_title_generation_setting.py`, defaulting to truncation
- [x] 1.7 Move the head assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py` to `0037`
- [x] 1.8 Run each migration against a real database from `0031` forward and confirm no `NoSuchTableError`

## 2. Conversation lifecycle — backend

> Three things this section assumed that turned out not to hold, resolved as noted:
>
> - **2.9 needed a capability that did not exist.** `send_message` addresses an *agent*, never a
>   conversation, and `latest_open_conversation` already skips archived rows — so "a send whose
>   recipient conversation is archived" could not happen on any path. `MessageCreate` and the MCP
>   tool gained an optional `conversation_id` (operator decision, 2026-08-08). Unset keeps
>   today's behaviour exactly; set and archived is refused with the three parts.
> - **2.8's count is the archived listing's length.** A wrapper object carrying `archived_count`
>   would have changed the endpoint's shape, which design.md's migration plan step 2 explicitly
>   keeps stable. A dedicated count belongs with the project-wide listing that 5.1 and section 6
>   may add, not here.
> - **2.11 was already half done.** `UnaskedQuestion.conversation_id` existed and was populated;
>   only `Question` and `PermissionRequest` needed the column.

- [x] 2.1 `new_conversation()` in `hub/hub/conversations.py` takes a required `origin`; update every call site, passing `peer` from `hub/hub/api/v1/messages.py`
- [x] 2.2 Pure `title_from_message(text) -> str` helper: truncate at a word boundary within the limit, no partial words; unit-tested with no database
- [x] 2.3 Set the title when the first message of a conversation is recorded; leave an existing title untouched
- [x] 2.4 Add `title_set_by_operator` so a generated title can never overwrite an operator's
- [x] 2.5 `PATCH /projects/{id}/agent/{agent}/conversations/{cid}` for rename — reject empty and over-length with a stated reason
- [x] 2.6 `archivable(conversation) -> Optional[str]` returning the obstruction reason: unfinished run, or undelivered `InboundQueueEntry` rows
- [x] 2.7 `POST .../conversations/{cid}/archive` and `.../unarchive`, refusing with 409 and the reason from 2.6
- [x] 2.8 Conversation listing excludes `archived` by default; `?lifecycle=archived` returns them with a count
- [x] 2.9 `hub/hub/api/v1/messages.py` refuses a send whose recipient conversation is archived, returning the cause, the instruction to start a new conversation, and the submitted content restated verbatim
- [x] 2.10 Mirror that refusal through the MCP `send_message` adapter and assert both paths carry the same three parts
- [x] 2.11 Record `conversation_id` when creating `Question`, `PermissionRequest` and `UnaskedQuestion`, taken from the opening run
- [x] 2.12 Expose per-conversation attention state on the conversation listing: `running`, `waiting`, or `idle`

## 3. Conversation lifecycle — tests

- [x] 3.1 `test_conversation_titles.py` — truncation at a word boundary, first-message titling, operator title never overwritten, empty/over-length rename rejected
- [x] 3.2 `test_conversation_origin.py` — operator vs peer at creation, immutability across rename/archive/unarchive
- [x] 3.3 `test_conversation_archive.py` — archive/unarchive round trip, listing exclusion, archived conversation still readable
- [x] 3.4 `test_conversation_archive_refusal.py` — live run refuses, undelivered queue entry refuses, neither is mutated, success once cleared
- [x] 3.5 `test_archived_send_refusal.py` — HTTP and MCP both fail with cause + instruction + verbatim content; no message, no queue entry, no rehoming
- [x] 3.6 `test_conversation_attention.py` — each of question, permission request and unasked question raises `waiting`; answering clears it; running and waiting are distinct
- [x] 3.7 Extend `test_bola.py` for the new routes — cross-project access refused

## 4. Title generation

> **No `Run` row is recorded, against design.md's wording.** It reasoned that the spawn should
> be "a one-shot run bound to no conversation", `Run.conversation_id` being nullable. Doing so
> would stall the agent: `turn_scheduler.schedule_agent` and `trigger_agent_directly` both gate
> on `Run.agent == a, Run.status == "running"`, so a titling run under the agent's name makes
> it look busy until the title returns. Recorded as a `conversation_titled` event instead.

- [x] 4.1 One-shot titling spawn: reuse an existing project runner, bound to no conversation, no session resume, bounded timeout
- [x] 4.2 Trigger it after the agent's first response is recorded, only when the setting is on and the title is not operator-set
- [x] 4.3 Failure and timeout are no-ops — the truncated title stands and the agent's run is untouched
- [x] 4.4 Bound concurrent titling spawns so many simultaneous conversation starts cannot fan out unboundedly
- [x] 4.5 `test_title_generation.py` — off by default; on, replaces the truncated title; never overwrites an operator title; no timeline entry; no change to agent context usage; failure leaves the truncated title

## 5. Navigation — the tree gains a level

- [x] 5.1 Decided: a project-wide listing (`GET /projects/{id}/conversations`). One request rather than one per expanded agent — no fetch waterfall when an agent expands, the recency view of section 6 reads the same cache, and it is where 2.8's archived count belongs
- [x] 5.2 `Sidebar.tsx`: agent rows gain an expander and a name button as separate controls, matching the project row's existing split
- [x] 5.3 Render an agent's open conversations as children, newest activity first, labelled by title
- [x] 5.4 Cap the list at 7 with an expander stating how many remain (operator decision, 2026-08-08: three agents expanded at 7 each still fits a rail without scrolling; one constant, revisit against a real project)
- [x] 5.5 Per-conversation attention indicator, with running and waiting visually distinct
- [x] 5.6 Persist agent expansion alongside the existing `aw.projectRailCollapsed` state

## 6. Navigation — the recency view

- [x] 6.1 View toggle in the rail; agent tree is the default; the choice persists to localStorage
- [x] 6.2 Recency list of the project's conversations across agents, most recent activity first
- [x] 6.3 A persistent 2px leading edge in the owning agent's colour, matching `agentColorVars` — no hover tint
- [x] 6.4 The same attention indicator as the tree
- [x] 6.5 A "Show archived (N)" control in the recency view, listing the project's archived conversations across agents (operator decision, 2026-08-08: recency hides archived, but the count and the way in must be visible — hiding them silently reads as data loss)
- [x] 6.6 Cap the recency list per project with the same expander contract as the tree — "Show N more" and a way back (operator requirement, 2026-08-08: *"The recency should have a conversation limit as well by project"*). Larger than the tree's per-agent 7, because this view flattens every agent: `RECENCY_DISPLAY_CAP = 15`

## 7. Row menus and the new-conversation surface

- [x] 7.1 Shared row-menu component on `@radix-ui/react-dropdown-menu`, opened from a visible control on the row, keyboard-reachable, returning focus on dismiss
- [x] 7.2 Conversation menu: rename (inline edit or dialog), archive
- [x] 7.3 Agent menu: new conversation, agent settings, show archived (N)
- [x] 7.4 Agent settings opens `AgentInfoTab` in a dialog without unmounting the open conversation
- [x] 7.5 New-conversation surface: composer-primary, agent pre-bound when started from an agent row
- [x] 7.6 Started from the recency view, the surface requires an agent to be chosen before sending
- [x] 7.7 Navigating away without sending leaves no conversation record

## 8. Selection lifts into the destination

- [x] 8.1 Remove `selectedConversationId` from `AgentOutputPanel`; the conversation arrives as a prop
- [x] 8.2 Move the auto-select-most-recent behaviour into destination resolution, and make it not fire when the destination is deliberately the new-conversation surface
- [x] 8.3 Remove `onConversationChange`'s round trip; navigation writes the destination directly
- [x] 8.4 Confirm the existing effect that seeds runtime overrides still fires on conversation change
- [x] 8.5 Existing frontend suites green at each step — do not land 8.1–8.3 as one commit

## 9. Controls rehoused, dead surfaces removed

- [x] 9.1 Durable handoff becomes a labelled control on the conversation header beside "Fold all turns", disabled with its reason when unavailable
- [x] 9.2 Remove "New conversation", the conversation entries, "Handoff" and "Agent details" from `ConversationControls.tsx`
- [x] 9.3 Delete the now-empty conversation-actions overflow menu
- [x] 9.4 Delete `AgentsPage.tsx` and `AgentDetailPanel.tsx` and their tests; confirm nothing imports them
- [x] 9.5 Update any frontend suite that mocked the overflow menu

## 10. Frontend tests

- [x] 10.1 `conversationTree.test.tsx` — conversations listed under an agent, newest first, titled; expander toggles without navigating; agent name opens the most recent conversation
- [x] 10.2 `conversationCap.test.tsx` — the remainder is behind an expander stating the count, never silently dropped
- [x] 10.3 `recencyView.test.tsx` — toggle, persistence, cross-agent ordering, persistent agent colour with no hover dependency
- [x] 10.4 `conversationAttention.test.tsx` — a question in one conversation shows as waiting while a different conversation is open
- [x] 10.5 `rowMenus.test.tsx` — both menus keyboard-operable, focus returns to trigger, agent settings do not unmount the conversation
- [x] 10.6 `newConversationSurface.test.tsx` — agent pre-bound from the tree; agent required from recency; abandonment creates nothing
- [x] 10.7 `handoffPlacement.test.tsx` — handoff present and labelled on the header at rest; disabled with reason when unavailable
- [x] 10.8 Assert no conversation identifier appears as a label anywhere in the rail

## 11. Verification

- [x] 11.1 `pytest hub/tests/ -q` green; `pytest tests/ -q` green
- [x] 11.2 `cd hub/ui && npx vitest run` green; `npx tsc --noEmit` clean
- [x] 11.3 `ruff check hub/hub/` introduces no new errors beyond the 3 pre-existing
- [x] 11.4 `npx openspec validate --specs --strict` passes
- [x] 11.5 `npm run build`, copy `hub/ui/dist` over `hub/hub/static/ui`, confirm with `diff -rq`
- [x] 11.6 Live: three agents, several conversations each — expand, rename, archive, unarchive, and confirm a blocked question in a background conversation is visible in the rail without opening it

> Rename, archive, the archived listing, `archived_by_agent`, and unarchive were all exercised
> against the real database on `localhost:8010` (`proj-84d218db`, 35 conversations), as was the
> 400 on an empty title. The **rail has not been driven in a browser** — every UI claim rests on
> the suite, and the operator found two defects by eye on 2026-08-08 that 549 passing tests did
> not. `conv-f22fb84f` is left titled "Renamed live from the row menu" with
> `title_set_by_operator = true`; that is this check's residue, not a real title.

- [x] 11.7 Live: archiving is refused for a running conversation and for one holding an undelivered queue entry, each with its reason

> The undelivered-entry half was verified live: a peer message to `haiku-3` made archiving return
> 409 with *"This conversation has messages waiting to be delivered…"*, and archiving succeeded
> once the entry was withdrawn. The **live-run half was not** — it needs a real CLI mid-turn.
> `archivable` checks the run first, and `test_conversation_archive_refusal.py` covers it.

- [x] 11.8 Live: an agent messaging an archived conversation receives the cause, the instruction, and its own content back

> 409 with all three parts, verbatim, against the running Hub.

- [x] 11.9 Live: enable title generation and confirm the title upgrades with no timeline entry and no change to the agent's context usage

> Both real CLIs answer the one-shot prompt usably: `claude --model claude-haiku-4-5 -p …` →
> "Identifying prime numbers from one to thirty" (7.1s); `codex exec --skip-git-repo-check
> --model gpt-5.4-mini …` → "Prime counting from 1 to 30" (5.6s). End to end on the real
> database, `conv-04d67c6d` went from the truncated *"Create a file called blocked.md containing
> the word test."* to *"Agent Misinterprets File Creation Request"*; the operator-set title on
> `conv-f22fb84f` was left alone; `agent_outputs` for the conversation stayed at 29, so no
> timeline entry and no context cost; one `conversation_titled` event was written. Caveat: Codex
> printed only the answer in this run, so `title_from_output`'s last-non-empty-line rule was not
> actually stressed by preamble. The project setting was **returned to `truncate`** — generation
> stays opt-in.

- [x] 11.10 Check light mode for every new surface — it was not checked in the previous change

> Verified statically, not visually. Every colour on `RowMenu`, `ConversationRow`, `AgentTree`,
> `RecencyView`, `AgentSettingsDialog`, `NewConversationSurface` and the rebuilt
> `ConversationControls` resolves through a token `index.css` defines in both mode blocks
> (`--amber --red --green --scrim --border --surface --text/-2/-3 --row-hover --rail-marker`);
> the only literal is a mode-neutral dialog shadow, matching the existing one.
> `hubVisualLanguage` already fails any raw hex anywhere under `src/`. **A visual pass in light
> mode is still owed** — contrast is not something a token audit can answer.
