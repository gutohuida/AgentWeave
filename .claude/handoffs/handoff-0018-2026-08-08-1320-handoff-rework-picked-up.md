# Handoff: conversation-navigation signed off in use; handoff-rework picked up, exploration not yet started

**Date:** 2026-08-08T13:20 · **Branch:** hub-native-experience · **HEAD:** b53ebd9
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0017-2026-08-08-0235-conversation-navigation-complete.md
**Status:** chunk complete, working tree clean. Next change chosen and scoped;
**no exploration task has been run yet.**

## Goal

Two things, in order:

1. **Finish and stabilise `2026-08-07-conversation-navigation`.** Done — 81/81. The operator used
   it and reported two defects, both fixed (below). Still **not archived and specs not synced**.
2. **Start `2026-08-07-conversation-handoff-rework`** — chosen by the operator this session from
   four options. Its blocking gate cleared when the navigation change landed.

The *why* for (2), verified this session rather than taken from the proposal: **the Handoff
control does not do anything.** `HANDOFF_PROMPT` tells the agent to invoke an `aw-checkpoint`
skill and write to `.agentweave/shared/checkpoints/`.

- `get_skill_template` has exactly one caller in the repository outside its own definition, and
  it is `tests/test_handoff_resume_templates.py`. No code path installs any skill into any
  project.
- The string `checkpoints` does not appear anywhere in `src/` or `hub/hub/`.
- `RESUME_HANDOFF_PREFIX` tells the successor to read `.agentweave/shared/context.md`, which
  nothing writes.
- "Handoff ready" is set when the run merely stops. No artifact is ever checked for.

Last session I moved that control from a buried overflow-menu item to a labelled button visible
at rest on the conversation header. It is now **more prominent and more misleading than before**.

## Current state

### The Hub

Running on **http://localhost:8010**, started detached (PowerShell `Start-Process`, working
directory `hub/`). Reads `hub/.env`'s `DATABASE_URL=sqlite+aiosqlite:///data/agentweave.db` → the
real `hub/data/agentweave.db`, alembic head `0037`. Restarted this session so the messaging fix
below is live. `hub/hub/static/ui` is read from disk per request, so replacing the bundle needs no
restart — but a **Python change does**.

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

Live project **`proj-84d218db` ("Testbed")**. API key `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`
(in `hub/.env`). Agent → runner bindings, confirmed this session:

| agent | runner | cli | model |
|---|---|---|---|
| `haiku-1`, `haiku-2`, `haiku-3`, `file_edit` | `runner-f1140195` | claude | `claude-haiku-4-5-20251001` |
| `codex-1`, `codex-2` | `runner-a2dfcf5d` | codex | `gpt-5.4-mini` |

Unbound spares: `runner-d554f423` (claude, no model), `runner-a6ddebf3` (codex, no model).
Both `claude` and `codex` are on PATH and answer a one-shot prompt in 5–8s.

### Three commits this session

1. `5a4db3c` — the new-conversation surface's headline. Bound: *"What should `codex-1` work
   on?"*; unbound: *"Who should work on this?"*. 28px semibold, centred. Task 7.8.
2. `a29488f` — **operator-reported defect.** The agent chips on that surface were rendered,
   clickable, and inert when an agent arrived pre-bound (`agent = boundAgent ?? chosen` ignored
   the click). Pre-selection is now a default: choosing another agent retargets the unsent
   message, the headline follows, and typed text survives. The chosen agent moved into the
   destination. Task 7.5a.
3. `b53ebd9` — **operator-reported defect, and a serious one.** See below.

### Agent-to-agent messaging was completely down, and is fixed

`conversation_id` was added to the MCP `send_message` tool and to `MessageCreate` — the schema on
the **operator** route `/api/v1/projects/{id}/messages` — but **not** to `AgentMessageCreate`, the
schema on `/api/v1/agent-actions/messages`, which is where `mcp_server.send_message` actually
posts. The tool puts `conversation_id` in every body it builds, `null` included, and that schema
sets `extra: "forbid"`, which rejects a forbidden **key** regardless of its value.

So **every** peer message failed `422: conversation_id: Extra inputs are not permitted` — not only
the ones naming a conversation. Down from `37983d3` (2026-08-07) until `b53ebd9` today.

