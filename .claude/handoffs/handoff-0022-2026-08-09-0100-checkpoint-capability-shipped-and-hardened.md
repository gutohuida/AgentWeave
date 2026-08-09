# Handoff: conversation-checkpoint finished and archived, then hardened against live testing

**Date:** 2026-08-09T01:00 · **Branch:** hub-native-experience · **HEAD:** `4053325`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0021-2026-08-08-1815-config-page-archived-checkpoint-prereqs-done.md`
**Status:** chunk complete. 15 commits, all pushed. **Working tree clean.**

## Goal

Two phases, both finished:

1. Finish `2026-08-07-conversation-handoff-rework` — all 60 tasks — then sync its specs and
   archive it. The operator's instruction: *"continue developing non stop until you finish this
   entire spec."*
2. Then fix what live testing found. The operator tested it and reported five problems; four were
   real defects and one was a design change they asked for.

The *why*: the old handoff asked the agent to invoke a skill AgentWeave never installed and write
to a path outside its worktree. Observed twice — once producing a good artifact somewhere
unreachable, once producing nothing and asking a question back. **Both reported "Handoff ready",
because readiness meant the run had ended.** The whole capability exists to replace that with a
Hub-generated record that is graded against the database.

## Current state

### `2026-08-07-conversation-handoff-rework` — **60/60, synced, archived**

Moved to `openspec/changes/archive/`. Its `conversation-checkpoint` delta became a **new shipped
capability** at `openspec/specs/conversation-checkpoint/spec.md` (11 requirements).
`npx openspec validate --specs --strict` → **27 passed** (was 26).

What shipped, by section:

| section | what it is |
|---|---|
| 4. The Worker | `hub/hub/worker.py` — generic one-shot model call, 8 outcomes, never raises |
| 5. The record | `Checkpoint` + `hub/hub/checkpoints.py` — computed envelope, `0043`–`0044` |
| 6. Generation | `hub/hub/checkpoint_generation.py` — prompt, body, blind-resume probe |
| 7. Access | `hub/hub/checkpoint_access.py` — two grants, citations, recall |
| 8. Lifecycle | `checkpoint_policy.py`, `checkpoint_cutover.py`, `checkpoint_trigger.py` |
| 9 + 0 | rename, dead prompts deleted, stale CLI references fixed |

### Two follow-up changes — **complete, NOT archived**

Both are 100% done and validate. They exist because live testing found gaps.

| change | tasks | what |
|---|---|---|
| `2026-08-09-checkpoint-configuration-surface` | 16/16 | the settings UI, and a destructive save bug |
| `2026-08-09-checkpoint-warning-before-spend` | 12/12 | `offered` warns instead of generating |

**Neither has been synced or archived.** That is next-step 1.

### Other in-flight changes (untouched this session)

| change | tasks |
|---|---|
| `2026-07-30-hub-native-experience` | 119 done / **69 open** — biggest remaining front |
| `2026-08-04-hub-contextual-navigation` | 43 / **2 open** — both need a *human*, see below |
| `2026-08-04-hub-charcoal-visual-refresh` | 39 / **3 open** — same |
| `2026-08-07-spec-execution-coordinator` | 0 / 29 — **gated skeleton, DO NOT START**, fails validate by design |

**The five open tasks in the two nearly-done changes are all marked "not run — tool limitation,
not skipped".** They need live keyboard traversal, numeric contrast ratios, and
`prefers-reduced-motion` — none of which the available browser automation can do (it emulates
`prefers-color-scheme` only). Twenty minutes of operator time archives two changes.

### Live environment

Hub running detached on **http://localhost:8010**, restarted many times. Project
**`proj-84d218db` ("Testbed")**, API key `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (also in
`hub/.env` as `AW_BOOTSTRAP_API_KEY`). **Database at alembic `0050`.** Restart:

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

**Project checkpoint config as left:** `offered`, threshold **150000 tokens**, notes at
**15000**, runner `runner-f1140195` (Claude Code — Haiku 4.5), model
`claude-haiku-4-5-20251001`, `checkpoint_auto_continue` **false**.

