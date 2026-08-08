# Handoff: agent-configuration-page built end to end; 36/39 tasks, 3 partial, nothing open

**Date:** 2026-08-08T17:07 · **Branch:** hub-native-experience · **HEAD:** b4913a7
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0019-2026-08-08-1559-checkpoint-designed-config-page-proposed.md
**Status:** chunk complete. Six commits, all verified. **Working tree clean.**

## Goal

Take `2026-08-08-agent-configuration-page` from 0/39 to built: agent configuration becomes its own
destination rather than a 520px modal, the dead fields go, and an agent becomes archivable instead
of undeletable-by-omission.

The *why*, in the operator's words: *"I think the agent configuration is starting to become bigger
we need to rework the config page instead of a pop up to be a page on it's own just like the project
config."* Configuration outgrew a dialog — it has sections now, and it must be linkable and survive
a reload, none of which a dialog can be.

## Current state

### The change is effectively complete

`openspec/changes/2026-08-08-agent-configuration-page/tasks.md` — **36 done, 3 partial, 0 open.**

The three partials are each blocked on something genuinely outside this change:

| task | missing | why |
|---|---|---|
| 3.1 Identity | `description` field | **`Agent` has no such column** (`models.py:107-140`). Needs a migration, not UI |
| 3.2 Execution | default permission posture | this is where stored `config["yolo"]` belongs — see Key decision 1 |
| 3.7 Workspace | worktree, working directory | provider sessions + their paths render; the worktree itself does not |

### What shipped, by commit

- **`534cb64`** — section 1. `role`/`yolo` off `AgentSummary` and the UI.
- **`09f21c7`** — `2026-08-07-conversation-navigation` synced into `openspec/specs/` and archived.
- **`40e61aa`** — section 2. The `agent-settings` destination; `AgentSettingsDialog` deleted.
- **`e728cc0`** — sections 3b + 4, plus the `agent-conversation-workspace` delta section 2 owed.
- **`2d79083`** — the two archived-agent offering surfaces the first pass missed.
- **`b4913a7`** — section 5. The creation-time boundary, as a test rather than a comment.

### Live environment

Hub running detached on **http://localhost:8010**, restarted twice this session (Python changed).
Project **`proj-84d218db` ("Testbed")**, key in `hub/.env` as `AW_BOOTSTRAP_API_KEY`.
**Database is at alembic `0038`** — the new agent-lifecycle migration is applied to the live DB.
Restart command:

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

**I archived `haiku-3` in the testbed during verification and unarchived it again** — roster
confirmed back to six agents. No cleanup owed.

### Other in-flight changes (unchanged this session)

| change | tasks |
|---|---|
| `2026-08-07-conversation-handoff-rework` | 11 done / 59 open — the checkpoint change, §2 and §3 are prerequisites |
| `2026-07-30-hub-native-experience` | 119 / 69 open |
| `2026-08-04-hub-contextual-navigation` | 43 / 2 open |
| `2026-08-04-hub-charcoal-visual-refresh` | 39 / 3 open |
| `2026-08-07-spec-execution-coordinator` | 0 / 29 — gated skeleton, **do not start**, fails validate by design |

## Files touched

### Committed

**Backend**
- `hub/hub/schemas/agents.py` — `role`/`yolo` removed from `AgentSummary`; `lifecycle` added; stale
  runner-enum comment replaced. Done.
- `hub/hub/api/v1/agents.py` — dropped `role=`/`yolo=` population; `list_agents` gained
  `?lifecycle=open|archived|all` (default `open`) with the filter applied *after* every roster
  source contributes; `_render_hub_agent_context` peer roster filtered to open; `_owned_agent`
  helper; `POST /{name}/archive` and `/{name}/unarchive`. Done.
- `hub/hub/api/v1/projects.py` — `_project_summary` roster filtered to `lifecycle == "open"`.
  **This is the rail's actual source.** Done.
- `hub/hub/api/v1/messages.py` — `create_message_for_actor` now loads the recipient row and refuses
  a send to an archived agent (409, three-part contract). Done.