Fixed by adding the field and passing it through `send_peer_message`. Verified live against
:8010 with a minted run credential, sending the exact body the tool builds: `201`.

**Why the suite missed it, which matters more than the fix:** both sides were tested, the join
was not. `test_mcp_server.py` mocks `urlopen` and asserts the body the tool *builds* — it
explicitly asserts `"conversation_id": None` is present, so it encoded the broken behaviour as
correct. `test_archived_send_refusal.py` stubs `_hub_request` and manufactures its error from the
**operator** route while its docstring claimed it "reaches the same route". That docstring is
corrected in `b53ebd9`.

New: `hub/tests/test_mcp_body_contract.py` reads each route's real request model off the FastAPI
app (via `route.path_regex` so `/tasks/task-1` resolves against `/tasks/{task_id}`) and feeds it
the real body each MCP tool produces. It carries `test_the_helper_would_actually_fail_on_drift`,
and I confirmed by temporarily removing the field again that it turns red with the exact 422.
Also new: `hub/tests/test_agent_message_routing.py`, 6 tests over the agent route.

### Where the handoff-rework stands — nothing started

`openspec/changes/2026-08-07-conversation-handoff-rework` is **0/24**. I read it and stopped.

**Gate 1** ("`2026-08-07-conversation-navigation` must be implemented first") is **cleared**.
**Gate 2** — section 1, the exploration — is the work, and none of it has been run.

**I found an ordering conflict in the change's own task list, and it is not recorded there yet.**
Section 0 is marked "not gated — do these independently", and 0.1 replaces `HANDOFF_PROMPT`. But
task 1.1 asks *"what does the agent actually do when told to invoke a skill it does not have?"*
Doing 0.1 first destroys the condition 1.1 exists to observe. **Run 1.1–1.3 before section 0.**

I had written a probe (`hub/observe_handoff.py`) to run 1.1 and **deleted it before handing off**,
because it hardcoded the API key and would have been committed. What it did, worth rebuilding:

- extracted `HANDOFF_PROMPT` from `AgentOutputPanel.tsx` with
  `re.search(r"const HANDOFF_PROMPT = `(.*?)`", source, re.DOTALL)` — observe the *shipped*
  string, never a retyped approximation;
- `POST /api/v1/projects/proj-84d218db/agent/trigger` with `{agent, message, conversation_id}`;
- polled `GET /api/v1/projects/{p}/agents` every 5s until that agent's `status` left `running`;
- dumped `GET /api/v1/projects/{p}/agent/{agent}/chat/{conversation_id}`, printing each entry's
  `kind` (and `output_kind` for `agent_output`).

It was **never run** — the operator stopped it to take a handoff. No live handoff observation
exists yet.

Candidate conversations with real history, confirmed present today:
`conv-e41cc24e` (haiku-1, *"Count slowly from 1 to 30…"*), `conv-e7ceb4fc` (haiku-1),
`conv-ee0b0582` (codex-1), `conv-fd217ed1` (codex-1).

## Files touched

`git status --short` is **empty** — working tree clean.

### This session's changes, all committed

- `hub/ui/src/components/agents/NewConversationSurface.tsx` — added the `h1` headline
  (`data-testid="new-conversation-headline"`), centred the agent chips, dropped the small
  "Choose an agent" label the headline replaced; then removed local `chosen` state entirely and
  added the `onChooseAgent` prop.
- `hub/ui/src/App.tsx` — passes `onChooseAgent`, navigating `newConversationDestination` with
  `{ replace: true }`.
- `hub/ui/src/__tests__/newConversationSurface.test.tsx` — local `Controlled` harness playing
  App's half; 8 tests including "treats a pre-selected agent as a default, not a lock" and
  "keeps the typed message when the agent is changed".
- `hub/hub/api/v1/agent_actions.py` — `AgentMessageCreate.conversation_id`, and
  `send_peer_message` passes it to `MessageCreate`.
