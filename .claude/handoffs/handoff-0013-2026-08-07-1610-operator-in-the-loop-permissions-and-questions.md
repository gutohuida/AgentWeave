# Handoff: operator-in-the-loop permissions and questions, shipped; five follow-ups decided

**Date:** 2026-08-07T16:10 · **Branch:** hub-native-experience · **HEAD:** 96884f4
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0012-2026-08-07-0033-permissions-tool-schemas-and-base-knowledge.md
**Status:** chunk complete. 12 commits. Everything below is implemented, tested and
live-verified. The operator then chose five follow-ups (Next steps 1–5) — none started.

## Goal

Make an agent able to **stop and involve the operator** rather than guess: ask permission before
acting, and ask a question when a decision is genuinely the operator's. Driven throughout by the
operator's own live testing, in the same loop as handoff-0012.

The session ended with the operator saying *"I'm kind of lost right now"* and asking for a plain
explanation, then choosing follow-ups from the limitations list. Those choices are Next steps 1–5
and the reasoning behind each is in Key decisions.

## Current state

### Shipped and live-verified

**1. Permissions — who decides what an agent may do.** The composer's Permissions pill offers four
postures for *both* providers, same labels:

| Posture | id | Who answers |
|---|---|---|
| Edit files | `acceptEdits` | nobody — the unchanged default |
| Workspace only | `workspace` | the Hub, against the run's own directory |
| Ask me | `manual` | the operator, via a card |
| Full access | `bypassPermissions` | nobody |