- `hub/hub/db/models.py` — `Agent.lifecycle` (+`server_default="open"`) and `Agent.archived_at`;
  `ck_agents_lifecycle` CheckConstraint. Done.
- `hub/hub/agent_lifecycle.py` — **new.** `archivable`/`archive`/`unarchive`, mirroring
  `conversations.py:172,250,256`. Done.
- `hub/hub/migrations/versions/0038_add_agent_lifecycle.py` — **new.** Done.
- `hub/tests/test_agent_archival.py` — **new**, 12 tests. Done.
- `hub/tests/test_agents_self_registered.py` — `yolo` assertions replaced;
  `test_agent_summary_carries_no_role_or_yolo` added. Done.
- `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py` — head assertions
  `0037` → `0038`. Done.

**Frontend**
- `hub/ui/src/lib/navigation.ts` — `agent-settings` union member, `AGENT_SETTINGS_SECTIONS`,
  `agentSettingsDestination`, `agentSettingsBackDestination`, `isAgentSettingsDestination`,
  `isSectionedDestination`; serialize/parse with the `settings`-before-conversation ordering. Done.
- `hub/ui/src/components/agents/AgentSettingsPage.tsx` — **new.** Seven sections, `ArchiveControl`,
  `SessionList`, `SessionRow`. Done.
- `hub/ui/src/components/agents/AgentSettingsControls.tsx` — **new.** `WaitingSetting`,
  `RunnerPicker`, `CharterPicker`, moved out of the deleted `AgentInfoTab`. Done.
- `hub/ui/src/components/layout/Sidebar.tsx` — agent-settings shell branch, section list, back
  control, `onOpenAgentSettings`/`onBackFromAgentSettings` props; dialog wiring removed. Done.
- `hub/ui/src/App.tsx` — renders `AgentSettingsPage`; wires both handlers; `activeAgent` covers the
  new kind; conversation header handler. Done.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — `onOpenAgentSettings` prop + header button
  (`data-testid="conversation-agent-settings"`). Done.
- `hub/ui/src/api/agents.ts` — `role`/`yolo` off the type, `lifecycle` on;
  `useAgents(lifecycle)` with the filter in the query key; `useArchiveAgent`. Done.
- `hub/ui/src/components/agents/AgentCard.tsx` — `agent.yolo` ⚡ indicator removed. Done.
- **DELETED:** `hub/ui/src/components/layout/AgentSettingsDialog.tsx`,
  `hub/ui/src/components/agents/AgentInfoTab.tsx`.
- `hub/ui/src/__tests__/` — `agentArchival.test.tsx` (new); `urlNavigation.test.ts`,
  `rowMenus.test.tsx`, `agentWaitingSettings.test.tsx`, `chartersUi.test.tsx`,
  `runnersUi.test.tsx` all updated. Done.
- `hub/hub/static/ui/` — rebuilt and `diff -rq` verified three times. Committed artefact.

**openspec**
- `.../2026-08-08-agent-configuration-page/{proposal,design,tasks}.md` — corrected + progress.
- `.../specs/agent-configuration/spec.md` — the `yolo` requirement rewritten; three archival
  scenarios added.
- `.../specs/agent-conversation-workspace/spec.md` — **new delta**, supersedes the
  settings-open-without-navigating rule.
- `openspec/specs/conversation-lifecycle/spec.md` — **new capability** (from the archive sync).
- `openspec/specs/agent-conversation-workspace/spec.md`, `openspec/specs/agent-capability-plane/spec.md`
  — synced.
- `openspec/changes/archive/2026-08-07-conversation-navigation/` — moved.

### Section 5 (committed as `b4913a7`)

- `hub/ui/src/components/agents/AgentCreateDialog.tsx` — JSDoc stating the creation-time boundary
  rule. **Comment only; the built bundle is byte-identical, which is why `hub/hub/static/ui` has
  no diff for this commit.** Done.
- `hub/ui/src/__tests__/agentCreationUi.test.tsx` — two tests: creation offers no
  timeout/threshold/permission/access/checkpoint/worktree control; charter is never required
  (`charter_id` is **omitted**, not null). Done.