**Agents `opus-1` and `opus-2` each have an agent-level override:** `offered`, `tokens`, **1000**.
That is a testing value — at 1k every turn crosses it. Reset or raise before normal use.

**Testbed state changed and not restored:** several real checkpoints exist (`ckpt-*`), a synthetic
task `task-probe-check` and question `q-probe-check` were seeded on `proj-84d218db` for probe
verification, and `conv-c311b78f` is left marked `checkpoint_warning='due'`. Operator said
*"no need for backups everything is test env"*.

## Files touched

Everything is **committed and pushed**; working tree clean. `hub/hub/static/ui/` is the committed
build artefact, rebuilt and `diff -rq` verified after every frontend commit.

### New backend modules

- `hub/hub/worker.py` — one-shot model invocations. `build_worker_command`, `_run_worker_process`,
  `parse_claude_envelope` / `parse_codex_envelope`, `extract_json_object`, `run_worker`.
- `hub/hub/checkpoints.py` — the computed envelope. `compute_envelope`, `runs_to_cover`,
  `create_checkpoint`, `latest_checkpoint`, `TASK_SCOPE_NOTE`.
- `hub/hub/checkpoint_generation.py` — prompt, `CheckpointBody`, `render_body`,
  `render_checkpoint`, `grade_probe`, `generate_checkpoint`, `probe_checkpoint`, `pending_notes`.
- `hub/hub/checkpoint_access.py` — `may_read_checkpoint`, `may_recall`, `build_citations`,
  `recall_observation`, `participants`.
- `hub/hub/checkpoint_policy.py` — `resolve_policy`, `threshold_error`, `describe_threshold`,
  `crosses`, `should_checkpoint`, `should_request_notes`.
- `hub/hub/checkpoint_cutover.py` — `cut_over`, `successor_title`, `delivery_content`,
  `CutoverRefusedError`.
- `hub/hub/checkpoint_trigger.py` — `consider`, `consider_from_reading`, `_declined`,
  `_in_flight`, `_dispatched`.
- `hub/hub/api/v1/checkpoints.py` — list, rendered, take, cutover, continue, dismiss-warning.

### Migrations (nine new; head is `0050`)

`0042` worker_invocations · `0043` Run.snapshot_commit_sha · `0044` checkpoints ·
`0045` checkpoint_notes · `0046` project+agent checkpoint policy · `0047` queue-entry
`checkpoint` origin (table rebuild, follows `0019`) · `0048` grants + citations ·
`0049` Project.checkpoint_auto_continue · `0050` Conversation.checkpoint_warning.

Head assertions bumped in `hub/tests/test_migrations.py` **and**
`hub/tests/test_project_persistence.py`.

### Modified backend

- `hub/hub/db/models.py` — `Checkpoint`, `CheckpointNote`, `WorkerInvocation`; new columns on
  `Project`, `Agent`, `Conversation`, `Run`; `checkpoint` added to the inbound-queue origin checks.
- `hub/hub/output_recording.py` — **resolves `conversation_id` onto the usage payload** and calls
  `consider_from_reading(project_id, agent, payload.get("conversation_id"), payload)`.
- `hub/hub/api/v1/agent_trigger.py` — captures `snapshot_worktree`'s SHA at both sites.
- `hub/hub/api/v1/projects.py` — `ProjectSettings` gains the checkpoint fields; **`PUT` now merges
  with `exclude_unset=True`** and validates the merged state.
- `hub/hub/api/v1/agents.py` — checkpoint override + grants on PATCH and in `list_agents`; the two
  stale `/aw-checkpoint` inbox messages rewritten.
- `hub/hub/api/v1/agent_actions.py` — `submit_checkpoint_notes` endpoint, `recall` endpoint.
- `hub/hub/api/v1/agent_chat.py` — `checkpoint_warning` on the conversation response.
- `hub/hub/api/v1/inbound_queue.py` — `conversation_id` on `QueueEntryResponse`.
- `hub/hub/mcp_server.py` — `submit_checkpoint_notes` and `recall` tools.
- `hub/hub/worktrees.py` — `files_changed_in`.
- `hub/hub/inbound_queue.py` — accepts `origin_type="checkpoint"`.
- `hub/hub/schemas/agents.py` — checkpoint override + grant fields.