- `hub/tests/test_mcp_body_contract.py` — **new**, 7 tests.
- `hub/tests/test_agent_message_routing.py` — **new**, 6 tests.
- `hub/tests/test_archived_send_refusal.py` — corrected the false docstring only.
- `hub/hub/static/ui/**` — rebuilt twice; current served bundle `assets/index-D0RqKR3V.js`.
- `openspec/changes/2026-08-07-conversation-navigation/tasks.md` — 7.5a, 7.8, and a long note
  under 2.10 recording that it shipped broken and was marked complete anyway.
- `openspec/changes/2026-08-07-conversation-navigation/specs/agent-conversation-workspace/spec.md`
  — the pre-selection-is-not-a-binding wording, plus scenarios for the headline and the change of
  mind.
- `.claude/handoffs/handoff-0017-*.md` — reconciled counts after the headline landed.

## Key decisions

1. **Observe before correcting, in the handoff-rework.** Section 0's "do these independently" is
   wrong about 0.1 specifically. Not yet written into the change's `tasks.md` — do that.
2. **The new-conversation headline names the agent, not the project** (operator picked it from
   four options). The project is already in `ProjectHeader` two lines above; the roster is what
   this product has that a chat app does not. "work on", not "build", because agents also
   investigate and review. Rejected: the direct T3 port; a stable project headline with the agent
   in a subline; *"What's next for X?"*. The agent name is **not** tinted — *"I don't want it to
   be colorful"* — the chip below already carries the dot.
3. **A pre-selected agent is a default, not a lock.** The operator offered an alternative —
   hide the other agents when pre-bound — and I did not take it: it makes the surface's shape
   depend on how you arrived at it, and forbids a change of mind that costs nothing before any
   record exists. **Recorded as a decision they can overrule**, task 7.5a.
4. **Retargeting uses `replace`, not `push`.** A change of recipient for one unsent message is
   not a place to navigate back out of.
5. **The MCP fix is the field, but the durable part is the contract test.** Adding
   `conversation_id` to `AgentMessageCreate` is three lines; the reason this class of bug shipped
   is that nothing validated a tool's real body against its real route.
6. **Deleted the exploration probe rather than committing it** — it hardcoded the API key.

## Constraints and user directives (verbatim)

**From this session:**
- *"Can we just add something cleaver on the composer creation page. The T3 one has in big bold
  letters 'What should we build in [project_name]'. I want to do something similar tailored for
  Agentweave. Give me some options"*
- *"One thing that I noticed is that when I open a conversation from the agent tree is locks into
  that agent. I like the way that it pre select but it shouldn't lock. If I change the
  conversation should be directed elsewhere. Or we should remove the other agents from the screen
  so it's not confusing"*
- *"So we need the conversation id to send a message. But not always the agent will have it so we
  need a way to send to the newest conversation if the agent doesn't have the id"* — the premise
  was slightly off and worth remembering: omitting the id **always** meant "newest open, opening
  one if none". That path was simply unreachable. It works now.
- *"okay, then I'll come back to this mechanic later"* — said about **hop budget**, after I
  explained it. Not a work item; do not start it.
- *"LEt's do a handoff first. Then I'll run a clear and we go form there"*

**Carried and still binding:**
- *"no need for backups everything is test env"*
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter with
  highlight on the cards just like T3. It should feel as a extension of the chat box"*
- *"using right click is nice but no everyone will think about it. So your instinct to show three
  dots is good. I think we should go with that."*
- *"handoff need a explicit place to sit. Where we know it's there. Users might not know of
  forget about the handoff."*
- *"What is taking so long?"* / *"The test is taking very long why?"* — **the operator is
  sensitive to wall-clock time.** `pytest hub/tests/` is ~3:00 for 1073 tests; `npx vitest run`
  ~11s for 578. Targeted files during development, one full sweep before committing.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly; openspec, never aw-spec skills; `Icon` is the only icon system and its
  names are the Material-style keys in `Icon.tsx`'s map; `approve_tool_call` keeps **no return
  annotation**; `hub/hub/static/ui` is a committed build artefact refreshed after `npm run build`
  and confirmed with `diff -rq`; never mark a task complete on the strength of a plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. **Done at
  session start** — see Verification. **Repeat next session.**

## Dead ends