- `openspec/changes/2026-08-08-agent-configuration-page/tasks.md` — section 5 + 6.6 marked. Done.

## Key decisions

1. **`yolo` is live, and the handoff-0019 premise was wrong.** It is not `bool = False` with nothing
   behind it — `agents.py` populated it from `agent_meta`, and `Agent.config["yolo"]` drives
   `agent_trigger.py:288` → `runner_commands.py:187,201,246`
   (`--dangerously-skip-permissions` vs `--permission-mode`), `codex_appserver._thread_policy`, and
   the readiness refusal at `agents.py:210`. **Only the read-only summary field was removed.** Its
   editable home is Execution's permission posture (task 3.2, not yet built). `proposal.md`,
   `design.md` and the spec delta all stated the false version and were corrected — left alone they
   would have led someone to restore the field or delete a live config key as dead.
2. **Agent settings is a destination, not a dialog** — and that *contradicted the shipped spec* in
   two places requiring settings to open "without unmounting or navigating away from the
   conversation". Superseded by a MODIFIED delta rather than left to disagree with the code. The old
   rule existed to stop the conversation being destroyed; a destination does not carry that hazard.
3. **Back is fixed and free.** `conversationId: null` already resolves to the agent's most recent
   conversation via `resolveConversationSelection`, so no origin is stored. Rejected: remembering
   where the operator came from (departs from `App.tsx`'s fixed "Back to {project}").
4. **`isAgentSettingsDestination` kept separate from `isConfigurationDestination`.** The latter is a
   type guard callers narrow on to read `environmentSection`; widening it would break them.
   `isSectionedDestination` is the union the rail's `data-mode` uses.
5. **The parse order is the whole trick.** The conversation branch claims any URL carrying `agent`,
   so `settings` must be tested first or every settings link resolves to a chat. Three regression
   tests, including that `settings` naming no agent is *not* coerced into a destination.
6. **Sections route to real panels, beyond the scoped section 2.** A section list whose seven
   buttons do nothing is not a shell, it is a broken page. Controls extracted to
   `AgentSettingsControls.tsx` so relocating a setting is a change of placement, not a rewrite.
7. **The provider session list went to Workspace, not back to the conversation** — operator's
   choice when asked. What makes it useful is the directory each session ran in; it answers "where
   did this agent work", not "what is it doing now". Departs from task 4.1's literal wording.
8. **`AgentInfoTab` deleted.** Settings moved to the page, sessions to Workspace; what remained was
   a status block and two counters that both render elsewhere.
9. **Migration 0038 does not add the CHECK constraint to existing tables.** SQLite needs a batch
   rebuild, and a rebuild here would restate only the columns *this* revision knows about, silently
   dropping whatever later revisions added. `create_all` builds it for fresh DBs; write paths reject
   other values.
10. **`server_default="open"` as well as `default`.** Without it a fresh `create_all` schema and an
    upgraded one disagree — caught by `test_migration_0016`, which builds historical states with raw
    SQL and failed with `NOT NULL constraint failed: agents.lifecycle`.
11. **An archived agent keeps its name reserved.** `request_agent`'s uniqueness check deliberately
    still counts archived agents — archival is reversible and freeing the name would make
    unarchiving a collision. The agent budget counts them for the same reason. Both pinned by test.
12. **A new agent opens at its conversation** (`App.tsx:379`, already the behaviour). Everything the
    first turn needs was asked at creation; opening settings shows a page with no reason to read it.

## Constraints and user directives (verbatim)

**From this session:**
- *"start implementation."*
- On where the session list should live: chose **"Workspace settings section"** over keeping it with
  the conversation.
- On what to do next: chose **"3b — archival"**.
- On the archive question earlier: chose **"Sync and archive it now"** for conversation-navigation.

**Carried and still binding:**
- *"Wait. Are you already implementing? Should we dive in first to see what to do or at least give
  me the plan on what are you doing so I can make a more informed decision."* — **lay out the plan
  before building anything non-trivial.** Honoured this session for sections 2 and 3b.
- *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*
- *"we need to add a allow auto checkpoint with a box allowing to chose the percentage or the amount
  of tokens (because the context windows for different models can change some people might want to
  compact with 150K tokens rather then 50%) the count should be in K tokens so the user just sets
  150, 200, 300"* — for the checkpoint change, not yet built.
- *"okay let's ok with i for v1 but we need to take a hard note on this because I'm for sure going
  to forget this in the future."* — memory `project_checkpoint_trigger_prompts_provisional`.
- *"no need for backups everything is test env"*
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*
- *"What is taking so long?"* — **the operator is sensitive to wall-clock.** `pytest hub/tests/` is
  ~2:40–3:10 for ~1086 tests; `npx vitest run` ~40s. Targeted files during dev, one full sweep
  before committing.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; **live-verify prior claimed work on
  resume** (done at session start; repeat next session).

## Dead ends

- **`openspec` CLI cannot handle date-prefixed change names.** `npx openspec status --change
  2026-08-07-conversation-navigation` → *"Change name must start with a letter"*. Confirmed again
  for `status`, not just `new`. Sync and archive by hand.
- **`npm run lint` (from `CLAUDE.md`) does not work at all.** ESLint 9 requires a flat
  `eslint.config.js`; the repo has none, so it fails before linting anything. Pre-existing. `tsc` is
  what actually checks. Also `ruff check hub/hub/` reports **3 pre-existing errors** in `jobs.py` and
  `codex_appserver.py` — not mine, do not "fix" them as part of this change without saying so.
- **Bash-tool `cd` persists between calls.** A background `pytest hub/tests/` inherited a `hub/ui`
  cwd, collected nothing, and **exited 0** with "no tests ran". Use absolute paths for background
  runs and always read the tail, never trust the exit code alone.
- **Scripted multi-block Python surgery on source files mangles them.** A regex/offset script to
  delete three function definitions from `AgentInfoTab.tsx` ate the component's tail because offsets
  shifted after the first deletion. `git checkout` + explicit `Edit` calls instead.
- **`preview_snapshot` returns ~25k tokens.** Use `preview_evaluate` with a targeted expression for
  DOM assertions; reserve snapshots for actual visual checks.
- **`preview_click` and some `preview_evaluate` returns fail MCP schema validation** ("expected
  record, received null/array"). Wrap returns in an object literal `(() => ({...}))()`. Radix menu
  items need dispatched `pointerdown`/`mousedown`/`mouseup` before `click()`.
- **Message API uses `from`/`to` aliases**, not `sender`/`recipient` — a 422 otherwise. Responses
  serialize back to `from`/`to`.
- **`AgentCreate` omits `charter_id` entirely when no charter is chosen** — it is not sent as null.
- Carried and still true: `ORDER BY EventLog.id` does not order by recency; `extra: "forbid"` rejects
  a forbidden **key** regardless of value; **the default `python` on PATH has no pytest — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`**; the `app` fixture is an
  httpx client with no `.routes`; there is **no `db_session` fixture** — use
  `async_session_factory()` from `hub.db.engine`.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0019's claims at session start** (standing directive): tree matched
  `226f103`, `openspec validate --changes --strict` → 6 passed / 1 failed as claimed.
- `pytest hub/tests/` at each commit: **1074** (534cb64) → **1083** (e728cc0) → **1086** (2d79083)
  → **1086 passed, 10 skipped** on the final tree at `b4913a7`. ~2:40–3:10 each.
- `npx vitest run` → **594 passed / 68 files** after section 5.
- `npx tsc --noEmit` → clean.
- `ruff check` on every file touched → clean.
- `npx openspec validate --changes --strict` → 5 passed, 1 failed (the gated skeleton, by design);
  `--specs --strict` → 25 passed, 0 failed.
- `npm run build` + copy to `hub/hub/static/ui` + `diff -rq` → identical, three times.
- **Driven in a real browser against `:8010`** — deep link resolved to its section rather than a
  conversation; section switching moved the URL; back landed on `conv-72bd6353`; both entry points
  reached the page with no dialog; dark mode active row = 2px `rgb(124,140,255)`; archiving dropped
  the rail to five agents and the count to "5 agents"; unarchiving restored six.
- Direct SQLite check: `alembic_version` = `0038`, `agents` has `lifecycle` and `archived_at`.

**Explicitly NOT verified — do not assume:**
- No Codex or Claude agent run was triggered this session; the archived-agent *peer send* refusal is
  covered by API test only, never observed with a live agent actually calling `send_message`.
- Light mode was checked by eye for the settings page; **the archive control was only seen in dark
  mode**.
- The three partial tasks (3.1, 3.2, 3.7) are **not** implemented.

## Git state

Branch `hub-native-experience`, HEAD **`b4913a7`**, **working tree clean**. **No upstream — nothing
has ever been pushed on this branch; `git rev-list --count master..HEAD` = **282**.**

Six commits this session: `534cb64`, `09f21c7`, `40e61aa`, `e728cc0`, `2d79083`, `b4913a7`.

## Next steps

Nothing is half-finished; step 1 is a genuine choice between two fronts.

1. **Finish task 3.1 — add `Agent.description`.** Concretely: add
   `description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)` to `Agent` in
   `hub/hub/db/models.py` (beside `lifecycle`, ~line 131); write
   `hub/hub/migrations/versions/0039_add_agent_description.py` copying the guarded shape of
   `0038_add_agent_lifecycle.py`; bump the `"0038"` head assertions to `"0039"` in
   **`hub/tests/test_migrations.py`** (5 sites) **and `hub/tests/test_project_persistence.py`**
   (1 site); expose it on `AgentSummary` (`hub/hub/schemas/agents.py`) and populate it in
   `list_agents`; render an editable field in the Identity section of
   `hub/ui/src/components/agents/AgentSettingsPage.tsx`. **This is executable as written.**
2. **Or** finish 3.2 — the default permission posture control in Execution, which is where the
   stored `config["yolo"]` finally gets an editable home (see Key decision 1). Slightly larger,
   because it means deciding how posture and the legacy `yolo` key reconcile.
3. **Or start the checkpoint change** (`2026-08-07-conversation-handoff-rework`, 11/70). Its §8
   agent-level settings now have a destination — that was the point of sequencing this change
   first. §2 (peer delivery routes by recency, one site at `messages.py:133`) and §3 (Claude
   agents have never reported a context percentage — a *conformance* failure against a correct
   spec, `runner_parsing._claude_usage_sample:199`) are the unblocked fronts.
4. **Then sync and archive `2026-08-08-agent-configuration-page`** once the partials land — it is
   36 done / 3 partial / 0 open. Use the manual procedure from Dead ends, not the openspec CLI.
5. Carried: the operator's visual pass on light mode and `⋯` visibility; the archive control has
   only been seen in dark mode.

## Open questions for the user

1. **Should this branch be pushed?** 282 commits, no upstream, never asked-and-answered across five
   handoffs now.
2. **Should `.claude/handoffs/` stay tracked?** 105 files.
3. Should `pytest-xdist` be added? The ~3-minute sweep is the main wall-clock cost, and the operator
   has flagged wall-clock before.
4. Carried: peer-thread presentation was deferred — raise as its own change when the tree gets noisy.

## Read on resume

- `openspec/changes/2026-08-08-agent-configuration-page/tasks.md` — **start here.** The three `[~]`
  partials say exactly what is missing and why.
- `openspec/changes/2026-08-07-conversation-handoff-rework/design.md` — the 13 decisions, if picking
  up the checkpoint change instead.
- `hub/ui/src/lib/navigation.ts` — the destination shape, the parse-order trap, and
  `agentSettingsBackDestination`.
- `hub/hub/agent_lifecycle.py` — the archival contract, and the comment explaining why deletion does
  not exist.
- `hub/tests/test_agent_archival.py` — 12 tests; the docstrings record *why* each offering surface
  is filtered and which one a green suite failed to catch.
- `openspec/explorations/2026-08-08-handoff-behaviour.md` — the captured evidence behind the
  checkpoint change; read before questioning any of its decisions.