### Modified CLI

- `src/agentweave/diagnostics.py` — four dead `agentweave sync-context` hints corrected.
- `src/agentweave/constants.py`, `templates/ai_context.md`, `templates/claude_context.md`,
  `templates/kimi_context.md` — same dead command.
- `src/agentweave/templates/skills/aw-checkpoint.md` — **deleted** (task 0.4).

### Frontend

- `hub/ui/src/api/checkpoints.ts` — **new.** `useCheckpoints` (SSE-subscribed), `takeCheckpoint`,
  `cutOver`, `continueConversation`, `dismissCheckpointWarning`.
- `hub/ui/src/api/projects.ts` — `ProjectSettings` interface, `useProjectSettings`.
- `hub/ui/src/api/queue.ts` — `useQueuedEntries`.
- `hub/ui/src/api/agents.ts` — checkpoint override + grant hooks and fields.
- `hub/ui/src/api/agentChat.ts` — `checkpoint_warning` field.
- `hub/ui/src/api/client.ts` — `readableApiError`.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — **heavily changed.** Handoff prompts
  deleted, `handleCheckpoint` / `handleContinue` / `handleCutOver` / `handleDismissWarning`,
  two banners, `warningDismissed` local flag.
- `hub/ui/src/components/agents/BannerStack.tsx` — `tone`, `action`, `secondaryAction`.
- `hub/ui/src/components/agents/ConversationControls.tsx` — "Checkpoint" label, `ready` state
  removed from `HandoffState`, non-compact context indicator.
- `hub/ui/src/components/agents/AgentSettingsControls.tsx` — `CheckpointOverrideSetting`,
  `CheckpointGrantsSetting`.
- `hub/ui/src/components/agents/AgentSettingsPage.tsx` — Context and Access sections filled;
  `NotYetPopulated` deleted.
- `hub/ui/src/components/environment/ProjectSettingsPanel.tsx` — **rewritten** to round-trip the
  whole settings object; all checkpoint controls; `describeThreshold`.
- `hub/ui/src/components/context/contextPresentation.ts` — label now `28.9k / 1M · 3%`.
- `hub/ui/src/App.tsx` — an agent with no conversations gets the start surface.

### Tests added

`hub/tests/`: `test_worker.py` (23), `test_checkpoint_record.py` (16),
`test_checkpoint_generation.py` (19), `test_checkpoint_notes.py` (9), `test_checkpoint_policy.py`
(25), `test_checkpoint_cutover.py` (23), `test_checkpoint_access.py` (15),
`test_checkpoint_configuration.py` (14).
`hub/ui/src/__tests__/`: `agentCheckpointSettings.test.tsx` (7), plus rewrites of
`agentHandoff.test.tsx` (8) and `projectSettingsPanel.test.tsx` (7).

## Key decisions

1. **The probe reads the whole rendered checkpoint, not the model's prose alone.** The generation
   prompt is *forbidden* from asking for computed fields, so a well-formed body legitimately
   contains no file list — a body-only probe would fail every correct checkpoint. Reading the
   artifact as a successor receives it catches what is real: a body contradicting the envelope,
   and a render that drops the envelope.
2. **A probe that cannot run leaves the checkpoint `ready`, `probe_status` NULL.** An unrunnable
   grader is the Hub's failure, not the checkpoint's.
3. **`status <> 'ready' OR body IS NOT NULL` is a schema constraint**, not just a rule in
   `create_checkpoint`. The defect being removed is a readiness signal that meant "the run
   stopped"; making the empty-but-ready state unrepresentable stops it returning.
4. **`Run.snapshot_commit_sha` was a discovered prerequisite.** `snapshot_worktree` always
   returned the SHA and both call sites discarded it. One worktree is shared by all of an agent's
   concurrent conversations and every auto-snapshot has an identical message, so timestamp
   matching is guesswork. **No backfill** — historical conversations report no changed files.
