# Handoff: conversation navigation — 80/80, shipped and deployed; nothing driven in a browser

**Date:** 2026-08-08T02:35 · **Branch:** hub-native-experience · **HEAD:** 5a4db3c
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0016-2026-08-08-0145-conversation-navigation-backend-and-rail-shipped.md
**Status:** chunk complete. Seven commits, working tree clean.
`2026-08-07-conversation-navigation` is **80/80 tasks** — every section done, including the
operator's new 6.6 (the recency cap) and 7.8 (the new-conversation headline). The change is
**not archived**: the operator tests tomorrow and has not signed off.

## Goal

Finish `openspec/changes/2026-08-07-conversation-navigation/` — give a conversation a name, a
provenance, a home in the rail, and a way to be put away — plus the operator's overnight
addition: *"The recency should have a conversation limit as well by project."*

The *why*, carried from handoff-0015: a conversation is the unit of work in AgentWeave and was
the one object with no place in the shell. Sixteen entries labelled `conv-a3f81b2c…` in an
overflow menu that also held durable agent settings. And `Question`, `PermissionRequest` and
`UnaskedQuestion` all block a run pending an answer, invisible outside the conversation they
were raised in, while `Agent.question_timeout_seconds` counts down.

## Current state

### Running and serving the current code

The Hub is up on **http://localhost:8010**, started **detached** (PowerShell `Start-Process`,
PID 23456 at the time of writing, working directory `hub/`), so it survives this session. It
reads `hub/.env`'s `DATABASE_URL=sqlite+aiosqlite:///data/agentweave.db` → the real
`hub/data/agentweave.db`, alembic head `0037`. Served bundle: `assets/index-CUEzDa2T.js`.
**`hub/hub/static/ui` is read from disk on each request, so replacing it needs no Hub restart.** The live project is **`proj-84d218db` ("Testbed")** with agents
`codex-1`, `codex-2`, `file_edit`, `haiku-1`, `haiku-2`, `haiku-3`; 35 open conversations,
0 archived. API key `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (in `hub/.env`).

To restart it if it dies:

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

### Seven commits this session, oldest first

1. `239d929` — the recency view's per-project cap (`RECENCY_DISPLAY_CAP = 15`) with
   "Show N more" / "Show fewer". The operator's overnight requirement, plus tasks.md 6.6 and a
   new spec scenario.
2. `d0a9247` — auto-selection moves out of the panel into destination resolution
   (`resolveConversationSelection`), and the destination gains `NEW_CONVERSATION_ID` so
   "unspecified" and "the operator asked for a new one" stop being the same value. Resolution
   writes itself back with `replaceState`.
3. `7ad0ad9` — `AgentOutputPanel` loses `selectedConversationId`; the conversation arrives as a
   prop. Section 8.
4. `b947d87` — row menus on every agent and conversation row, rename/archive/unarchive, the
   agent menu, the agent-settings dialog hosted by the rail, and the new-conversation surface.
   Section 7 + tasks 10.5, 10.6, 10.8.
5. `e4958fc` — handoff onto the conversation header; the overflow menu, the composer's "To"
   pill, `AgentsPage.tsx` and `AgentDetailPanel.tsx` deleted. Section 9 + task 10.7.
6. `7f91131` / `0f3fdd3` — rebuilt `hub/hub/static/ui`, ruff back to baseline, and the
   verification notes.
7. *(added after the first handoff was written)* the new-conversation surface's headline —
   *"What should `codex-1` work on?"*, and *"Who should work on this?"* unbound. 28px semibold,
   centred above the composer. Task 7.8, two new spec scenarios, two new tests.

### What actually works, verified live against the real database

- `PATCH …/conversations/{id}` renamed `conv-f22fb84f`; an empty title is refused with 400.
- Archive → the project listing went 35 open / 0 archived → 34 open / 1 archived with
  `archived_by_agent: {"haiku-1": 1}`; `?lifecycle=archived` returned the row; unarchive restored it.
- Archiving a conversation holding an undelivered `InboundQueueEntry` returned **409** with
  *"This conversation has messages waiting to be delivered. Archiving it would strand them,
  because nothing delivers into an archived conversation."*; archiving succeeded once the entry
  was withdrawn.
- A peer message addressed to an archived conversation returned **409** carrying all three
  parts — cause, the instruction to omit `conversation_id`, and the submitted content verbatim.
- **Title generation, end to end, with real CLIs.** `claude --model claude-haiku-4-5-20251001
  -p …` → "Identifying prime numbers from one to thirty" in 7.1s; `codex exec
  --skip-git-repo-check --model gpt-5.4-mini …` → "Prime counting from 1 to 30" in 5.6s.
  `maybe_generate_title` upgraded `conv-04d67c6d` from the truncated *"Create a file called
  blocked.md containing the word test."* to *"Agent Misinterprets File Creation Request"*, left
  the operator-set title on `conv-f22fb84f` alone, added **no** `agent_outputs` rows (29 before,
  29 after), and wrote one `conversation_titled` event.

### Known-broken / not done

1. **Nothing has been driven in a browser.** Every UI claim rests on 576 frontend tests. On
   2026-08-08 the operator found two defects by eye in under a minute that 549 passing tests did
   not. Treat the rail, the row menus, the new-conversation surface and the header's handoff
   button as **unvalidated by eye**.
2. **Light mode is verified only by token audit** (task 11.10). Every colour on the new surfaces
   resolves through a token `index.css` defines in both mode blocks; contrast has not been looked at.
3. **The `⋯` row-menu trigger is hover/focus-revealed, not always visible.** `.row-action` is
   `opacity: 0` at rest and revealed by `.row-group:hover`, `:focus-within`, `:focus-visible`,
   `[data-state="open"]`, or `data-persistent="true"` (set on the active row). This follows the
   project row's existing settings-gear convention. The operator said *"your instinct to show
   three dots is good"* — **if they expected them always visible, the fix is one line**: drop
   `opacity: 0` from `.row-action` in `hub/ui/src/index.css:381`.
4. **`archivable`'s live-run refusal was not exercised live** — only the undelivered-queue-entry
   half was. It needs a real CLI mid-turn. `hub/tests/test_conversation_archive_refusal.py`
   covers it.
5. **`AgentCard.tsx` is now unreachable.** Deleting `AgentsPage.tsx` removed its only call site.
   Left in place deliberately: it is the only home of the `collaboration_ready` indicator and
   deleting it was not asked for. `agentCardCollaboration.test.tsx` still renders it directly.
6. **`conv-f22fb84f` is left titled "Renamed live from the row menu"** with
   `title_set_by_operator = true`. That is residue from task 11.6, not a real title.
7. **`conv-04d67c6d` is left titled "Agent Misinterprets File Creation Request"** — residue from
   task 11.9. The project setting was returned to `truncate`.
8. **The change is not archived and the delta spec is not synced** into
   `openspec/specs/agent-conversation-workspace/spec.md`. Deliberate: the operator has not seen it.
9. Carried and still true: three older openspec changes in flight; Codex per-file approval paths
   unstarted; `pytest tests/` writes `.agentweave/` to the repo root (removed manually again).

## Files touched

`git status --short` is **empty** — working tree clean, everything committed.

### Frontend — new files

- `hub/ui/src/components/layout/RowMenu.tsx` — the shared row menu on
  `@radix-ui/react-dropdown-menu`. Visible `⋯` trigger (`.row-action`), items with an optional
  disabled `reason`. Complete.
- `hub/ui/src/components/layout/AgentSettingsDialog.tsx` — `AgentInfoTab` in a dialog hosted by
  the rail, with `onCloseFocus` handing focus back to the invoking trigger. Complete.
- `hub/ui/src/components/agents/NewConversationSurface.tsx` — composer-primary start surface:
  a 28px centred headline (`data-testid="new-conversation-headline"`), centred agent chips,
  pre-bound or requiring a choice. POSTs `agent/trigger` and hands the resulting
  `conversation_id` up. Complete.
- `hub/ui/src/__tests__/support/ControlledConversation.tsx` — test harness playing App's half of
  the panel's controlled-component contract. Not a test file itself.
- `hub/ui/src/__tests__/conversationSelection.test.ts` (7), `conversationDestination.test.tsx` (4),
  `rowMenus.test.tsx` (10), `newConversationSurface.test.tsx` (4), `handoffPlacement.test.tsx` (4).

### Frontend — modified

- `hub/ui/src/lib/navigation.ts` — `NEW_CONVERSATION_ID`, `newConversationDestination`,
  `isNewConversationDestination`, `SelectableConversation`, `resolveConversationSelection`; the
  conversation destination's `agent` is now `string | null`; `parseDestination` recognises the
  sentinel with no agent; `serializeDestination` omits a null agent. Complete.
- `hub/ui/src/hooks/useWorkspaceNavigation.ts` — `navigate(next, { replace })`. Complete.
- `hub/ui/src/App.tsx` — calls `useProjectConversations` (same cache the rail uses), resolves
  `resolvedConversationId`, replace-navigates when the destination named no conversation, routes
  `isNewConversationDestination` to `NewConversationSurface`, passes `onNewConversation` to the
  Sidebar. Complete.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — props are now
  `conversationId` / `onSelectConversation`; `selectedConversationId`, `onConversationChange`,
  `NEW_CONVERSATION_VALUE` and `selectConversation` are gone; new local `startingFresh` for the
  post-handoff state; `selfDirectedMoveRef` records where the panel sent itself so the
  leaving-a-conversation reset skips exactly that arrival; the continuity line names the
  conversation by title via `continuityLabel`. Complete.
- `hub/ui/src/components/agents/ConversationControls.tsx` — rewritten. Agent indicator, context
  usage, Stop, **Handoff** (labelled, `data-testid="conversation-handoff"`, disabled with its
  reason in `aria-label`), Fold all turns. No menu, no dialog. Complete.
- `hub/ui/src/components/agents/Composer.tsx` — gained `disabledReason` (disables send and
  states why); lost `conversations` / `onSelectConversation` / `onNewConversation`. Complete.
- `hub/ui/src/components/layout/AgentTree.tsx` — agent `RowMenu` (new conversation, agent
  settings, show archived (N)), per-agent archived listing fetched only when asked for,
  `projectId` passed to every `ConversationRow`. Complete.
- `hub/ui/src/components/layout/ConversationRow.tsx` — rewritten as a `row-group` wrapper: the
  row button, a `RowMenu`, inline rename input, and an inline error line for a refusal. Complete.
- `hub/ui/src/components/layout/RecencyView.tsx` — `RECENCY_DISPLAY_CAP = 15` with the
  expander, a "New conversation" row calling `onNewConversation(projectId, null)`. Complete.
- `hub/ui/src/components/layout/Sidebar.tsx` — `onNewConversation` prop, `settingsAgent` state
  and `settingsInvokerRef`, renders `AgentSettingsDialog`. Complete.
- `hub/ui/src/components/common/Icon.tsx` — added `more_horiz` → lucide `MoreHorizontal`. Complete.
- `hub/ui/src/api/agentChat.ts` — `archived_by_agent?`, `conversationErrorMessage`,
  `useRenameConversation`, `useArchiveConversation`, `useUnarchiveConversation`. Complete.
- `hub/ui/src/index.css` — `.row-action[data-state="open"] { opacity: 1 }`. Complete.
- Tests updated: `agentHandoff.test.tsx`, `agentRunningComposer.test.tsx`,
  `conversationControls.test.tsx`, `conversationComposer.test.tsx`,
  `composerModelControls.test.tsx`, `recencyView.test.tsx`.
- `hub/hub/static/ui/**` — rebuilt, `diff -rq` against `hub/ui/dist` clean.

### Frontend — deleted

- `hub/ui/src/components/agents/AgentsPage.tsx`
- `hub/ui/src/components/agents/AgentDetailPanel.tsx`
- `hub/ui/src/components/agents/ComposerConversationRouting.tsx`

### Backend — modified

- `hub/hub/api/v1/agent_chat.py` — `ProjectConversationsResponse.archived_by_agent`; the project
  listing groups archived rows by agent and derives `archived_count` from that sum. Complete.
- `hub/tests/test_conversation_archive.py` — three assertions extended for `archived_by_agent`.

### openspec

- `openspec/changes/2026-08-07-conversation-navigation/tasks.md` — 79/79, plus prose notes under
  §11 recording exactly what each live check did and did not cover.
- `openspec/changes/2026-08-07-conversation-navigation/specs/agent-conversation-workspace/spec.md`
  — one added paragraph and one scenario for the recency view's per-project cap.

## Key decisions

1. **`RECENCY_DISPLAY_CAP = 15`, not the tree's 7.** The tree caps per agent; the recency view
   flattens every agent, so seven would hide the second half of a working day in the one view
   that exists for scanning. Rejected: reusing `CONVERSATION_DISPLAY_CAP` (wrong unit — the
   caps mean different things); no cap (six agents at seven each is 42 rows in a 252px rail).
2. **`NEW_CONVERSATION_ID` is a distinct destination value, not `conversationId: null`.** With
   one value, the operator's empty composer is replaced by their most recent thread the moment
   the conversation list resolves. design.md predicted exactly this bug.
3. **Auto-selection replace-navigates rather than push-navigates.** Opening an agent is the
   operator's navigation; resolving *which* of its conversations that means is not. Pushing it
   would put the current conversation behind Back.
4. **The prepared handoff does not move the destination.** It sets a local `startingFresh`
   instead. Moving it would land on the new-conversation surface and take the prepared handoff
   with it. This also fixes a bug that existed in the running app before this session: the old
   `onConversationChange(null)` round trip reset `handoffState` to `idle`, so the resume prefix
   could never fire — the direct-render tests could not see it because they pinned
   `initialConversationId`.
5. **`selfDirectedMoveRef` stores the destination it sent, not a boolean.** A bare flag left set
   (because the parent ignored the move) would suppress the *next* genuine conversation change.
   Storing the value means it can only ever suppress the arrival it was set for.
6. **The conversation destination's `agent` became `string | null`** rather than adding a
   `kind: 'new-conversation'` destination. The agentless start is the same surface with one
   fewer thing known; a second kind would have meant two representations of one state.
7. **`archived_by_agent` is a new field on the project listing**, not a second request. An agent
   row's "Show archived (N)" cannot state N from a project-wide total, and fetching the archived
   rows just to count them defeats "only fetched once asked for".
8. **Agent settings are hosted by the `Sidebar`, not the panel.** "Without unmounting the open
   conversation" is a property of *where the dialog lives*; hosting it in the rail — which
   outlives the content area — makes it true rather than promised.
9. **The `⋯` uses the existing `.row-action` hover/focus reveal.** Matches the project row's
   settings gear and keeps the rail quiet, which the operator asked for ("I don't want it to be
   colorful… feel as an extension of the chat box"). See Known-broken #3 for the one-line change
   if they wanted them always visible.
10. **The continuity line names the conversation by title, truncated at 44 characters.** It
    printed `Continuing ${id.slice(0,12)}…`, and the spec says an identifier is not a label.
11. **`AgentCard.tsx` was not deleted** even though it is now unreachable. Task 9.4 named two
    files; deleting a third takes the `collaboration_ready` indicator with it.
12. **The new-conversation headline names the agent, not the project** (operator's choice from
    four options, 2026-08-08). The project is already in `ProjectHeader` two lines above, and the
    roster is what AgentWeave has that a chat app does not. The unbound variant is the
    instruction rather than decoration above one. Rejected: the direct T3 port; a stable
    project headline with the agent in a subline; *"What's next for X?"*. The agent name is
    **not** tinted with its identity colour — *"I don't want it to be colorful"* — the chip
    below already carries the dot.

## Constraints and user directives (verbatim)

**From this session:**
- *"The recency should have a conversation limit as well by project."*
- *"I'm going to sleep. Finish implementing this spec and I'm going to test it tomorrow."*
- *"Can we just add something cleaver on the composer creation page. The T3 one has in big bold
  letters 'What should we build in [project_name]'. I want to do something similar tailored for
  Agentweave."* — answered by task 7.8; they picked the agent-naming option at T3's weight.

**Carried from handoff-0013 through 0016 and still binding:**
- *"no need for backups everything is test env"*
- *"The recency doesn't show archived conversations. But you can expand the archived ones. There
  should be a button show archived or something like that"*
- *"Once we expand with show more there is no button with show less."*
- *"What is taking so long?"* / *"The test is taking very long why?"* — **the operator is
  sensitive to wall-clock time.** `pytest hub/tests/` is ~2:30 for 1060 tests; `npx vitest run`
  is ~11s for 577. Run targeted files during development, one full sweep before committing.
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter with
  highlight on the cards just like T3. It should feel as a extension of the chat box"*
- *"using right click is nice but no everyone will think about it. So your instinct to show three
  dots is good. I think we should go with that."*
- *"handoff need a explicit place to sit. Where we know it's there. Users might not know of
  forget about the handoff."*
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly, never `git add -A` without a pathspec; openspec, never aw-spec skills;
  `Icon` is the only icon system (**names are the Material-style keys in `Icon.tsx`'s map —
  `more_horiz`, `schedule`, `smart_toy`, not lucide component names**); `approve_tool_call` keeps
  **no return annotation**; `hub/hub/static/ui` is a committed build artefact that must be
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on
  the strength of a plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All six commits this session were unprompted.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. **Done at
  session start** — see Verification. **Repeat next session.**

## Dead ends

- **`DATABASE_URL="sqlite+aiosqlite:///$(pwd)/data/agentweave.db"` from Git Bash creates a
  database in the wrong place.** `$(pwd)` yields `/c/Users/...`, giving a four-slash URL that
  SQLAlchemy reads as an absolute path, which Windows resolves to `C:\c\Users\...`. It silently
  migrated a brand-new database from `0001` while the real one sat untouched. The stray tree at
  `C:\c\Users\huida\Documents\projects\` was removed. **Use the relative
  `sqlite+aiosqlite:///data/agentweave.db` with `WorkingDirectory` set to `hub/`, or omit
  `DATABASE_URL` and let `hub/.env` supply it.** (`C:\c\Users\huida\.agentweave\` predates this
  and was left alone.)
- **`Stop-Process -Id $pid -Force` split across a Git Bash `while read` loop breaks.** The
  `-Force` lands on its own line and PowerShell reads it as a command. Get the PID first, then
  issue a single `powershell -Command "Stop-Process -Id <n> -Force"`.
- **Opening a Radix menu with `{Enter}` focuses the first item; opening it with a click focuses
  the menu content.** A test that does one and asserts the other is off by one `ArrowDown`.
- **`projectScopedApiContract.test.tsx` greps API source for the literal `['project', projectId`.**
  A mutation's `onSuccess: (_data, variables) => …['project', variables.projectId, …]` fails it.
  Destructure to a bare `projectId`.
- **`ordering EventLog by `id` does not give newest-last.** IDs are random strings; a
  `conversation_titled` event written seconds ago does not appear in `ORDER BY id DESC LIMIT 3`.
  Query by `event_type` or `timestamp`.
- **`maybe_generate_title` and `generate_conversation_title` are keyword-only** (`*,`). Positional
  args raise `TypeError: takes 0 positional arguments`.
- Carried and still true: `op.batch_alter_table(recreate="always")` must guard on **both**
  `conversations` and `projects`; a CHECK on `runners.cli` makes an unsupported CLI unreachable
  even by direct SQL; binding a runner before triggering makes tests spawn a real `claude`
  (trigger first, then bind); `mcp_server.send_message` is a plain function, not a FastMCP object;
  `QuestionCreate` requires `from_agent`, `options` (min 2), `header`, `multi_select`;
  `AgentSummary` has no `id` or `color_index` (the rail's agents are `ProjectAgentSummary`);
  `localhost:8010/api/v1/projects/Agentweave/...` is "Project not found" — the real project is
  `proj-84d218db`; **`openspec validate` reads only a requirement's FIRST LINE for `SHALL`**; the
  `openspec` CLI cannot manage a date-prefixed change; **the default `python` on PATH has no
  pytest — use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`**.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0016's claims at session start** (the standing directive):
  `npx vitest run` → **549 passed, 62 files**, matching its recorded figure exactly. The rail,
  the recency view and the six conversation routes were all on disk as described.
- `pytest hub/tests/ -q` → **1060 passed, 10 skipped** in 2:27.
- `pytest tests/ -q` → **372 passed, 3 skipped**. (Created `.agentweave/` at the repo root; removed.)
- `cd hub/ui && npx vitest run` → **576 passed, 67 files** (up from 549; one obsolete
  overflow-menu test was removed and two headline tests added after the first count of 577).
- `npx tsc --noEmit` → clean.
- `ruff check hub/hub/` → **3 errors, the pre-session baseline.** (A C416 I introduced was fixed.)
- `npx openspec validate --specs --strict` → **24 passed, 0 failed.**
- `npx openspec validate --changes --strict` → 4 passed, 2 failed — the handoff-rework and
  spec-execution-coordinator **skeletons, intentionally**.
- `npm run build` then `diff -rq hub/ui/dist hub/hub/static/ui` → identical.
- **Live against the real database and running Hub:** all of Current state → "verified live".

**Explicitly NOT run/tested — do not assume:**
- **Nothing has been driven in a browser by me.** No screenshot, no click, no visual check.
- **Light mode: token audit only.** No visual check.
- **The live-run archive refusal** (a real CLI mid-turn) was not exercised.
- **The full trigger→title path was not exercised through an agent turn** — 11.9 called
  `maybe_generate_title` directly. The two call sites in `agent_trigger.py` (~line 1214 exec,
  ~line 1580 app-server) are covered by `test_title_generation.py` only.
- **`title_from_output`'s last-non-empty-line rule was not stressed** — Codex printed only the
  answer in the one real run.
- `mkdocs build` not run. `npm run lint` still does not start (ESLint 9, no flat config).

## Git state

Branch `hub-native-experience`, HEAD `0f3fdd3`, **working tree clean**. **No upstream — nothing
has ever been pushed on this branch. 261 commits ahead of `master`** (was 253 at handoff-0016).

Commits this session: `239d929`, `d0a9247`, `7ad0ad9`, `b947d87`, `e4958fc`, `7f91131`,
`0f3fdd3`, `8f81dcc` (this handoff), `5a4db3c` (the headline).

**openspec in flight (6):** `2026-08-07-conversation-navigation` (**80/80, ready to sync and
archive once the operator has looked at it**), `2026-08-07-spec-execution-coordinator` (0/29,
gated skeleton — do not start), `2026-08-07-conversation-handoff-rework` (0/24, gated skeleton —
do not start), `2026-08-04-hub-charcoal-visual-refresh` (39/42),
`2026-08-04-hub-contextual-navigation` (43/45), `2026-07-30-hub-native-experience` (119/188).

## Next steps

1. **Ask the operator to open http://localhost:8010 and look at the rail**, specifically: do the
   `⋯` controls appear where they expect (they are hover/focus-revealed — see Known-broken #3),
   does clicking a conversation open it, does "New conversation" from an agent row land on the
   composer-primary surface, and does the Handoff button read correctly on the header. This is
   next-step 1 because they found two defects by eye last session that a green suite did not.
2. **If they want the `⋯` always visible**, delete `opacity: 0;` from `.row-action` in
   `hub/ui/src/index.css` (line 381), rebuild with `cd hub/ui && npm run build`, copy `dist` over
   `hub/hub/static/ui`, confirm with `diff -rq`, and restart the Hub.
3. **Check light mode by eye** (task 11.10's remaining half) — toggle the mode and look at
   `RowMenu`'s dropdown, `ConversationRow`'s error line, `NewConversationSurface`'s agent chips,
   and the disabled Handoff button.
4. **Once they sign off: `openspec-sync-specs` then `openspec-archive-change`** for
   `2026-08-07-conversation-navigation`. Do not do this before they have looked.
5. **Tidy the two live-check residues** if they care: `conv-f22fb84f` is titled "Renamed live
   from the row menu" and `conv-04d67c6d` is titled "Agent Misinterprets File Creation Request".
6. Carried and unresolved: the three older openspec changes; `pytest tests/` writing
   `.agentweave/` to the repo root; Codex per-file approval paths; the specification program.

## Open questions for the user

1. **Should the `⋯` row menus be visible at rest, or is hover/focus-reveal right?** Implemented
   as reveal, matching the project row's settings gear. One-line change either way (next step 2).
2. **Is 15 the right recency cap?** Chosen against the tree's 7 with reasoning, not measured
   against a real day's work.
3. **Is the 120-character title cap too long?** Carried unanswered from handoff-0016. The
   backfill produced titles that ellipsise before becoming distinguishable in a 252px rail.
   Generation, now confirmed working, produces much shorter ones — which may be the real answer.
4. **Should `origin: peer` be visually distinct in the tree, or only in the conversation header?**
   Carried from handoff-0015; implemented as a small `peer` chip on the row without an answer.
5. **Should `AgentCard.tsx` be deleted?** It is unreachable now, and it is the only home of the
   `collaboration_ready` indicator.
6. **Should `pytest-xdist` be added?** Offered at handoff-0016, not yet answered. The suite is now
   ~2:30.
7. Should `hub-native-experience` be pushed? Still no upstream, now **261** commits ahead.
   Carried unresolved since handoff-0012.
8. Should the Hub gain project/agent deletion? (Carried from handoff-0012.)
9. Should the database backup at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept?
10. Should `.claude/handoffs/` stay tracked? It is (102 files).

## Read on resume

- `openspec/changes/2026-08-07-conversation-navigation/tasks.md` — 80/80 with the §11 prose notes
  recording exactly what each live check covered. Start here.
- `hub/ui/src/components/layout/RowMenu.tsx` and `hub/ui/src/index.css` (the `.row-action` block,
  ~line 380) — next step 2's target if the `⋯` needs to be always visible.
- `hub/ui/src/components/layout/ConversationRow.tsx` — the row, its inline rename, and the
  refusal line; where any conversation-row feedback lands.
- `hub/ui/src/components/agents/NewConversationSurface.tsx` — the composer-primary start surface,
  the newest and least-exercised component.
- `hub/ui/src/lib/navigation.ts` — `NEW_CONVERSATION_ID` and `resolveConversationSelection`, the
  contract everything about conversation selection now rests on.
- `openspec/changes/2026-08-07-conversation-navigation/design.md` — the eight decisions with their
  rejected alternatives. Read before deviating; several decisions above deviate deliberately and
  say why.
