# Handoff: two operator test rounds shipped — collaboration fixed, then permissions, tool schemas, and base knowledge

**Date:** 2026-08-07T00:33 · **Branch:** hub-native-experience · **HEAD:** d116929
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0011-2026-08-06-2055-composer-chrome-refinement-shipped-and-archived.md
**Status:** chunk complete. 17 commits. One openspec change built + synced + **archived**
(`2026-08-06-hub-collaboration-and-conversation-fixes`), one built + verified live but
**deliberately NOT archived, awaiting operator review**
(`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`). Databases were wiped and a fresh
testbed created mid-session at the operator's request.

## Goal

Resumed handoff-0011, whose top next-step was "triage whatever the operator reports from their
manual test". That happened twice, in two rounds, and the underlying purpose throughout was to make
AgentWeave's central premise — multiple agents collaborating under an operator — actually work
end-to-end rather than merely be wired up. Both rounds were driven by the operator's own live
testing, and in both rounds the first diagnosis was incomplete; the real causes were found only by
reading `agent_outputs` rows and by measuring against a live browser.

## Current state

### Round one — six reported defects, all fixed, change archived

Operator report (verbatim in Constraints below) listed six problems. All six shipped as
`openspec/changes/archive/2026-08-06-hub-collaboration-and-conversation-fixes/`.