5. **`checkpoint` is its own queue-entry origin.** Under `automatic` no operator asked and no
   agent sent it, so `operator`/`agent` would misstate provenance.
6. **Two independent grants**, because summary access is not transcript access. **Neither is
   readable from a charter** — a charter is text a model reads, so it must not widen access. There
   is a test for that.
7. **Participation stays derived** (`Task.created_by_run_id → Run`), lineage stored. Conflating
   them gives a `lineage_id` that means two things.
8. **`PUT /settings` merges with `exclude_unset=True`**, and validates the *merged* state.
   Validating the fragment would refuse a lone notes value for wanting a threshold the project
   already has.
9. **`offered` warns instead of generating** (the operator's request). Generation still happens
   *the moment they say yes*, never deferred — a checkpoint can only be written from the context
   about to be lost.
10. **`Conversation.checkpoint_warning` is one column with three states**, not two booleans:
    `warned` + `dismissed` makes "dismissed but never warned" representable.
11. **Dismissal is final for a conversation, not a lineage.** A successor is created NULL.
12. **`model_is_declared` accepts exact ids only**, matching `runners._reject_undeclared_model`,
    not the alias resolution `context_window_for_model` does.

## Constraints and user directives (verbatim)

**From this session:**
- *"I'm going to prepare dinner and eat. Continue developing non stop until you finish this entire
  spec."*
- *"Okay for everything."* — approving auto-continue, the context readout, and the new-agent screen.
- *"Let's make it so instead of automatically generating one is more like a warning. A warning
  shows that we can dismiss and then it does not show again if we dismiss. This way is better
  because if I want to extend a little longer I can"*
- *"It's counter intuitive to send a message to continue I want a config of auto continue on
  compact and if not the user need a button to send the new message and start the turn and not
  send a message to continue."*
- *"We need to show a warning like a model check the model context window (also the context
  windows should be a config on the chat bar)"* — **the second half is NOT done.** See open
  questions.
- *"I can't see easily the amount of token being used or the context filling, where is it?"*

**Carried and still binding:**
- *"Wait. Are you already implementing? Should we dive in first to see what to do or at least give
  me the plan on what are you doing so I can make a more informed decision."* — **lay out the plan
  before building anything non-trivial.**
- *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*
- *"we need to add a allow auto checkpoint with a box allowing to chose the percentage or the
  amount of tokens ... the count should be in K tokens so the user just sets 150, 200, 300"* —
  **done this session.**
- *"okay let's ok with i for v1 but we need to take a hard note on this because I'm for sure going
  to forget this in the future."* — memory `project_checkpoint_trigger_prompts_provisional`.
- *"no need for backups everything is test env"*
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*
- *"What is taking so long?"* — **the operator is sensitive to wall-clock.** `pytest hub/tests/` is
  ~3:00–4:00 for 1262 tests; `npx vitest run` ~15–20s. Targeted files during dev, one full sweep
  before committing.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; **live-verify prior claimed work
  on resume**.

## Dead ends

**New this session:**
- **`asyncio.create_task` needs a strong reference.** The loop holds only a weak one; a task whose
  only reference was a local can be collected mid-flight. This silently killed the checkpoint
  trigger, and because the collected task never ran its `finally`, the conversation stayed in
  `_in_flight` forever. Fixed with a module-level `_dispatched` set.
- **`UsageSample.to_payload` carries no `conversation_id`.** Cost hours. The trigger dropped every
  reading at its first guard. Confirmed against 677 stored readings: null on every one.
- **Then I read it back from the wrong variable** — `sample_payload` rather than `payload`. Same
  symptom, second time. **When resolving a value into a copy, check every later read.**
- **`PUT /settings` replaced from Pydantic defaults**, so the six-field settings form silently
  reset all eight checkpoint fields. Reproduced live before fixing.
- **Adding a hook to a component breaks every test that mocks that api module** — 35 vitest
  failures from adding `useQueuedEntries`. Patch the mocks in the same commit.
- **`openspec validate` wants SHALL/MUST on the *first line* of a requirement body.** A wrapped
  `SHALL` on line 2 fails with "must contain SHALL or MUST".