- **`extra: "forbid"` rejects a forbidden *key*, not a forbidden *value*.** `"conversation_id":
  null` is rejected exactly as hard as a real id. This is why one missing field took down every
  peer message rather than a subset, and it is the thing to check first the next time a tool
  reports 422.
- **A test that asserts the payload a client builds proves nothing about whether the server
  accepts it.** Both `test_mcp_server.py` and `test_archived_send_refusal.py` were green
  throughout the outage.
- **The `app` fixture in `hub/tests/conftest.py` is an httpx `AsyncClient`, not the FastAPI app.**
  It has no `.routes`. A test that needs the routing table must call `create_app()` itself.
- **FastAPI route lookup by string equality fails on templated paths.** `/tasks/task-1` only
  resolves against `/tasks/{task_id}` through `route.path_regex.match(...)`.
- **`ORDER BY EventLog.id` does not order by recency** — ids are random strings. Query by
  `event_type` or `timestamp`.
- **`DATABASE_URL="sqlite+aiosqlite:///$(pwd)/..."` from Git Bash writes to the wrong disk
  location** — `$(pwd)` gives `/c/Users/...`, a four-slash URL, which Windows resolves to
  `C:\c\Users\...`. It silently migrated a fresh database from `0001` last session while the real
  one sat untouched. Use the relative form with `WorkingDirectory` set to `hub/`, or let
  `hub/.env` supply it.
- **`Stop-Process -Id $p -Force` inside a Git Bash double-quoted string breaks** — bash eats `$p`
  and PowerShell then reads `-Force` as a command. Resolve the PID first, then issue one
  `powershell -Command`.