1. **"claude doesn't seem to be getting my message" had TWO independent causes.**
   - **Cause A (context):** `_render_hub_agent_context` decided what to tell an agent by testing
     `declared = agent in session_data["agents"]`, read from the `project_sessions` table — whose
     only two writers (the CLI's `Session.save()` push and the watchdog) were deleted in
     `2026-08-03-single-runtime`. Every Hub-native agent was therefore permanently "undeclared" and
     received a stand-down block: *"do not modify files, do not claim tasks, send a short
     availability message to the principal"*. The roster was empty for the same reason, so agents
     could not name a peer — one 404'd sending to a literal agent called `principal`. Fixed:
     known-ness is now `agent_row is not None`, the block is deleted, and the roster is read from
     `agents` joined to `runners`.
   - **Cause B (delivery), found only after Cause A was fixed and agents *still* said "no task":**
     `claude` installs from npm as **`claude.CMD`**, a batch shim run by `cmd.exe`, which truncates
     a command line at the first raw newline. The Hub passes the whole turn prompt as one `-p`
     argument whose first line is the tool-access notice and whose later lines carry the operator's
     message — so every Claude run on Windows received *only* that notice. Proven by spawning
     through a `.cmd` shim and reading the child's own `argv`. `resolve_executable` now unwraps a
     `.cmd`/`.bat` to the `.exe` it delegates to, narrowly: only a shim whose payload is one quoted
     `.exe` followed by `%*` and nothing else. `codex` resolves to a real `.EXE` and was unaffected.
2. **`display_model: "Native"`** (the open question carried from handoff-0011) — same dead
   `project_sessions` source. Fixed by applying the `Agent.runner_id -> Runner` override before
   deriving display fields; unbound self-registered agents keep deriving from `Agent.config`.
3. **Codex could not collaborate** — the app-server transport that fixes it already existed and was
   verified, but sat behind an `--app-server` opt-in that the Add-agent dialog never set. Inverted:
   codex uses app-server unless a runner carries `--no-app-server`. New `uses_app_server()` is the
   single source of truth shared by the trigger path and the launchability probe.
4. **Operator message bubble** — dropped its 14% `--blue` wash for `--surface-2` / `--border`.
5. **"charcoal box inside a black box"** — removed `.conversation-composer-surface`'s
   `0 20px 52px rgba(2,5,18,0.28)` outer shadow and flattened `.conversation-composer-fade`'s
   gradient. Kept the inset top highlight.
6. **Turns folded themselves** — `foldOverride[key] ?? !isLastTurn` made foldedness a function of
   position. Now `?? false`; the per-turn fold control is unconditional so a single-turn
   conversation is still foldable.
7. **Cross-agent send removed** — `ComposerAgentSelector` deleted along with its `targetAgent`
   plumbing and the now-dead `onAgentConversationChange` prop. `collaboration_ready` moved to
   `AgentCard`.

**Live-verified before archiving** (project outside this repo — see Dead ends):
`haiku-a → haiku-b "Please respond with 'ok-agent'"`, `haiku-b → haiku-a "ok-agent"` (auto-woken),
`codex-a → haiku-a "codex-here"`.

### Environment reset (operator request, mid-session)

- Wiped `hub/data/agentweave.db`, `hub/data/agentweave-dev.db`, and the stray root `data/agentweave.db`.
  **Backed up first to `C:\Users\huida\Documents\aw-db-backup-2026-08-06\`** — not deleted outright.
- Removed three agent git worktrees with `git worktree remove` (they were registered in *this*
  repo's git, pointing into `testbed/`), then deleted six `agentweave/*` scratch branches after
  confirming they held nothing but two auto-snapshots of a one-line file.
- Deleted `.agentweave/` artifacts including two that `CLAUDE.md` forbids: one at the **repo root**
  and one in `hub/`. Both were accumulated test output.
- Deleted the earlier scratch project `C:\Users\huida\Documents\aw-livetest`.
- New instance identity minted; DB rebuilt through all 28 migrations.
- **Fresh testbed created: `C:\Users\huida\Documents\agentweave-testbed`**, project
  `proj-84d218db` ("Testbed"), agents `haiku-1`, `haiku-2` (claude / `claude-haiku-4-5-20251001`)
  and `codex-1`, `codex-2` (codex / `gpt-5.4-mini`), each pair sharing one runner.

### Round two — three failures + a base-knowledge overhaul, change NOT archived

Operator tested 16 items; 11 passed, 3 failed. Built as
`openspec/changes/2026-08-06-agent-permissions-tool-schemas-and-base-knowledge/` (in-flight).

1. **Claude could not write files — again two causes.**
   - `--permission-mode manual` means *ask the operator*, but the Hub spawns headlessly and no
     approval surface exists, so every write was refused. (The change that introduced `manual`,
     `2026-08-06-claude-non-yolo-permission-mode`, explicitly recorded this as never measured and
     deferred the approval surface to `2026-08-06-operator-in-the-loop-turns`, still deferred.)
     Default is now `acceptEdits`.
   - **Every denied path was the project root while the agent's cwd was its worktree.** `README.md`
     was inside that worktree. Nothing told the agent where it was. Codex only succeeded because it
     happened to use a relative path.
   - Added a **per-conversation Permissions control** (`permission_mode` in
     `CATALOG["claude"].controls`), rendering as a composer pill beside Model and Effort with no new
     endpoint, column, or component. Labels are written out — "Edit files" / "Ask first" / "Full
     access" — because `_enum` would derive "Acceptedits". `_build_claude_command` guards both the
     `--permission-mode` and `--dangerously-skip-permissions` branches so an override is not
     overridden by the flag appended later; without that guard the pill would look functional and do
     nothing.
2. **Codex's first `send_message` always 422'd** — `message_type` was a bare `str`, so the schema
   advertised no values. Claude omitted it (default) and always worked; Codex guessed `"text"`.
   Declared `Literal` on `send_message.message_type`, `create_task.priority`, `update_task.status`
   (no default, eight states — the next failure waiting to happen), and `create_job.session_mode`.
   Also reduced `HubAPIError`'s detail from a stringified list of Pydantic dicts to a sentence, and
   added the missing `direct_trigger` to `src/agentweave/constants.py`'s `MESSAGE_TYPES`.
3. **Conversation never followed output and opened at the oldest message** — the effect depended on
   `lines` (the legacy raw output log), not the entries the timeline renders, and nothing scrolled
   on open. Both fixed, plus a jump-to-newest control shown only while following is suspended.
4. **Base-knowledge overhaul** (operator: *"We need a complete overhaul because so much has
   changed"*):
   - Context gained **"Your workspace"** (absolute cwd, worktree branch, peers invisible, resolve
     paths against it) — `effective_work_dir` threaded in from `trigger_agent_directly`.
   - Context gained **"Your tools"**, generated from `mcp_server`'s own `Literal` aliases so it
     cannot drift, including the four job tools agents were never told about.
   - **Deleted** the `Canonical runtime context: .agentweave/context/<agent>.md` line — it pointed
     at a file the agent had already been given, and following it caused the session's first
     permission denial.
   - **All 21 seeded charters de-staled.** Charter text is inlined into the model context, so
     `Read roles.json, protocol.md, shared/context.md` was a live instruction to read files the Hub
     has never created. `shared/context.md` is doubly impossible: each agent has its own worktree.
     Charters telling agents to *update project instructions* were also instructing an
     impossible action (operator-only, no tool) — those now use the task ledger, `send_message`,
     or `ask_user`.
   - `access_path_notice`'s CLI-fallback branch no longer names commands removed in
     `2026-08-03-single-runtime`; `post_new_session_request` no longer says "Your principal";
     `STALLED_STATUS_MESSAGE` no longer tells the operator to restart the watchdog.

## Files touched

Full list is `git diff --name-only 8fef86a..HEAD` (78 paths). Grouped by what they are:

**Hub backend**
- `hub/hub/api/v1/agents.py` — canonical context rewritten (roster from Hub tables, "Your
  workspace", "Your tools" via new `_tool_surface_lines()`, context-path line deleted);
  `display_model`/`runner` derive from the bound Runner; `collaboration_ready` rule inverted;
  `post_new_session_request` text.
- `hub/hub/api/v1/agent_trigger.py` — codex transport default inverted; `work_dir`/`isolated`
  threaded into the context renderer.
- `hub/hub/pty_runner.py` — `_unwrap_cmd_shim()` + `resolve_executable` change (the truncation fix).
- `hub/hub/mcp_server.py` — `Literal` aliases, four tool signatures, `Args:` docstrings,
  `_readable_detail()`.
- `hub/hub/model_catalog.py` — `permission_mode` ControlDescriptor.
- `hub/hub/runner_commands.py` — `DEFAULT_CLAUDE_PERMISSION_MODE`, override guard, docstring.
- `hub/hub/codex_appserver.py` — `APP_SERVER_OPT_OUT_FLAG`, `TRANSPORT_SENTINELS`, `uses_app_server()`.
- `hub/hub/launchability.py` — `access_path_notice` CLI branch.
- `hub/hub/agent_status.py` — `STALLED_STATUS_MESSAGE`.
- `hub/hub/data/charters/*.md` — all 21 seeded charters.
- `src/agentweave/constants.py` — `MESSAGE_TYPES` gained `direct_trigger`.

**Hub UI**
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — scroll rewritten (layout effects,
  `scrollTop` assignment), jump-to-newest control, `targetAgent` plumbing removed.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — neutral operator bubble, no auto-fold,
  unconditional fold control.
- `hub/ui/src/components/agents/Composer.tsx` — selector and its props removed.
- `hub/ui/src/components/agents/ComposerAgentSelector.tsx` — **deleted**.
- `hub/ui/src/components/agents/AgentCard.tsx`, `AgentsPage.tsx` — collaboration-readiness badge.
- `hub/ui/src/App.tsx` — dead `onAgentConversationChange` handler removed.
- `hub/ui/src/index.css` — composer shadow + fade gradient.
- `hub/hub/static/ui/**` — committed build artefact, regenerated twice.

**Tests** — `hub/tests/`: `test_mcp_tool_schemas.py` (new), `test_agent_facing_text.py` (new),
`test_pty_runner.py`, `test_runner_parsing.py`, `test_agents_self_registered.py`,
`test_agent_trigger.py`, `test_agent_trigger_overrides.py`, `test_agents.py`,
`test_launchability.py`. `hub/ui/src/__tests__/`: `agentCardCollaboration.test.tsx` (new),
`conversationControls.test.tsx`, `agentTimeline.test.tsx`, `hubVisualLanguage.test.ts`,
`composerAgentSelector.test.tsx` (**deleted**).

**Specs** — `openspec/specs/` for `agent-composer`, `agent-context-onboarding`,
`agent-conversation-workspace`, `agent-tool-surface`, `runner-registry` (round-one deltas synced in);
plus both change directories.

**Pre-existing dirty files, untouched this session** (carried since handoff-0001):
`M .claude/handoffs/handoff-0001-...md`, `M Makefile`, and the untracked scratch paths listed in
Git state.

## Key decisions

1. **`acceptEdits`, not a Hub-answered approver, for now.** Operator chose "Both: toggle now,
   Hub-answered next". Claude's hidden `--permission-prompt-tool <tool>` flag is verified to exist
   (absent from `--help`, registered with `.hideHelp()`, accepts a value) and would let the Hub
   answer each request itself, mirroring `codex_appserver.decide_approval`. Deferred to its own
   change.
2. **Permission modelled as a model-catalog control, not a bespoke setting.** `ComposerModelControls`
   renders every `kind === 'enum'` control and the override path is control-id agnostic, so one
   descriptor buys pill + persistence + validation + argv rendering.
3. **An explicit per-conversation permission choice overrides the agent's standing `yolo` flag**,
   rather than emitting both flags. More specific and deliberate wins.
4. **MCP `Literal` values are restated in `mcp_server.py`, not imported from `hub.schemas`.**
   Deliberate deviation from the plan: that module is spawned as a standalone script from an
   arbitrary cwd by both transports and imports only stdlib + fastmcp. A package import would make
   the entire tool surface fail to start if layout changed. `test_mcp_tool_schemas.py` asserts the
   aliases match the validators instead.
5. **`.cmd` shim unwrapping is deliberately narrow** — only a payload of one quoted `.exe` followed
   by `%*` and nothing else. A JS shim (`node.exe cli.js %*`) bakes in an argument that argv[0]
   substitution would silently drop. Worst case is the previous behaviour, never a wrong command.
6. **Scrolling assigns `scrollTop` in a layout effect; no `requestAnimationFrame`, no smooth
   scroll.** Measured live: in a non-painting window rAF never fired and smooth scrolling left
   `scrollTop` at 0, while direct assignment landed immediately. My first implementation used both
   and was silently a no-op live — the tests could not see it because jsdom has no frame loop.
7. **Charters corrected in place, not deleted.** Their substance (scope, responsibilities, handoff
   rules) still matches the runner/agent/charter model; only the startup ritual and removed-subsystem
   references were wrong. Existing projects keep their stored copies — they are operator-editable.
8. **The testbed lives outside this repo.** A project inside the AgentWeave checkout inherits its
   `CLAUDE.md`, which forbids using AgentWeave there; an agent cited that rule verbatim and refused.
9. **Databases were backed up, not destroyed**, before the wipe.

## Constraints and user directives (verbatim)

- Round-one report: *"A couple of fixes from the last changes: claude doesn't seem to be getting my
  message. I've sent a clear instruction and it just ignored. The user message box in the
  conversation is too bright. Seems out of place, feels like it is using the old dark navy color
  palete. Let's remove the ability and the buttons that enable the user from one screen to send
  message to another agent. Is counter intuitive. Also codex not being able to be part of the
  collaboration defeats the purpose. We need codex collaborating. Around the conversation chat box
  seems to be a darker box. Feels weird. There is a charcoal chat box and then a black box around
  it? IT's weird. I don't want to altomatically fold previous conversation upon sending a new
  message."*
- *"I want you to clean the db and agentweave and start a fresh agentweave in a test folder with 2
  claude agents (haiku) and 2 codex agents (gpt mini)"*
- Round-two base-knowledge directive: *"Actually this should be in the "base knowledge" of every
  agent when it start in the repo. To understand it works within agent tree. We have to review all
  the base files generated in agentweave that teach the context tools etc. We need a complete
  overhaul because so much has changed"*
- Round-two permission ask: *"Do we make a way to pass the prompt to agentweave. I know that T3 code
  can do that. The code is in this machine. Is it a config to give permission? Can we create a
  button or toggle on the chat box like the other configs (model configs)."*
- `AskUserQuestion` decisions this session: single-provider model picker scope (round one, carried);
  codex transport = **"Invert the default"**; dark box = **"Both / not sure"**; folding = **"Never
  auto-fold"**; bubble = **"Fully neutral charcoal"**; permission fix = **"Both: toggle now,
  Hub-answered next"**; toggle scope = **"Per-conversation pill"**; MCP schema scope = **"Fix all
  four tools"**; overhaul scope = **"Rewrite injected context now, template tree separately"**;
  dead templates = **"Delete, keeping handoff/resume"**.
- From `CLAUDE.md`, load-bearing throughout: never create `.agentweave/`, `agentweave.yml`, or
  `spec/` at the repo root; stage paths explicitly, never `git add -A`; use openspec, never aw-spec
  skills, on this repo; `Icon` is the only icon system; never mark a task complete on the strength
  of a plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All 17 commits happened unprompted, each after its own test run.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at
  session start (re-ran `hub/tests/`, 766 passed, matching handoff-0011). **Repeating the directive
  for the next session.**

## Dead ends

- **Diagnosing "claude ignores my message" as purely a context bug.** The context fix was real and
  necessary but insufficient; agents still reported no task. Only reading `agent_outputs` payloads
  (not the agent's own paraphrase) and then spawning through a real `.cmd` shim found the argv
  truncation. **Lesson: the agent's narration of a failure is not evidence; the recorded tool
  payload is.**
- **Suspecting `--allowedTools "mcp__agentweave__*"` of restricting Read/Write.** Tested directly —
  `manual` + `allowedTools` both permitted reading a file inside cwd. Not the cause.
- **Suspecting the prompt was mangled by `PtySession`/pywinpty argv joining.** Tested with a script
  that echoes its own argv through `PtySession.spawn`: newlines and JSON survived intact. Only the
  `.cmd` shim path truncated.
- **First `.cmd`-unwrap rule matched "exactly one `.exe` anywhere in the file"** — the e2e test
  caught that it silently dropped a shim's baked-in script argument. Tightened to "payload is one
  quoted `.exe` plus `%*` and nothing else".
- **First scroll implementation used `requestAnimationFrame` + `scrollIntoView({behavior:'smooth'})`.**
  Passed every test, did nothing live. See Key decision 6.
- **`sed` with `^## ADDED Requirements$` to splice spec deltas** — CRLF line endings meant the
  anchor never matched, and it silently appended stray `---` separators to three main specs.
  Reverted with `git checkout` and redone in Python with explicit newline handling.
- **Inserting a new test class mid-file** silently absorbed the following tests into it
  (`test_claude_proxy_and_native_use_the_same_construction` ran as part of the wrong class). Moved
  the class after the original's end.
- **Two openspec requirements failed `validate --strict`** because the validator reads only the
  requirement's *opening line* for SHALL/MUST, and both buried it on line two. Reworded.
- **A flaky frontend test** (jump control) revealed a real race: the deferred open-scroll frame
  could undo an operator scroll. Later removed entirely with the rAF rewrite.

## Verification

**Ran, with real output, final state:**
- `pytest hub/tests/ -q` — **841 passed, 9 skipped** (766 at session start).
- `pytest tests/ -q` (CLI) — **372 passed, 3 skipped**.
- `cd hub/ui && npx vitest run` — **465 passed** (458 at session start), stable across repeated
  full runs.
- `npx tsc --noEmit` — clean.
- `ruff check` on every touched Python file — clean, except one pre-existing SIM117 in
  `hub/tests/test_agent_trigger.py` and pre-existing SIM105s in `hub/hub/codex_appserver.py`, both
  confirmed against a stashed clean tree.
- `npx openspec validate --specs --strict` — **24 passed, 0 failed**.
- `npm run build` + `pytest hub/tests/test_ui_staleness.py` (5 passed); `hub/hub/static/ui`
  regenerated and committed.
- **Live**, against a Hub restarted on this code (`127.0.0.1:8010`, key
  `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` from `hub/.env`), project `proj-84d218db`:
  - `haiku-1` created `notes.md` with no permission error and reported its cwd as
    `...\.agentweave\worktrees\haiku-1`.
  - With `overrides={"permission_mode":"manual"}`, the exact original refusal returned and no file
    was created — proving the control reaches argv.
  - `codex-1`'s **first** `send_message` succeeded with **zero 422s**, and it chose
    `message_type: "direct_trigger"` — a valid non-default value it could only know from the enum.
  - Conversation opens at the newest entry (`distanceFromBottom: 0`); jump control appears only when
    scrolled away, returns the view, and hides again.
  - `GET /agents/agent-context` contains no `roles.json`, `principal`, `agentweave.yml`,
    `.agentweave/context/`, `watchdog`, or `protocol.md`.

**Explicitly NOT run/tested — do not assume:**
- **The composer Permissions pill was never clicked in a browser.** It was verified through the API
  (`overrides={"permission_mode":"manual"}`) and through `ComposerModelControls`' catalog-driven
  rendering, but no live click. The catalog mock in `conversationControls.test.tsx` returns
  `undefined`, so no test renders it either.
- Following new output *live* was not observed with content actually growing in a visible
  conversation — the test run created a new conversation, so that view's content did not change.
  Covered by jsdom tests and by the same `scrollTop` path proven live for open/jump.
- No charter has been bound to any agent and exercised; the de-staled charter text has never been
  in front of a model.
- `bypassPermissions` ("Full access") was never exercised live.
- The `--permission-prompt-tool` approach is **researched only** — not implemented, not tested.
- Light-mode was not re-checked this round (it was verified in round one).
- Existing projects' *stored* charters are unchanged by design; only newly seeded projects get the
  corrected text. Not verified what an old project now shows.

## Git state

Branch `hub-native-experience`, HEAD `d116929`, **no upstream — nothing has ever been pushed on this
branch** (carried from every prior handoff).

17 commits this session, oldest to newest: `153ed94`, `d5899dc`, `4b9604f`, `d63f2c5`, `d5f82c2`,
`e761741`, `0b40063`, `1caa1ce`, `255a941`, `b98e595`, `59fcb69`, `a101586`, `af144fa`, `d4c205c`,
`828718b`, `e116ae0`, `d116929`. Verified via `git log --oneline 8fef86a..HEAD` (`8fef86a` was
handoff-0011's final HEAD).

Uncommitted, all pre-existing, none from this session: `M .claude/handoffs/handoff-0001-...md`,
`M Makefile`. Untracked: `.claude/handoffs/*` (this chain), `.claude/skills/{handoff,resume,review-iteration}/`,
`openspec/explorations/2026-08-03-specification-authority-technical.md`, `scripts/`,
`src/agentweave/templates/skills/{handoff,resume}.md`, `tests/test_handoff_resume_templates.py`.
Note `data/` no longer appears — that stray root database was deleted during the environment reset.

## Live environment

- **Hub dev server on `127.0.0.1:8010`** — uvicorn from `hub/`, background, no `--reload`, running
  HEAD `d116929`. Log at `/tmp/hub-dev-8010.log`. Disposable; kill any time. Started with
  `python -m uvicorn hub.main:app --host 127.0.0.1 --port 8010` using
  `C:/Users/huida/AppData/Local/Programs/Python/Python311/python.exe` (the only interpreter here
  with pytest/fastapi/sqlalchemy).
- **Project `proj-84d218db` ("Testbed")** at `C:\Users\huida\Documents\agentweave-testbed` — its
  own git repo, deliberately outside this checkout. Agents `haiku-1`, `haiku-2`, `codex-1`,
  `codex-2`. Contains real conversation history, messages, and worktrees under
  `.agentweave/worktrees/<agent>` from this session's verification.
- **Database backup** at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` — the pre-wipe
  `agentweave.db` and the stray root one. Nothing depends on it; delete when comfortable.
- All previous test projects (`proj-de54b547`, `proj-d9b5ed67`, `proj-a35df4bc`, `Agentweave`) are
  **gone** — the database was wiped.

## Next steps

1. **Operator review of `openspec/changes/2026-08-06-agent-permissions-tool-schemas-and-base-knowledge/`,
   then sync + archive it.** Implementation and all 7 task sections are complete and verified; it was
   left in-flight deliberately. Archiving means: hand-sync the five delta specs
   (`agent-run-sandboxing`, `agent-tool-surface`, `agent-context-onboarding`,
   `agent-conversation-workspace`, `agent-charter`) into `openspec/specs/`, run
   `npx openspec validate --specs --strict`, then `git mv` the change into
   `openspec/changes/archive/`. **The openspec CLI's `--change` flag remains broken for
   date-prefixed names** — hand-edit the spec files, as done twice already this session.
2. **Click the Permissions pill in a browser.** It is the one part of section 2 with no live or
   jsdom coverage (see Verification). Open
   `http://127.0.0.1:8010/?project=proj-84d218db&agent=haiku-1`, confirm a "Permissions" pill sits
   beside Model and Effort, switch it to "Ask first", send a write instruction, and confirm the
   refusal — the API-level equivalent already passes.
3. **Follow-up change: the Hub-answered permission approver.** Add one MCP tool to
   `hub/hub/mcp_server.py` and pass `--permission-prompt-tool mcp__agentweave__<tool>` from
   `_build_claude_command`. The handler mirrors `hub/hub/codex_appserver.py`'s `decide_approval`
   (allow in-workspace and the Hub's own tools, deny outside, never leave a request unanswered).
   Response shape is `{behavior: 'allow'}` / `{behavior: 'deny', message: string}`.
4. **Follow-up change: delete `src/agentweave/templates/`.** All 33 files are orphaned —
   `get_template`/`get_skill_template` have zero call sites outside their own module and two tests,
   and neither the Hub nor the five-command CLI writes them. Operator decided: delete, **keeping
   `handoff.md` and `resume.md`**. Also remove `tests/test_packaging.py`'s template assertions and
   the stale `tests/__pycache__/test_skill_templates.*.pyc`, and correct `CLAUDE.md`, which still
   describes the templates as live (`line 137`) and documents CLI commands that no longer exist
   (`agent configure`, `run`, `switch`, `mcp-setup`).
5. **Bind a charter to an agent and run it** — the de-staled charter text has never reached a model.

## Open questions for the user

1. Should `hub-native-experience` be pushed? Still no upstream, now 17 commits further ahead.
2. Should the Hub gain project/agent deletion? This session required deleting SQLite files by hand,
   `git worktree remove`, and branch pruning because nothing in the product can remove anything.
3. `M .claude/handoffs/handoff-0001-...md` and `M Makefile` — intentional WIP, or commit/revert?
   Carried unresolved since handoff-0001.
4. `npm run lint` in `hub/ui` does not start (ESLint 9 installed, no flat config). Pre-existing;
   fix or drop the script?
5. `session/sync`'s destructive-replace semantics — `project_sessions` is now fully dead for context
   and holds only quality gates, which nothing in the Hub can set. Delete the table and endpoint?
6. The `review-0002` agent-name uniqueness gap — still open, still not investigated.
7. `64dbb4b "Add harness-audit and harness-refresh skills"` — still unexplained.
8. `item/permissions/requestApproval`'s yolo-grant shape — still never observed live.
9. Task 8.11 from the archived `2026-08-04-hub-model-control-and-provisioning` (live confirmation no
   agent reports context usage above 100%) is still unresolved in the archive.
10. Should the database backup at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept?

## Read on resume

- `openspec/changes/2026-08-06-agent-permissions-tool-schemas-and-base-knowledge/tasks.md` — the
  in-flight change's per-task implementation record; read before archiving it (next step 1).
- `hub/hub/api/v1/agents.py` — `_render_hub_agent_context` and `_tool_surface_lines`; the largest
  behavioural change of the session and where any further base-knowledge work lands.
- `hub/hub/pty_runner.py` — `_unwrap_cmd_shim`; read if any Windows spawn or prompt-delivery
  question resurfaces.
- `hub/hub/runner_commands.py` + `hub/hub/model_catalog.py` — the permission default and the
  `permission_mode` control, for next steps 2 and 3.
- `hub/hub/codex_appserver.py` — `decide_approval`, the template the Claude approver should mirror.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — the scroll rewrite and the reason it does
  not use `requestAnimationFrame`.