- **Bash heredocs break on apostrophes.** `cat > file <<'EOF'` with `operator's` in the body
  produced "unexpected EOF". Use the Write tool for prose files.
- **`git add -A` swept in a stray `hub/hub/data/agentweave.db`** created by a script that ran from
  the package directory. Now gitignored.

**Carried and still true:**
- **Bash-tool cwd resets between calls, unpredictably.** Bit me ~5 times this session. **Always
  `cd /c/Users/huida/Documents/projects/AgentWeave && …` first**, or use absolute paths.
- **`ORDER BY EventLog.id` does not order by recency** — bit me again while debugging the trigger.
  Order by `timestamp`.
- **`openspec` CLI cannot handle date-prefixed change names for sync/archive.** Do it by hand.
  `npx openspec validate <name> --strict` (no `change/` prefix) does work.
- **`npm run lint` does not work at all.** ESLint 9 needs a flat config the repo lacks; `tsc` is
  what checks. `ruff check hub/hub/` reports **3 pre-existing errors** (`jobs.py`,
  `codex_appserver.py`) — none mine.
- **`pytest hub/tests/ tests/` together fails collection** — both trees have `tests/__init__.py`,
  so `tests.*` is ambiguous. Run separately, as `make test-all` does. **Pre-existing.**
- **The default `python` on PATH has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **The live DB is `hub/data/agentweave.db`**; `cd hub` first, table is `event_logs` (plural).
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.
- `extra: "forbid"` rejects a forbidden **key** regardless of value; there is **no `db_session`
  fixture** — use `async_session_factory()`; `preview_snapshot` returns ~25k tokens.

## Verification

**Ran, with real output:**
- `pytest hub/tests/` at each commit: 1116 → **1262 passed, 10 skipped** (~3:00–4:00).
- `pytest tests/` (CLI): **372 passed, 3 skipped.**
- `npx vitest run` → 600 → **638 passed / 73 files.**
- `npx tsc --noEmit` → clean at every frontend commit.
- `ruff check` on every touched file → clean (3 known pre-existing elsewhere).
- `npx openspec validate --specs --strict` → **27 passed, 0 failed** (was 26).
  `--changes --strict` → 5 passed, 1 failed (the gated skeleton, by design).
- `npm run build` + copy to `hub/hub/static/ui` + `diff -rq` → identical, every frontend commit.
- **Live, against `:8010` with real CLI spawns:**
  - Worker one-shot on **both** providers: `claude` ok 7.3s/31074 µ$, `codex` ok 9.7s; an
    undeclared model refused **before** spawning.
  - `ckpt-3377549f` on a real 10-run conversation: ready, probe passed, 18.8s. Its body recovered
    a genuine cross-agent worktree-isolation dead end.
  - Seeded real ground truth (`task-probe-check`, `q-probe-check`) and confirmed a blind reader
    recovered both; graded the failure direction directly too.
  - Anchoring and lineage observed live (`ckpt-052550e1` → previous `ckpt-3377549f`).
  - After the trigger fix: a real 50,000-token reading against opus-1's 1,000-token threshold
    produced `ckpt-588eef9a`, `context_pressure`, ready, probe passed.
  - After the warning change: a real opus-2 turn under `offered` left `conv-c311b78f` marked
    `due` with **no worker invocation at all**.
  - The exact partial `PUT` that wiped the config now preserves it; explicit null still clears.

**Explicitly NOT verified — do not assume:**
- **No UI has been driven in a browser this session.** The Checkpoint button, Continue button,
  offer banner, warning banner, settings controls and agent controls are **unit-tested only**.
  The operator drove some of it and reported back; that is the only browser evidence.
- **No live agent has ever called `submit_checkpoint_notes`.** The whole notes design assumes a
  real model treats it as a tool call rather than replying in prose. Untested.
- **`recall` has never been called by a live agent.**
- **The senderless peer path and the peer archive-successor path** remain API-test only.
- **`files_changed` has never been observed non-empty in production** — every conversation tested
  predates `Run.snapshot_commit_sha`.
- The five manual-verification tasks in the two nearly-done changes (keyboard, contrast,
  reduced-motion) — **cannot** be done with available tooling.