- **Claude** routes through `--permission-prompt-tool mcp__agentweave__approve_tool_call` (an MCP
  tool on the Hub's own server). Contract measured against Claude Code 2.1.221 — see Dead ends,
  three details are unguessable.
- **Codex** routes through `codex_appserver.decide_approval`, which now takes `posture` and
  `workspace`. `ASK_OPERATOR` is a sentinel that is deliberately *not* a valid protocol reply;
  `run_turn` resolves it via a `request_approval` callback supplied by `agent_trigger.py`.
- Denials are recorded as `permission_denied` EventLog rows and appear in the agent timeline.

**2. Questions — `ask_user` blocks.** It posts a question, then polls until answered or
`QUESTION_ANSWER_TIMEOUT` (240s), and returns the answer as its own tool result. `header`,
`options` (2–8, each `{label, description}`) and `multi_select` are **required** — the schema
rejects a call without them.

**3. The panel.** `AgentQuestionCard` and `PermissionRequestCard` render above the composer using
`.conversation-interject` (the composer's own width/radius/border, one step lighter on
`--surface-2`). The question panel has **no input and no submit of its own** — free text goes
through the real composer, whose send button confirms the selection.

### Known-broken / not done (the operator's own list, in their words)

1. **Codex often does not call `ask_user` at all.** Measured: told *"Ask me which package manager
   to use"*, Claude called the tool; Codex wrote the question as plain text and ended the turn, so
   no question row existed and the operator would never see it. Told explicitly to use the tool,
   Codex did it perfectly with full structure. So it is disposition, not capability.
2. **One question at a time.** No batching. The `1/2` counter in the panel counts *outstanding
   questions*, not T3's step-through of one multi-question prompt.
3. **Timeouts are hardcoded** — 120s permissions, 240s questions.
4. **Codex's boundary check is coarser.** Its file-change approvals carry no per-file path; live it
   sends `{"grantRoot": null, "reason": null}`.
5. **Boundary, not sandbox** — a shell command can build a path at runtime. Operator: *"let's skip
   this one for now."*
6. **Nothing has been seen in a browser.** Four surfaces (Permissions pill, approval card, question
   card, the restyle) verified only through the API and jsdom.

## Files touched

Full list: `git diff --name-only d116929..HEAD` (65 paths incl. `hub/hub/static/ui`).

**Hub backend**
- `hub/hub/mcp_server.py` — `approve_tool_call` (no return annotation, deliberately), `_decide`,
  `_ask_operator`, `_report_decision`, `ask_user` rewritten to block and require structure;
  constants `OPERATOR_POSTURE`, `OPERATOR_DECISION_TIMEOUT=120`, `OPERATOR_POLL_SECONDS=2`,
  `QUESTION_ANSWER_TIMEOUT=240`, `QUESTION_POLL_SECONDS=2`. Complete.
- `hub/hub/codex_appserver.py` — `approval_subject`, `_within`, `_thread_policy`, `ASK_OPERATOR`;
  `decide_approval` takes `posture`/`workspace`; `run_turn` takes `posture`/`workspace`/
  `request_approval`. Complete.
- `hub/hub/runner_commands.py` — `CLAUDE_PERMISSION_PROMPT_TOOL`, `APPROVER_PERMISSION_MODES`,
  `OPERATOR_POSTURE`; `_build_claude_command` takes `control_overrides`. Complete.
- `hub/hub/model_catalog.py` — `ApplySpec` moved above `ControlValue`; `ControlValue.apply`
  per-value override; `WORKSPACE_PERMISSION_MODE`; `permission_mode` control on **both** claude and
  codex (codex renders `style="none"`). Complete.
- `hub/hub/api/v1/agent_trigger.py` — `AW_WORKSPACE_DIR` and `AW_PERMISSION_POSTURE` in spawn env;
  `_codex_posture`, `_await_operator_permission`, `CODEX_OPERATOR_DECISION_TIMEOUT=120`;
  `permission_mode` threaded through `_execute_run` → `_execute_codex_appserver_run`. Complete.
- `hub/hub/api/v1/permissions.py` — **new**. Operator-facing list + `/decide`. Complete.
- `hub/hub/api/v1/agent_actions.py` — `/permission-decisions`, `/permission-requests` (open + poll),
  `AgentQuestionCreate` now requires the structure. Complete.
- `hub/hub/api/v1/questions.py` — stores `options`/`header`/`multi_select`/`answer_labels`; a
  **blocking** question no longer also enqueues a delivery. Complete.
- `hub/hub/api/v1/agents.py` — `_tool_surface_lines()` describes `ask_user`'s real signature;
  approver excluded from the tool list. Complete.
- `hub/hub/api/v1/projects.py` — `_project_summary` gained the `agents_with_active_run` override
  (the rail-dot fix). Complete.
- `hub/hub/db/models.py` — `PermissionRequest`; `Question.options/header/multi_select/answer_labels`.
- `hub/hub/schemas/questions.py` — `QuestionOption`; required fields; `QuestionAnswer.labels`.
- `hub/hub/api/v1/__init__.py` — registers `permissions_router`.
- Migrations `0029_add_permission_requests.py`, `0030_add_question_options.py`,
  `0031_question_option_descriptions.py`. **Head is 0031.**

**Hub UI**
- `hub/ui/src/components/agents/AgentQuestionCard.tsx` — rewritten to T3's pattern. Complete.
- `hub/ui/src/components/agents/PermissionRequestCard.tsx` — restyled; `describe()` falls back
  path → command → grantRoot → cwd → reason. Complete.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — owns `questionSelection`/`composerDraft`,
  `answerPendingQuestion`, `handleQuestionToggle`; a pending question owns the composer. Complete.
- `hub/ui/src/components/agents/Composer.tsx` — new optional props `canSubmitEmpty`,
  `onTextChange`, `placeholder`. Complete.
- `hub/ui/src/api/permissions.ts` — **new**. `hub/ui/src/api/questions.ts` — `QuestionOption`,
  `labels` on the answer mutation, `refetchInterval: 3000`.
- `hub/ui/src/api/agents.ts` — `permission_denied` in `eventBelongsToTimeline`.
- `hub/ui/src/hooks/useSSE.ts` — `permission_denied`, `permission_requested`, `permission_decided`.
- `hub/ui/src/index.css` — `.conversation-interject`, `.interject-eyebrow`, `.interject-choice`
  (+ `-body/-label/-desc`), `.interject-kbd`, `.interject-count`. `.interject-input` was added then
  removed when the panel lost its input.
- `hub/hub/static/ui/**` — committed build artefact, rebuilt several times. **Currently in sync.**

**Tests** — new: `hub/tests/test_permission_approver.py`, `hub/tests/test_blocking_questions.py`,
`hub/ui/src/__tests__/agentQuestionCard.test.tsx`, `permissionRequestCard.test.tsx`. Modified:
`test_questions.py`, `test_mcp_server.py`, `test_agent_actions_coordination.py`, `test_bola.py`,
`test_agent_tool_surface_phase7.py`, `test_agent_facing_text.py`, `test_agent_trigger.py`,
`test_migrations.py`, `test_project_persistence.py`, `test_operator_projects_api.py`, and three
frontend suites that render `AgentOutputPanel` (`conversationControls`, `agentRunningComposer`,
`agentHandoff`) which needed `@/api/permissions` and `@/api/questions` mocks.

**Pre-existing dirty, untouched this session:** `M .claude/handoffs/handoff-0001-...md`,
`M Makefile`, and the untracked paths in Git state.

## Key decisions

1. **The permission decision is made in-process, reported to the Hub best-effort.** Rejected:
   routing every decision through a Hub endpoint. `decide_approval` already records that an
   unanswered request suspends a turn forever, and a round-trip is a decision path that can time
   out. Reporting happens *after* the answer and swallows every failure.
2. **`ask_user`'s structure is required, not taught.** This is the session's most important
   decision and came directly from the operator: *"we have to teach which is underministic. Like,
   the agent can just forget to use the options."* Rejected: better prose. Mirrors Claude Code's own
   `AskUserQuestion`, where header/options/multiSelect are all mandatory and free text is the UI's
   escape rather than a missing-options case. **Minimum 2 options** — one option is a confirmation
   dialog wearing a choice's clothes.
3. **The question panel has no input and no submit.** Free text goes through the real composer; its
   send button confirms the selection. This is *why* the earlier version felt wrong — no restyle
   would have fixed a second input box inside the card.
4. **A pending question owns the composer.** Otherwise the operator's reply becomes a new message
   and the agent keeps waiting for one that never comes.
5. **Codex's posture reaches it via the app-server protocol, not argv** — its catalog control
   renders `style="none"` and is read at trigger time.
6. **Codex "Ask me" starts `read-only` + `untrusted`.** Rejected: leaving the non-yolo pairing.
   `workspace-write` + `on-request` by design does not ask about in-workspace writes, which is why
   the first live Codex test silently did the work without prompting.
7. **`OPERATOR_POSTURE` is restated in `mcp_server.py`, not imported** from `runner_commands` —
   that module is spawned standalone and imports only stdlib + fastmcp. A test asserts they agree.
8. **Migration 0031 converts 0030's bare-string options in place** rather than teaching the reader
   both shapes — a tolerant reader never stops being tolerant.
9. **Answering a *blocking* question no longer enqueues a delivery.** Measured live: the agent
   answered, then woke again and restated the same directive as a whole extra turn.
10. **Timeouts are set to what was measured, not what was wanted.** 240s for questions because an
    ordinary MCP tool call was measured tolerating exactly that; 120s for permissions, inside the
    150s measured for the permission-prompt tool.

## Constraints and user directives (verbatim)

- *"Codex doesn't have this permission thing? It would be nice to control codex permissions as
  well. Also there are questions that claude and codex as the users and a prompt pops up. Can we
  implement that as well?"*
- *"I tried ask first but it did not pop up in the hub the approval. Is that not possible yet? The
  other permissions worked but I think the ask first should return the prompt in the hub. t3 code
  does that"*
- *"Now agentweave behaves like t3?"* … *"The re style and everything else seems to work. But it
  feels poor and malfunctioning. Also we have to teach which is underministic. Like, the agent can
  just forget to use the options to send multiple answers. And the T3 panel is richer"*
- On the cards' look, earlier: *"I don't want it to be colorful it should be like the chat box but
  maybe a little lighter with highlight on the cards just like T3. It should feel as a extension of
  the chat box"*
- Final follow-up choices, verbatim: *"Ok, fix #1. #2: Yes. #3: Make it configurable. Should we have
  a config screen for agents for things like this and future things? Having a gear somewhere in the
  screen, the chat box or chat screen? #4: explore. #5: okay, let's skip this one for now. #6:
  okay."*
- **AskUserQuestion decisions this session:** decision site = *"In-process, report to Hub"*; posture
  = *"New fourth posture, not yet default"*; "Ask first" = *"Fix 'Ask first' in place"*; unanswered
  = *"Deny after a timeout"*; Codex scope = *"Both postures, honest asymmetry"*; questions =
  *"Block by default, card in the conversation"*; option shape = *"Full parity: descriptions,
  header, multiSelect"*; determinism = *"Make options/header/multi_select required"*; panel =
  *"Full T3 pattern, composer-integrated"*.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml`, or `spec/` at the repo root;
  stage paths explicitly, never `git add -A`; openspec not aw-spec skills; `Icon` is the only icon
  system; never mark a task complete on the strength of a plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All 12 commits were unprompted.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at
  session start (841/465/372 all matched handoff-0012). **Repeat this next session.**

## Dead ends

- **The `--permission-prompt-tool` contract has three unguessable details**, each failing as what
  looks like a Hub bug: (a) Claude passes `tool_use_id`, and a signature omitting it fails *every*
  call with a Pydantic error; (b) the answer must be a JSON **string** in a text block;
  (c) **`structuredContent` must be absent** — FastMCP derives it from the return annotation, and
  with it present a correct `allow` is silently not honoured, indistinguishable from a deny.
  `approve_tool_call` therefore has **no return annotation**. Do not add one.
- **First Codex "Ask me" test silently did the work without asking.** `decide_approval` only ever
  sees requests the *thread policy* caused. Fixed by `_thread_policy`.
- **`test_ui_staleness.py` does not check this repo's artefact** — it exercises the mechanism in
  throwaway repos. `hub/hub/static/ui` was found stale despite it passing. Always `diff -rq
  hub/ui/dist hub/hub/static/ui` after `npm run build`.
- **Background-shell Hub dies between turns.** Started via the Bash tool's `run_in_background`, the
  uvicorn process is reaped when the task ends (log stops mid-startup, no error). Start it detached
  with PowerShell `Start-Process` instead — see Live environment.
- **Bash `/tmp` and Windows Python do not share a filesystem view.** A file written to `/tmp` by
  bash is invisible to `C:\...\python.exe`. Use a repo-relative path (`testbed/`) for anything both
  touch.
- **`cd hub/ui && npm run build` then `cp` with repo-relative paths fails** — the Bash tool's cwd
  persists, so the second command resolves against `hub/ui`. Run the `cp` from the repo root.
- **Editing Python with `python - <<'PY'` and `\n` inside a replacement string** injected a literal
  newline into a string literal and broke `approver.py` silently — the MCP server then failed to
  start and Claude reported "Available MCP tools: none".
- **I initially concluded SSE events carry no `project_id`** and nearly reported a false root cause.
  The per-project stream correctly does not stamp; the **operator** stream (`/api/v1/events`, what
  the UI uses) does.
- **I claimed T3's question mechanism is Claude-only.** Wrong — `t3src/src/session-logic.ts` handles
  `"unknown pending codex user input request"`; T3 has a provider-driver layer with a Codex path.

## Verification

**Ran, with real output, final state:**
- `pytest hub/tests/ -q` — **910 passed, 10 skipped** (841 at session start).
- `pytest tests/ -q` (CLI) — **372 passed, 3 skipped**.
- `cd hub/ui && npx vitest run` — **491 passed** (465 at start). `npx tsc --noEmit` — clean.
- `ruff check` on every touched file — clean. Pre-existing and untouched: two `SIM105` in
  `codex_appserver.py`, one `I001` in `api/v1/jobs.py`, plus others across `hub/tests/`.
- `npx openspec validate --specs --strict` — **24 passed, 0 failed**.
- `npm run build` + artefact synced; `diff -rq hub/ui/dist hub/hub/static/ui` identical.
- **Live**, Hub on `127.0.0.1:8010`, project `proj-84d218db`:
  - Workspace-only: write inside worktree succeeded; write to an absolute path outside produced no
    file and a `permission_denied` timeline entry naming the exact path; `send_message` still worked.
  - Ask-me (Claude): prompt appeared in 4s, Allow produced the file, Deny produced no file.
  - Ask-me (Codex): prompt appeared (`tool_name: "a file change"`, `grantRoot: null`), Allow
    produced the file; no prompt for the same work under the default posture.
  - Blocking question: appeared in 4s; agent output read *"Great! I got the answer. The operator
    responded: 'Use the staging Postgres, never production.'"*
  - Multi-select: header + 3 described options round-tripped; answering Postgres+Redis produced
    *"The operator selected: **Postgres** and **Redis**."*
  - Determinism: a deliberately vague *"Ask me which test framework to use"* produced header
    `'Test Framework'`, five described options, `multi_select: False`.
  - Enforcement: POST with no options/header → **422**; one option → **422**; full structure → **201**.
  - `--permission-prompt-tool` waits ≥150s; an ordinary MCP tool call waits ≥240s (both are the
    spike's own limits, not Claude's ceiling).

**Explicitly NOT run/tested — do not assume:**
- **No part of this UI has ever been rendered in a browser.** Not the Permissions pill, the approval
  card, the question card, the restyle, the kbd badges, the selected state, or the composer
  takeover. Every claim about them is from the API plus jsdom.
- Task 6.11 of the approver change (live failure of the reporting endpoint) — still open, with a
  written reason, in that change's `tasks.md`.
- Light mode not re-checked for any new CSS.
- `bypassPermissions` never exercised live.
- Codex `multi_select` never exercised — Codex only ever produced `multi_select: False`.
- The `1/2` counter has never been seen with two genuinely concurrent questions.
- No charter has been bound to an agent and run (carried unresolved from handoff-0012).

## Git state

Branch `hub-native-experience`, HEAD `96884f4`, **no upstream — nothing has ever been pushed on
this branch** (carried from every prior handoff).

12 commits this session, oldest→newest: `3609eef`, `ad86457`, `5d6c9f3`, `795f519`, `8610a10`,
`034524c`, `19c358d`, `a5ca7f4`, `223f439`, `f535da6`, `8b76b1a`, `96884f4`. (`d116929` was
handoff-0012's final HEAD.) 65 files, +4257/−564.

Uncommitted, all pre-existing, none from this session: `M .claude/handoffs/handoff-0001-...md`,
`M Makefile`. Untracked: `.claude/handoffs/*` (this chain), `.claude/skills/{handoff,resume,
review-iteration}/`, `openspec/explorations/2026-08-03-specification-authority-technical.md`,
`scripts/`, `src/agentweave/templates/skills/{handoff,resume}.md`,
`tests/test_handoff_resume_templates.py`.

**openspec:** `2026-08-07-hub-answered-permission-approver` is implemented, live-verified, and
**still in flight** (not archived). `2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`
was archived this session. Six commits (`034524c`, `19c358d`, `a5ca7f4`, `223f439`, `f535da6`,
`8b76b1a`) shipped with **no openspec change at all** — see Next step 6.

## Next steps

1. **Backstop for a question an agent never asked** (operator: *"Ok, fix #1"*). Codex frequently
   writes a question as prose and ends the turn; nothing reaches the operator. A tool call cannot be
   forced, so detect it instead: at run completion in
   `hub/hub/api/v1/agent_trigger.py`, if the run's final assistant text ends in a question and the
   run opened no `Question` row, emit a new event (suggest `question_not_asked`) carrying the
   agent, run_id and the offending text, surface it in the conversation the way `permission_denied`
   already is, and offer a one-click "ask this properly" that re-prompts the agent. Start by reading
   how `permission_denied` is persisted and broadcast (`hub/hub/api/v1/agent_actions.py`
   `record_permission_decision`) and mirror it.
2. **Batched questions** (operator: *"#2: Yes"*). Let one `ask_user` call carry several questions
   and step through them, as T3 does — `t3src/src/pendingUserInput.ts` has the reference model
   (`questionIndex`, `activeQuestion`, `isLastQuestion`, `canAdvance`, `answeredQuestionCount`).
   Needs a tool-contract change (a list of questions), a way to hold partial answers, and the
   panel's `1/N` to become a real step counter rather than a count of outstanding questions.
3. **Make the timeouts configurable, and decide where agent settings live** (operator: *"#3: Make it
   configurable. Should we have a config screen for agents for things like this and future things?
   Having a gear somewhere in the screen, the chat box or chat screen?"*). Two parts: (a) move
   `OPERATOR_DECISION_TIMEOUT`, `QUESTION_ANSWER_TIMEOUT` and `CODEX_OPERATOR_DECISION_TIMEOUT` out
   of module constants into per-project or per-agent settings; (b) **this is an open design
   question — see Open questions 1.**
4. **Explore recovering Codex's per-file paths** (operator: *"#4: explore"*). Its file-change
   approval carries only `grantRoot`, live `null`. Codex streams thread items *before* the approval
   request; investigate whether `map_item_to_events` in `hub/hub/codex_appserver.py` already sees
   the file list and can be correlated by `itemId`/`turnId`. Exploration first — do not build until
   it is known to be recoverable.
5. **Look at all of it in a browser** (operator: *"#6: okay"*). Four unverified surfaces, listed in
   Verification. `mcp__t3-code__preview_*` tools were available in the last session and could drive
   this. Start the Hub (see Live environment), open
   `http://127.0.0.1:8010/?project=proj-84d218db&agent=haiku-1`, trigger a question, and actually
   look at the panel, the kbd badges, the selected state, and the composer takeover.
6. **Reconcile openspec.** Six commits shipped with no change document, and
   `2026-08-07-hub-answered-permission-approver` is still unarchived while its scope has grown well
   past what it proposed. Decide whether to widen that change or write a second one, then sync and
   archive. Note `2026-08-06-operator-in-the-loop-turns` (deferred) describes a gap this session has
   largely closed and should be updated or retired.

**Explicitly dropped by the operator:** real sandboxing to close the runtime-path-construction hole
(*"#5: okay, let's skip this one for now"*).

## Open questions for the user

1. **Where do agent settings live?** The operator asked, unanswered: *"Should we have a config
   screen for agents for things like this and future things? Having a gear somewhere in the screen,
   the chat box or chat screen?"* Next step 3 needs this decided. Today the composer carries only
   per-conversation pills (Model, Effort, Permissions) and there is no per-agent settings surface at
   all.
2. Should `hub-native-experience` be pushed? Still no upstream, now 12 commits further ahead
   (unresolved since handoff-0012).
3. `M .claude/handoffs/handoff-0001-...md` and `M Makefile` — intentional WIP, or commit/revert?
   Carried unresolved since handoff-0001.
4. Should the Hub gain project/agent deletion? (carried from handoff-0012)
5. `npm run lint` in `hub/ui` does not start (ESLint 9, no flat config). Pre-existing.
6. Should the database backup at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept?

## Live environment

- **Hub on `127.0.0.1:8010`** — running HEAD `96884f4`. **Start it detached**, or it dies when the
  agent's background task ends:
  ```powershell
  Start-Process -FilePath "C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe" `
    -ArgumentList "-m","uvicorn","hub.main:app","--host","127.0.0.1","--port","8010" `
    -WorkingDirectory "C:\Users\huida\Documents\projects\AgentWeave\hub" `
    -RedirectStandardOutput "C:\Users\huida\Documents\projects\AgentWeave\testbed\hub-8010.log" `
    -RedirectStandardError "C:\Users\huida\Documents\projects\AgentWeave\testbed\hub-8010.log.err" `
    -WindowStyle Hidden
  ```
  Stop it by filtering `Get-CimInstance Win32_Process` on `*uvicorn*8010*`.
- **API key** `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (from `hub/.env`), sent as
  `Authorization: Bearer …` — **not** `X-API-Key`, which 401s.
- **Project `proj-84d218db` ("Testbed")** at `C:\Users\huida\Documents\agentweave-testbed`, its own
  git repo outside this checkout. Agents `haiku-1`, `haiku-2`, `haiku-3`, `codex-1`, `codex-2`, and
  `file_edit` (operator-created).
- **Python:** `C:/Users/huida/AppData/Local/Programs/Python/Python311/python.exe` is the only
  interpreter with pytest/fastapi/sqlalchemy.
- **Spikes** in `testbed/ppt-spike/` (`approver.py`, `slowtool.py`, `probe.py`) and the Codex
  protocol schema in `testbed/codex-schema/`. `testbed/.gitignore` is `*`, so none of it can leak
  into the repo. Disposable.
- **T3 source** extracted at `C:\Users\huida\t3src` — the reference for the panel and the question
  contract.

## Read on resume

- `hub/hub/mcp_server.py` — `approve_tool_call` (and the comment block above it) plus `ask_user`;
  the two mechanisms this session is about, and the place the unguessable contract is recorded.
- `hub/ui/src/components/agents/AgentQuestionCard.tsx` — the panel, for Next steps 2 and 5.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — `answerPendingQuestion` /
  `handleQuestionToggle` and the composer takeover; where batching (Next step 2) lands.
- `hub/hub/codex_appserver.py` — `_thread_policy`, `decide_approval`, `approval_subject`,
  `map_item_to_events`; needed for Next step 4.
- `hub/hub/api/v1/agent_trigger.py` — run completion and `_await_operator_permission`; where Next
  step 1's detection lands.
- `C:\Users\huida\t3src\src\pendingUserInput.ts` — the reference model for batched questions.
