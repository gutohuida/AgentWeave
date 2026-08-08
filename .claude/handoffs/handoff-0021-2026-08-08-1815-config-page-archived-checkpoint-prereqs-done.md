# Handoff: agent-configuration-page finished and archived; both checkpoint prerequisites done and live-verified

**Date:** 2026-08-08T18:15 · **Branch:** hub-native-experience · **HEAD:** `ec2a009`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0020-2026-08-08-1707-agent-configuration-page-built.md`
**Status:** chunk complete. Seven commits, all verified. **Working tree clean.**

## Goal

Two things, both finished:

1. Close `2026-08-08-agent-configuration-page` — the three tasks handoff 0020 left as `[~]`
   partials (3.1 description, 3.2 default permission posture, 3.7 workspace) — then sync its specs
   and archive it.
2. Start `2026-08-07-conversation-handoff-rework` from its **prerequisite** end. Sections 2 and 3
   gate everything else in that change: a checkpoint threshold keys on a context percentage Claude
   agents had never produced, and the cross-agent participation graph cannot be built on peer
   delivery that scatters one exchange across unrelated threads.

The operator's instruction for the session: *"continue implementing non stop. I'm going to the
super market. When I'm back I'll send a message and then we go back to the normal programing
cycle."*

## Current state

### `2026-08-08-agent-configuration-page` — **39/39, synced, archived**

Moved to `openspec/changes/archive/`. Its `agent-configuration` delta became a **new shipped
capability** at `openspec/specs/agent-configuration/spec.md` (9 requirements); the
`agent-conversation-workspace` and `operator-agent-creation` deltas were applied to those specs.
`npx openspec validate --specs --strict` → **26 passed** (was 25).

### `2026-08-07-conversation-handoff-rework` — **sections 2 and 3 done; 11 → 24 tasks**

| section | state |
|---|---|
| 0. Stale references | 0/5 — unblocked, small, independent |
| 1. Exploration | 11/11 (was already done) |
| **2. Deterministic peer delivery** | **7/7 — done, live-verified** |
| **3. Context usage measurement** | **5/5 — done, live-verified** |
| 4. The Worker | 0/5 — **next front, and genuinely non-trivial** |
| 5–9 | 0/44 |

### Other in-flight changes (untouched this session)

| change | tasks |
|---|---|
| `2026-07-30-hub-native-experience` | 119 / 69 open |
| `2026-08-04-hub-contextual-navigation` | 43 / 2 open |
| `2026-08-04-hub-charcoal-visual-refresh` | 39 / 3 open |
| `2026-08-07-spec-execution-coordinator` | 0 / 29 — gated skeleton, **do not start**, fails validate by design |

### Live environment

Hub running detached on **http://localhost:8010**, restarted **three times** this session (Python
changed each time). Project **`proj-84d218db` ("Testbed")**, key in `hub/.env` as
`AW_BOOTSTRAP_API_KEY`. **Database is at alembic `0041`.** Restart command:

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

**Testbed state I changed and did not fully restore:**
- `codex-1`'s description and `default_permission_mode` were set during verification and **reverted
  to null**. Its `config` now contains `{"yolo": false}` where the key was previously absent —
  behaviourally identical (`bool(config.get("yolo"))` was already False), but it is a written key.
- **Four live agent runs were triggered** (`haiku-1` ×3, `codex-1` ×1), leaving new conversations
  `conv-07374bbb`, `conv-0bdd26ba`, and a peer-bound `conv-05a0bbb4` on `codex-1`. Real messages
  `ping-1` / `ping-2` from `haiku-1` to `codex-1` exist. All intentional; operator said *"no need
  for backups everything is test env"*.

## Files touched

Everything below is **committed**; working tree is clean.

### Commit `830a45b` — task 3.1, `Agent.description`

- `hub/hub/db/models.py` — `Agent.description` `String(256)` nullable.
- `hub/hub/migrations/versions/0039_add_agent_description.py` — **new**, guarded like `0038`.
- `hub/hub/schemas/agents.py` — `description` on `AgentSummary`.
- `hub/hub/api/v1/agents.py` — `_validated_description` (blank → NULL, 256 cap, non-text 400);
  `description` in `_unrestricted_fields`, in the PATCH body handling and response, and populated
  in `list_agents`.
- `hub/ui/src/api/agents.ts` — `description` on the type, `MAX_AGENT_DESCRIPTION_CHARS`,
  `useUpdateAgentDescription`.
- `hub/ui/src/components/agents/AgentSettingsControls.tsx` — `DescriptionSetting` (textarea,
  commits on blur).
- `hub/ui/src/components/agents/AgentSettingsPage.tsx` — Description row in Identity.
- `hub/tests/test_agents_self_registered.py` — 3 new tests.
- `hub/ui/src/__tests__/agentDescription.test.tsx` — **new**, 6 tests.
- `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py` — head → `0039`.

### Commit `f7e279f` — task 3.2, default permission posture

- `hub/hub/db/models.py` — `Agent.default_permission_mode` `String(32)` nullable.
- `hub/hub/migrations/versions/0040_add_agent_default_permission_mode.py` — **new**.
- `hub/hub/model_catalog.py` — `PERMISSION_MODE_CONTROL`, `DEFAULT_PERMISSION_MODE`,
  `permission_mode_values()` (union across providers).
- `hub/hub/api/v1/agents.py` — `FULL_ACCESS_PERMISSION_MODE`, `_validated_permission_mode`,
  `_apply_default_permission_mode` (**writes `config["yolo"]` in the same breath**), applied
  *after* the config merge so a body carrying both ends coherent.
- `hub/hub/api/v1/agent_trigger.py` — injects the agent default into `control_overrides` when the
  conversation states none (**one site, `trigger_agent_directly`**).
- `hub/hub/runner_commands.py` — module docstring records that the agent default arrives by the
  same route as a per-run choice.
- `hub/ui/src/api/modelCatalog.ts` — `PERMISSION_MODE_CONTROL`, `permissionModeValues()`.
- `hub/ui/src/api/agents.ts` — `default_permission_mode`, `useUpdateAgentPermissionDefault`.
- `hub/ui/src/components/agents/AgentSettingsControls.tsx` — `PermissionDefaultSetting`.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — `EMPTY_CONTROLS`, `agentDefaultControls`,
  passes `effectiveControls` to `Composer`.
- `hub/ui/src/__tests__/support/modelCatalogFixture.ts` — **new**, shared catalog fixture.
- `hub/ui/src/__tests__/agentPermissionDefault.test.tsx`, `composerPermissionDefault.test.tsx` —
  **new**, 7 + 3 tests.
- `hub/tests/test_agent_default_permission_mode.py` — **new**, 7 tests.
- Mocks added to `agentArchival`, `agentDescription`, `agentWaitingSettings`, `chartersUi`,
  `runnersUi` test files.

### Commit `3346593` — task 3.7, Workspace

- `hub/hub/api/v1/worktrees.py` — `AgentWorkspaceInfo`, `GET /worktrees/{agent}`. **Declared after
  `/conflicts`**, which a path param would otherwise claim.
- `hub/ui/src/api/workspace.ts` — `AgentWorkspaceInfo`, `useAgentWorkspace`.
- `hub/ui/src/components/agents/AgentSettingsPage.tsx` — `WorkspaceLocation` (two rows).
- `hub/tests/test_worktrees.py` — 5 new tests.
- `hub/ui/src/__tests__/agentWorkspaceSection.test.tsx` — **new**, 7 tests.

### Commit `2820b16` — sync + archive

- `openspec/specs/agent-configuration/spec.md` — **new capability**, 9 requirements.
- `openspec/specs/agent-conversation-workspace/spec.md` — two MODIFIED requirements applied.
- `openspec/specs/operator-agent-creation/spec.md` — creation-time boundary appended.
- `openspec/changes/archive/2026-08-08-agent-configuration-page/` — moved (`git mv`).

### Commit `79d5610` — section 3, context usage

- `hub/hub/model_catalog.py` — `claude-opus-5` and `claude-fable-5` → `context_window=1_000_000`;
  **new** `context_window_for_model()` (exact id → alias → longest prefix).
- `hub/hub/runner_parsing.py` — `_claude_usage_sample` takes `model`; `parse_claude_line` passes
  `message.model`.
- `hub/hub/output_recording.py` — **new** `resolve_usage_limit()`, applied in
  `record_context_usage`.
- `hub/hub/api/v1/agents.py` — **new** `_usable_context_reading()`; the ctx read path now collects
  all rows per agent instead of `setdefault`ing the newest.
- `hub/tests/test_context_usage_measurement.py` — **new**, 10 tests.
- `hub/tests/test_model_catalog.py` — `test_unknown_context_window_is_none_not_a_substitute`
  **renamed and inverted** to `test_every_declared_claude_model_has_a_context_window`.

### Commits `a951e2c` + `ec2a009` — section 2, peer delivery

- `hub/hub/db/models.py` — `Conversation.bound_sender_conversation_id` (indexed) and
  `bound_sender_agent`.
- `hub/hub/migrations/versions/0041_add_conversation_peer_binding.py` — **new**.
- `hub/hub/conversations.py` — **new** `peer_bound_conversation()`.
- `hub/hub/api/v1/messages.py` — `latest_open_conversation` import **removed**; the no-id branch
  now binds.
- `hub/tests/test_agent_message_routing.py` — `_active_run` takes `conversation_id`;
  `test_no_conversation_id_lands_in_the_recipients_newest_open_one` **rewritten and inverted**;
  5 new tests.
- `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py` — head → `0041`.
- `openspec/changes/2026-08-07-conversation-handoff-rework/tasks.md` — sections 2 and 3 marked
  with their findings.

### Committed build artefact

`hub/hub/static/ui/` — rebuilt and `diff -rq` verified after `830a45b`, `f7e279f`, `3346593`.
**Not rebuilt after `79d5610`/`a951e2c`/`ec2a009`, because those three are backend-only.**

## Key decisions

1. **`yolo` is not a second setting — it is the older two-valued spelling of the default posture.**
   Writing `default_permission_mode` rewrites `config["yolo"]`; clearing the posture clears the
   flag. `runner_commands`, `codex_appserver._thread_policy` and the readiness check all read the
   flag, and drift produces one specific incoherence: a run under *Ask me* whose `yolo` suppresses
   the `--allowedTools` allowlist its own MCP tools need. Rejected: leaving them independent.
2. **The agent default is applied at trigger, not only in the composer.** One site,
   `trigger_agent_directly`, filling the `permission_mode` control when the conversation states
   none — so the agent default and a per-run choice are one mechanism. This is what makes the
   setting mean anything for peer- or schedule-triggered runs, which is the case it exists for.
3. **The composer *shows* the default but never *sends* it.** Via the `effectiveControls` prop
   `Composer` already had. Echoing it back would freeze today's default onto the conversation the
   first time anyone typed.
4. **Posture validated against the catalog's union, not the agent's bound provider.** An agent may
   have no runner bound, and rebinding must not invalidate a default already chosen.
5. **The description is never injected into a turn.** The charter is the behaviour contract; a
   second field that also shaped behaviour would leave two places to look when an agent acts
   wrongly. Blank collapses to NULL so "cleared" and "never written" are one state.
6. **Workspace isolation is rendered but deliberately not made editable.** `config.read_only` is
   real state nothing offers, so a control is defensible — but flipping an agent with uncommitted
   worktree work to the shared checkout strands that work. Needs its own change with a stated
   answer for the existing worktree. **A test asserts no such control exists**, so adding one is a
   decision rather than a drift.
7. **The archived spec delta said back-navigation returns to the *originating context*; the code
   returns to a **fixed** target.** Corrected the delta before syncing — left alone, the shipped
   spec would have stated a rule the code deliberately does not follow. A remembered origin makes
   one control mean different things on different visits with nothing on screen saying which.
8. **Context usage: the enabling fix was the model, not the merge.** `_claude_usage_sample`
   recorded no model, so there was nothing to resolve a window *by*. Claude names the model on the
   `assistant` message and the window on the `result` message. Rejected: merging the two events
   (the design explicitly rejects depending on a collision).
9. **The context read-path fallback is scoped to the newest row's provider session.** A compaction
   resets usage; reporting a pre-reset percentage as current is worse than reporting none, because
   it is the number the operator would act on.
10. **Peer binding uses two columns, not one key.** A conversation id and an agent name answer
    different questions; keeping them apart lets the senderless lookup require the conversation
    column to be NULL rather than hoping the namespaces never collide.
11. **The peer archive split falls out of filtering the lookup on `open`.** A sender that *named*
    an archived conversation is still refused (it chose one); a binding the operator archived gets
    a successor carrying the same binding.
12. **`latest_open_conversation` survives outside the peer path** — `questions.py`,
    `unasked_questions.py`, `output_recording.py` attach a question or output to the agent's
    *current* thread. That is not a routing decision between correspondents. Task 2.3 scopes the
    prohibition to the peer path; the design's prose ("disappears from the codebase entirely") is
    looser, and I followed the task.

## Constraints and user directives (verbatim)

**From this session:**
- *"continue implementing non stop. I'm going to the super market. When I'm back I'll send a
  message and then we go back to the normal programing cycle"*

**Carried and still binding:**
- *"Wait. Are you already implementing? Should we dive in first to see what to do or at least give
  me the plan on what are you doing so I can make a more informed decision."* — **lay out the plan
  before building anything non-trivial.** Section 4 (The Worker) is the first thing that qualifies.
- *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*
- *"we need to add a allow auto checkpoint with a box allowing to chose the percentage or the
  amount of tokens (because the context windows for different models can change some people might
  want to compact with 150K tokens rather then 50%) the count should be in K tokens so the user
  just sets 150, 200, 300"* — section 8.5, not yet built.
- *"okay let's ok with i for v1 but we need to take a hard note on this because I'm for sure going
  to forget this in the future."* — memory `project_checkpoint_trigger_prompts_provisional`.
- *"no need for backups everything is test env"*
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*
- *"What is taking so long?"* — **the operator is sensitive to wall-clock.** `pytest hub/tests/` is
  ~2:35–2:40 for ~1116 tests; `npx vitest run` ~12–40s. Targeted files during dev, one full sweep
  before committing.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; **live-verify prior claimed work on
  resume** (done at session start; repeat next session).

## Dead ends

**New this session:**
- **`ta.blur()` does not fire React's `onBlur` in this browser-automation setup.** Dispatching
  `new FocusEvent('focusout', {bubbles: true})` does. Cost ~20 minutes of "the mutation isn't
  firing" before instrumenting `window.fetch` proved no request was made. Same for `select`:
  use the native value setter + `new Event('change', {bubbles: true})`.
- **`preview_set_appearance` does not switch the app's theme.** The Hub reads
  `localStorage['agentweave-prefs']` (`{"mode":"dark"}`), not `prefers-color-scheme`. Set the key
  and reload. Note `document.body`'s background stayed dark in light mode while `--bg` on `:root`
  was `#fafafa` — pre-existing, not investigated, and the visible controls were correct.