## Git state

Branch `hub-native-experience`, HEAD **`4053325`**, **working tree clean, everything pushed.**
Upstream exists now (`origin/hub-native-experience`) — pushed for the first time this session
after six handoffs of asking.

**15 commits this session**, `9717e48..HEAD`: **95 files, +10414 / −851** (includes the rebuilt
`hub/hub/static/ui` bundle).

## Next steps

1. **Sync and archive the two completed changes.** Both are 100% done and validate:
   `2026-08-09-checkpoint-configuration-surface` and `2026-08-09-checkpoint-warning-before-spend`.
   Concretely: apply each `specs/conversation-checkpoint/spec.md` delta into
   `openspec/specs/conversation-checkpoint/spec.md` — the first is a **MODIFIED** of "Automatic
   checkpointing is configured as a threshold in proportion or in tokens" (replace in place), the
   second is an **ADDED** requirement "Crossing the threshold warns before it spends" (append).
   Then `git mv` both into `openspec/changes/archive/`, and re-run
   `npx openspec validate --specs --strict` (expect 27 passed). **Do this by hand — the openspec
   CLI cannot handle date-prefixed names.**
2. **Ask the operator to close the five manual-verification tasks** in
   `2026-08-04-hub-charcoal-visual-refresh` (8.8, 8.9, 8.10) and
   `2026-08-04-hub-contextual-navigation` (4.7, 7.7). Two changes archive on the back of it.
3. **Decide the "context window as a config on the chat bar" item** — see open questions.
4. **Reset the testing thresholds** on `opus-1` and `opus-2` (currently 1000 tokens, which fires
   every turn) before any realistic use.
5. Then the biggest open front is `2026-07-30-hub-native-experience` (69 open), concentrated in
   *specification traceability and authoring* (19) and *agent identity, charters and skills* (15).
   **Read those two sections before proposing an order — it is several changes wearing one number.**

## Open questions for the user

1. **"the context windows should be a config on the chat bar"** — I made the window *visible* in
   the conversation header (`28.9k / 1M · 3%`) but did not make it *configurable* there. Unclear
   whether they want the model picker surfaced on the composer (it exists in runtime overrides
   already) or something else. **Ask before building.**
2. **The 95% gap.** Claude Code auto-compacts near 95%, so a conversation dismissed early and run
   to exhaustion gets no second warning and no checkpoint. I offered a single final
   non-dismissible warning near the window; they have not answered.
3. **Per-agent notes point is not settable.** The project-level one is; the agent control sends
   `notes: null`. Left out rather than inventing a field they may not want per-agent.
4. **Should `.claude/handoffs/` stay tracked?** 108 files now. Unanswered across seven handoffs.
5. Carried: peer-thread grouping was deferred on 2026-08-08 and section 2 has now landed, so the
   navigation tree will be busier. Raise as its own change when it becomes noticeable.
6. **23 skill templates in `src/agentweave/templates/skills/` are packaged but unreachable** —
   nothing installs them. `aw-checkpoint.md` was deleted because task 0.4 decided it; the rest
   need their own change.
7. Design says **titling should migrate onto the Worker**; it is still bespoke in
   `conversation_titles.py`.

## Read on resume

- `openspec/changes/2026-08-09-checkpoint-warning-before-spend/specs/conversation-checkpoint/spec.md`
  — the delta to sync first; small and self-contained.
- `openspec/changes/2026-08-09-checkpoint-configuration-surface/specs/conversation-checkpoint/spec.md`
  — the MODIFIED delta; replaces an existing requirement in place.
- `openspec/specs/conversation-checkpoint/spec.md` — the shipped capability both apply to.
- `hub/hub/checkpoint_trigger.py` — where three separate wiring defects lived; read
  `consider_from_reading` before touching the dispatch.
- `hub/hub/output_recording.py` — `record_context_usage` resolves the conversation and calls the
  trigger. The `payload` vs `sample_payload` distinction is load-bearing.
- `testbed/CHECKPOINT-TEST-GUIDE.md` — the operator's testing checklist, still current.