- Carried and still true: Radix menus opened with `{Enter}` focus the first item, opened with a
  click focus the menu content; `projectScopedApiContract.test.tsx` greps API source for the
  literal `['project', projectId` so a mutation must destructure to a bare `projectId`;
  `maybe_generate_title`/`generate_conversation_title` are keyword-only; `openspec validate`
  reads only a requirement's FIRST LINE for `SHALL`; the `openspec` CLI cannot manage a
  date-prefixed change; **the default `python` on PATH has no pytest — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`**.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0017's claims at session start** (the standing directive): the
  Hub was serving `index-CUEzDa2T.js`, the six conversation routes were live, and
  `/projects/proj-84d218db/conversations` returned 35 open with `archived_by_agent`.
- `pytest hub/tests/ -q` → **1073 passed, 10 skipped** in 3:08.
- `cd hub/ui && npx vitest run` → **578 passed, 67 files**.
- `npx tsc --noEmit` → clean.
- `ruff check hub/hub/` → **3 errors, the pre-existing baseline**.
- `npx openspec validate --changes --strict` → conversation-navigation ✓ (the two skeletons still
  fail by design).
- `npm run build`, copied over `hub/hub/static/ui`, `diff -rq` identical.
- **Live:** the exact MCP `send_message` body → `201`; an unknown conversation id → 404 naming
  the id and the agent; the contract test turns red when the field is removed again.

**Explicitly NOT run/tested — do not assume:**
- **No handoff-rework exploration task has been run.** 1.1, 1.2 and 1.3 are untouched. There is
  **no** captured transcript of what a live agent does with the current handoff prompt.
- **Nothing has been driven in a browser by me**, still. The operator has now used the app and
  found two defects; the rail, row menus and light mode remain unvalidated by my own eye.
- **Light mode: token audit only.**
- `mkdocs build` not run. `npm run lint` still does not start (ESLint 9, no flat config).

## Git state

Branch `hub-native-experience`, HEAD `b53ebd9`, **working tree clean**. **No upstream — nothing
has ever been pushed on this branch. 266 commits ahead of `master`.**

Three commits this session: `5a4db3c`, `a29488f`, `b53ebd9` (plus `a6ddf1f`, the handoff-0017
count reconciliation).

**openspec in flight (6):**

| change | tasks | note |
|---|---|---|
| `2026-08-07-conversation-navigation` | **81/81** | ready to sync + archive; operator has now used it |
| `2026-08-07-conversation-handoff-rework` | **0/24** | **chosen next.** Gate 1 cleared; gate 2 is section 1 |
| `2026-08-07-spec-execution-coordinator` | 0/29 | gated skeleton — do not start |
| `2026-08-04-hub-charcoal-visual-refresh` | 39/42 | remaining 8.8/8.9/8.10 are all manual checks |
| `2026-08-04-hub-contextual-navigation` | 43/45 | 4.7 is real code; 7.7 is a manual check |
| `2026-07-30-hub-native-experience` | 119/188 | §14 spec traceability (19), §13 charters (15), §11 composer (9), §10 multi-project (8), §9 (5), §12 (5), §15 (4), §16 closeout (4) |

## Next steps

1. **Run exploration task 1.1.** Rebuild the probe described under "Where the handoff-rework
   stands" — extract `HANDOFF_PROMPT` from `AgentOutputPanel.tsx` by regex, POST it to
   `/api/v1/projects/proj-84d218db/agent/trigger` for `haiku-1` in `conv-e41cc24e`, poll until
   the agent leaves `running`, then dump the conversation timeline. Read the API key from
   `hub/.env` rather than hardcoding it, and delete the probe before committing. Capture the
   whole transcript verbatim — 1.1 asks whether the agent improvises, refuses, or silently
   no-ops, and the answer decides how much of section 5 (the proactive offer) is worth building.
2. **Then 1.2**, the same against `codex-1` in `conv-ee0b0582`. Codex has no project-level skill
   discovery at all, so expect a different answer, not a confirming one.
3. **Then 1.3** — send a follow-up after a handoff and capture what the successor conversation
   actually receives. Today `postTrigger(message, undefined)` opens a fresh conversation, so the
   expected finding is "nothing", but confirm it rather than assume it.
4. **Write 1.1–1.3 into `openspec/explorations/2026-08-08-handoff-behaviour.md`** before starting
   1.4. The change's own rule: *"'I think' is not an answer; a file path, a captured transcript,
   or an observed run is."*
5. **Record the section-0-versus-1.1 ordering conflict in the change's `tasks.md`**, so the next
   reader does not hit it.
6. **Only then section 0**, whose shape 1.1–1.3 will inform.
7. Still open from handoff-0017: sync + archive `2026-08-07-conversation-navigation`; the
   operator's visual pass on light mode and the `⋯` visibility.

## Open questions for the user

1. **Should the `⋯` row menus be visible at rest, or is hover/focus-reveal right?** Carried
   unanswered. One line: drop `opacity: 0` from `.row-action` in `hub/ui/src/index.css:381`.
2. **Should `2026-08-07-conversation-navigation` be synced and archived now?** They have used it
   and reported two defects, both fixed. Light mode is still unchecked by eye.
3. **Was hiding the other agents the better call on the new-conversation surface?** I chose the
   live-roster reading and recorded why (task 7.5a); it is theirs to overrule.
4. Carried: is the 120-character title cap too long? Should `origin: peer` be distinct in the
   tree or only in the header? Should `AgentCard.tsx` be deleted now that it is unreachable?
   Should `pytest-xdist` be added? Should this branch be pushed — **266** commits, no upstream?
   Should the Hub gain project/agent deletion? Should the backup at
   `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept? Should `.claude/handoffs/` stay
   tracked (103 files)?

## Read on resume

- `openspec/changes/2026-08-07-conversation-handoff-rework/tasks.md` — section 0 and section 1.
  **Start here.** Note the ordering conflict recorded above before touching section 0.
- `openspec/changes/2026-08-07-conversation-handoff-rework/proposal.md` — the two gates and the
  traced evidence of what is broken. Its "Prior exploration" section points onward.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` lines **37–49** — `HANDOFF_PROMPT` and
  `RESUME_HANDOFF_PREFIX`, the two constants under observation and the subject of tasks 0.1/0.2.
- `src/agentweave/templates/skills/handoff.md` — 106 lines, the subject of task 1.4: which of its
  sections apply to an AgentWeave conversation rather than a terminal coding session.
- `hub/tests/test_mcp_body_contract.py` — the pattern for testing a client body against its real
  route; reuse it rather than reinventing it if the rework adds tool surface.
- `openspec/changes/2026-08-07-conversation-navigation/tasks.md` — the note under 2.10, for how a
  task came to be ticked while the thing it described was broken.