- **Bash-tool cwd resets to the repo root between calls, unpredictably.** Several commands failed
  with "No such file or directory" after a previous `cd`. **Always `cd /c/Users/.../AgentWeave &&`
  first**, or use absolute paths. `ruff check hub/hub/` from the wrong cwd reports `E902`, which
  looks like a lint error and is not.
- **`git commit -m @'...'@` is PowerShell here-string syntax and does not work in the Bash tool.**
  It produced a commit subject literally beginning `@`. Use `git commit -F - <<'EOF'`.
- **The live DB is at `hub/data/agentweave.db`, and the table is `event_logs` (plural).** `sqlite3`
  from the repo root fails to open it; `cd hub` first.

**Carried and still true:**
- **`openspec` CLI cannot handle date-prefixed change names.** Sync and archive by hand.
- **`npm run lint` does not work at all.** ESLint 9 needs a flat config the repo lacks. `tsc` is
  what checks. `ruff check hub/hub/` reports **3 pre-existing errors** (`jobs.py`,
  `codex_appserver.py`) and `hub/tests/` reports **13 more** — none mine; do not "fix" them
  silently.
- **`preview_snapshot` returns ~25k tokens.** Use `preview_evaluate` with a targeted expression.
- **`preview_evaluate` returns must be object literals** — `(() => ({...}))()`.
- **Message API uses `from`/`to` aliases**, not `sender`/`recipient`.
- **`AgentCreate` omits `charter_id` entirely** when no charter is chosen.
- `ORDER BY EventLog.id` does not order by recency; `extra: "forbid"` rejects a forbidden **key**
  regardless of value; **the default `python` on PATH has no pytest — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`**; the `app` fixture is an
  httpx client with no `.routes`; there is **no `db_session` fixture** — use
  `async_session_factory()` from `hub.db.engine`.
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0020's claims at session start**: tree matched `13002ff`, working
  tree clean, six commits present as described.
- `pytest hub/tests/` at each commit: **1089** (`830a45b`) → **1096** (`f7e279f`) → **1101**
  (`3346593`) → **1111** (`79d5610`) → **1116 passed, 10 skipped** (`a951e2c`). ~2:35 each.
- `npx vitest run` → **600** → **610** → **617 passed / 72 files**.
- `npx tsc --noEmit` → clean at every frontend commit.
- `ruff check` on every touched file → clean.
- `npx openspec validate --specs --strict` → **26 passed, 0 failed** (was 25 — the new capability).
  `--changes --strict` → 4 passed, 1 failed (the gated skeleton, by design).
- `npm run build` + copy to `hub/hub/static/ui` + `diff -rq` → identical, three times.
- **Driven in a real browser against `:8010`**: description saved, survived reload, persisted to
  the DB; posture dropdown offered exactly the catalog's five options and wrote
  `default_permission_mode='manual'` with `config.yolo=false`; the composer's Permissions pill read
  **"Ask me"** on a conversation with no override and **"Edit files"** on one that overrode —
  proving the precedence; Workspace rendered the real worktree path, branch and "checked out and
  ready"; light mode checked on both new controls (`#18181b` on `#e9e9ec`, matching the existing
  pickers).
- **`GET /worktrees/never-ran`** returned `provisioned: false` and **created nothing on disk**.
- **Live context-usage observation (task 3.5):** before, all four testbed Claude agents reported
  `percent: null`; after a real `haiku-1` run, `percent: 15.12`, `context_tokens: 30233`,
  `limit_tokens: 200000`. The stored rows show the newest row for that session is *still* the
  limit-only report, so the read-path fallback is what surfaced it.
- **Live peer-delivery observation (task 2.7):** migration `0041` applied to the real DB (38
  conversations, none backfilled, index created). A real `haiku-1` turn called `send_message`; the
  Hub created `conv-05a0bbb4` bound to `conv-0bdd26ba`. A `codex-1` turn on an unrelated thread
  made `conv-8b300c8e` its newest — the decoy recency would have chosen — and the second send
  landed back in `conv-05a0bbb4`. **Both pings, one thread, with the decoy newer.**

**Explicitly NOT verified — do not assume:**
- **The frontend bundle was not rebuilt after the last three commits.** They are backend-only, so
  `hub/hub/static/ui` should still match — **but this was not re-confirmed with `diff -rq` after
  `ec2a009`.** Do that before any commit that touches `hub/ui/`.
- The **senderless** peer path (Hub/scheduler → agent) is covered by API test only; no live
  Hub-originated message was observed.
- The peer **archive-successor** path is covered by API test only, not observed live.
- `claude-opus-5` / `claude-fable-5` context windows come from Anthropic's published model
  reference, **not** from a live `result`-event observation like Sonnet 5 and Haiku 4.5. The test
  says so.
- Light mode was **not** re-checked for the Workspace section specifically (only Identity and
  Execution controls were measured).
- Section 4 onward of the checkpoint change is **not started**.

## Git state

Branch `hub-native-experience`, HEAD **`ec2a009`**, **working tree clean**. **No upstream —
nothing has ever been pushed on this branch; `git rev-list --count master..HEAD` = 290.**

Seven commits this session: `830a45b`, `f7e279f`, `3346593`, `2820b16`, `79d5610`, `a951e2c`,
`ec2a009`. Session diff `13002ff..HEAD`: **50 files, +3457 / −569.**

## Next steps

1. **Do section 0 of `2026-08-07-conversation-handoff-rework` — the stale references.** Five small,
   independent, fully-specified tasks, and the only unblocked work that needs no new design.
   Concretely, start with **0.3**: `src/agentweave/diagnostics.py:477` tells the operator to run
   `agentweave sync-context`, a command that no longer exists (the CLI is down to five commands —
   `status`, `doctor`, `stop`, `hub_start`, `reset`). Replace the hint with something real or
   delete it. Then 0.5 (`hub/hub/api/v1/agents.py` — the `compact_request` and `new_session_request`
   endpoints' stale wording), 0.1/0.2 (`AgentOutputPanel.tsx:48-60`, `HANDOFF_PROMPT` and
   `RESUME_HANDOFF_PREFIX` — the prefix names `.agentweave/shared/context.md`, a path that
   **exists nowhere**; the real file is `.agentweave/context/<agent>.md` and is already injected),
   and 0.4 (decide whether `src/agentweave/templates/skills/aw-checkpoint.md` should exist).
   **This is executable as written.**
2. **Or start section 4 — The Worker.** This is the checkpoint change's first real subsystem: a
   Hub-owned blocking spawn that generates a checkpoint from a conversation, reusing `Runner`
   records with an operator-chosen model. **Non-trivial — lay out the plan first**, per the carried
   directive. Read `design.md` decisions before proposing anything.
3. Carried from handoff 0020: the operator's own visual pass on light mode and `⋯` visibility.
4. Consider whether `hub/hub/static/ui` needs a rebuild before the next frontend commit (see
   "NOT verified").

## Open questions for the user

1. **Should this branch be pushed?** 290 commits, no upstream, never asked-and-answered across six
   handoffs now.
2. **Should `.claude/handoffs/` stay tracked?** 107 files.
3. Should `pytest-xdist` be added? The ~2:35 sweep is the main wall-clock cost, and the operator
   has flagged wall-clock before.
4. Carried: peer-thread presentation was deferred by the operator on 2026-08-08 — **and section 2
   just landed, so the navigation tree will now get busier.** Raise the grouping work as its own
   change when it becomes noticeable.

## Read on resume

- `openspec/changes/2026-08-07-conversation-handoff-rework/tasks.md` — **start here.** Sections 2
  and 3 record what was built and why; section 0 is the next executable work.
- `openspec/changes/2026-08-07-conversation-handoff-rework/design.md` — the 13 decisions. Read
  before questioning anything in sections 4–9.
- `openspec/explorations/2026-08-08-handoff-behaviour.md` — the captured evidence the change was
  written from, including the wrong-path finding behind task 0.2.
- `hub/hub/conversations.py` — `peer_bound_conversation`, the binding contract.
- `hub/hub/output_recording.py` — `resolve_usage_limit`, and why it fills gaps but never
  overwrites.
- `openspec/specs/agent-configuration/spec.md` — the capability archived this session; the
  posture, description and workspace requirements are the shipped contract now.
