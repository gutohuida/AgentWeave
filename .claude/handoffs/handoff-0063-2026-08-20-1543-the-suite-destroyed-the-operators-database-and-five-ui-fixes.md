# Handoff: the test suite destroyed the operator's database, and five UI fixes from the first live session

**Date:** 2026-08-20T15:43:27+01:00 · **Branch:** `loop/2026-08-20-spec-corpus-migration` · **HEAD:** `524ccc2`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0062-2026-08-20-1117-the-corpus-moved-into-agentweave.md`
**Status:** chunk complete. 7 commits, working tree clean, nothing pushed, no PR.

## Goal

The operator used AgentWeave for real for the first time and came back with **twelve numbered
issues**, ending with a hard blocker: *"Closing the agentweave app blocks me from oppening again.
When I tried to open it again it was asking for API key, project id to connect. I can't use it
anymore once I closed it."*

They then asked to reset the trial and remove two things, and finally to work through the fixes
(not the features). The *why* that governs judgement calls: this is the dogfooding migration
CLAUDE.md describes, so friction found while using the product is a **deliverable**.

**The operator's original twelve, numbered as they wrote them** — this list is the backlog:

1. Composer does not show the reasoning chain. T3 shows the whole chain then collapses to one
   message; AgentWeave stays on "working" until that final collapse. Wants the chain visible, and
   better still an expandable "rationalization" block like the work one. **NOT DONE.**
2. Composer textarea grows for a long prompt and stays that size after sending. **FIXED.**
3. Dark/light mode not saved; always reopens in light. **NOT DONE — see Dead ends.**
4. Scroll bounces: after sending, scrolling to the bottom jumps up a little. **FIXED.**
5. The spec main page is weak; wants an overview of the project, navigation, features, with detail
   in the other folders. **NOT DONE (feature).**
6. Leaving a conversation resets the working timer to 0. **FIXED.**
7. Leaving a conversation detaches the open spec. **PARTIALLY FIXED — see Key decisions 7.**
8. Stop a turn, send a new message, and the working indicator never shows. **FIXED.**
9. Agents should be able to create a new spec/explore page from an endpoint. **NOT DONE (feature).**
10. An agent should be able to send a message to itself in another conversation. **NOT DONE
    (feature).**
11. The spec should have a field for which agent will implement it, so approval auto-assigns.
    **NOT DONE (feature).**
12. Cannot reopen the app; asks for API key and project id. **ROOT-CAUSED AND FIXED.**

## Current state

### The blocker (item 12) was not a config problem — the database had been destroyed

`C:\Users\huida\.agentweave\hub\data\agentweave.db` was found with **every application table
emptied**: zero projects, agents, conversations, credentials. Only `alembic_version` and
`apscheduler_jobs` survived — exactly the two tables *not* registered on `Base.metadata`.

The chain, every link verified:

1. `hub/tests/conftest.py:10` **as of `1933886`** read
   `os.environ.setdefault("DATABASE_URL", "…:memory:")`. `setdefault` yields to an inherited value.
2. The `app` fixture (`conftest.py:30` at that revision) ran `Base.metadata.drop_all` on whatever
   that resolved to, once per test.
3. `src/agentweave/cli.py`'s `_hub_native_start` sets `os.environ["DATABASE_URL"]` in the Hub
   process (line ~981).
4. `hub/hub/api/v1/agent_trigger.py:540` builds a spawned run's env as `dict(os.environ)`. It
   popped `HUB_API_KEY`/`HUB_PROJECT_ID` but **not `DATABASE_URL`** — which is now popped at
   `agent_trigger.py:592`.
5. `CLAUDE.md` tells agents to run `pytest hub/tests/ -v`, and the operator's agents have
   worktrees at `.agentweave/worktrees/{Architect,Developer,Tester,teste}/`.

So an agent AgentWeave spawned, running this repo's own documented test command, dropped the
operator's live database — and pytest exited **green**.

**Reproduced deliberately** on a throwaway DB with a canary row: `DATABASE_URL=…/victim.db pytest
hub/tests/test_spec.py` → `19 passed`, canary gone, `projects` recreated with the Hub's 25-column
schema plus a `proj-test` row. After the fix: `19 passed`, one loud warning, canary intact.

The 21-of-43-tables-present state is the signature of a `drop_all` whose `create_all` was
interrupted partway (creation runs in dependency order; `projects`/`agents`/`conversations` exist,
`runs`/`spec_requirements`/`turn_usage` do not).

**Recovery was attempted and then discarded at the operator's instruction.** SQLite does not zero
freed pages, so ~823 distinct rows were carved back (11 conversations with the operator's own
prompts, 198 of 442 spec requirements, 203 revisions, 15 spec documents, 18 runs, 314 event rows,
25 charters). The operator chose *"Delete it too"*, so `testbed/db-recovery/` and the forensic
database copy were **deleted**. None of it survives.

### The reset the operator then asked for is done

- **Database wiped.** The file was deleted and the Hub restarted onto a fresh one.
- **`spec/changes/` deleted** — all three documents. Two were untracked and were committed first
  (`53e8b8f`) so the deletion is reversible via `git show`.
- **The thinking was preserved** in `openspec/explorations/2026-08-20-specs-in-flight-at-the-reset.md`
  (209 lines): the approved usage change with its 17 requirements and the live measurements behind
  them, the seeded subagent exploration with its 6 open questions, and the older quiet-hours doc.
- **Default project removed** — the mechanism, not just the value.
- **Unasked-question backstop removed** — detector, API, model, UI, table.

### Machine state, verified at 15:43

| | |
|---|---|
| Port 8000 Hub | **running**, fresh DB, `alembic 0082`, 44 tables |
| Operator credential | `aw_live_71b0560849ca74d02b882593ad4d10b1`, `/api/v1/setup/token` returns it |
| Projects on 8000 | **exactly one: `proj-adf8a200` "huida" → `C:\Users\huida`** |
| Port 8010 | running, untouched all session (standing prohibition) |
| Port 8020 | running, throwaway from handoff 0062; kill when convenient |

**The AgentWeave repo is NOT registered as a project right now.** `proj-5e960453` was re-opened
mid-session and then destroyed again by the deliberate wipe. `.agentweave/project.json` still holds
`proj-5e960453`, so re-opening the repo directory will adopt that id back.

**The operator's HOME directory is registered as a project**, from `~/.agentweave/project.json`
(`proj-adf8a200`), `last_opened_at` 13:57 — after the wipe, so something re-registered it.
Running bare `agentweave` from a home directory registers that directory. Worth deciding whether to
delete it.

### `spec/` on disk

`spec/agentweave.html` (the authored system map, the corpus `home`), `spec/capabilities/` (**34**
files), and `spec/index.json`. The index lists 33 documents and **every one still exists** — the
deleted change documents postdated it and were never in it. The two capability files it does not
list are `project-instructions` and `quiet-hours`, which read `unfiled` for the same reason as
always: no Hub can adopt a document that already exists on disk.

**The corpus has no database rows.** `spec_documents` is empty and `POST /documents` still renders a
placeholder over whatever file it is handed, so the Spec tab shows nothing. This is finding 17 from
handoff 0062, unchanged, and it is the main thing standing between the operator and a usable spec
surface.

## Files touched

All committed. `git status --short` is empty. Grouped by commit.

**`53e8b8f` — preserve before deleting**

- `spec/changes/project-usage-…/spec.html`, `spec/changes/tracking-and-showing-the-subagents-claude-spawns/spec.html` — committed solely so the next commit's deletion is recoverable.

**`5567ed7` — the wipe fix**

- `hub/tests/conftest.py` — `DATABASE_URL` **assigned** not `setdefault`; warns on an inherited
  value; new `assert_engine_is_disposable()` called at import and in the `app` fixture; exports
  `TEST_DATABASE_URL`. **Finished.**
- `hub/hub/api/v1/agent_trigger.py` — also pops `DATABASE_URL`, `AW_BOOTSTRAP_API_KEY`,
  `AW_TICKET_SECRET`. **Finished.**
- `hub/tests/test_agent_trigger.py` — the identity test now sets and asserts absence of those three.
- `hub/tests/test_suite_database_isolation.py` — **new**, 5 tests.
- `openspec/explorations/2026-08-20-dogfooding-findings.md` — **finding 18** added (67 lines).

**`14a8101` — the spec clearance**

- `spec/changes/*` — all three deleted.
- `openspec/explorations/2026-08-20-specs-in-flight-at-the-reset.md` — **new**, the memo.

**`6d856b8` — no default project**

- `hub/hub/db/engine.py` — the whole `AW_BOOTSTRAP_PROJECT_ID`-gated block removed from `init_db`.
- `hub/hub/config.py` — `aw_bootstrap_project_id`/`aw_bootstrap_project_name` deleted.
- `hub/tests/conftest.py` — new `seed_test_project()`, called between an explicit `create_all` and
  `init_db` (ordering is load-bearing: the seeders iterate projects).
- `hub/.env.example`, `src/agentweave/templates/skills/aw-setup-hub.md` — references removed.

**`40c3a97` — backstop removal**

- Deleted: `hub/hub/unasked_question.py`, `hub/hub/api/v1/unasked_questions.py`,
  `hub/tests/test_unasked_question.py`, `hub/tests/test_unasked_question_backstop.py`,
  `hub/ui/src/api/unaskedQuestions.ts`, `hub/ui/src/components/agents/UnaskedQuestionCard.tsx`,
  `hub/ui/src/__tests__/unaskedQuestionCard.test.tsx`.
- `hub/hub/api/v1/__init__.py` — router unregistered.
- `hub/hub/api/v1/agent_trigger.py` — `_flag_unasked_question` and both call sites removed.
- `hub/hub/db/models.py` — `UnaskedQuestion` removed.
- `hub/hub/conversations.py` — the attention query that made a detected question mark a
  conversation "waiting".
- `hub/hub/migrations/versions/0082_drop_unasked_questions.py` — **new**, drops the table.
- `hub/tests/test_migrations.py` — `HEAD_REVISION` → `"0082"`; `_run_alembic_with` gained a
  `revision` parameter; the 0036 test upgrades to `"0036"`; the 0081 round-trip downgrades to an
  absolute `"0080"`; the bootstrap-project test rewritten to set the retired env vars and prove
  they cannot bring a project back.
- `hub/tests/test_project_persistence.py` — head assertion → `"0082"`.
- `hub/tests/test_bola.py`, `test_conversation_attention.py`, `test_project_delete_api.py`,
  `test_question_batches.py` — references removed.
- 8 UI test files — the `vi.mock('@/api/unaskedQuestions', …)` block removed from each.
- `hub/ui/src/hooks/useSSE.ts` — two event names removed.
- `hub/ui/src/api/agents.ts`, `hub/ui/src/lib/eventSummary.ts` — `question_not_asked` cases **kept
  and marked retired** (history only; see Key decisions 5).
- `CLAUDE.md` — the backstop bullet replaced with a "there is deliberately no backstop" paragraph.

**`ceb0df4` — items 2, 6, 8**

- `hub/ui/src/components/agents/Composer.tsx` — height follows `text` in a `useLayoutEffect`;
  `onInput` handler removed. **Finished.**
- `hub/ui/src/hooks/useElapsedSeconds.ts` — takes an optional `since` timestamp, parsed through
  `hubDate`; clamps at 0; falls back to the transition. **Finished.**
- `hub/ui/src/components/agents/AgentTimeline.tsx` — passes the newest turn's first entry timestamp;
  new `anotherRunIsUnderway` memo feeding `runVisiblyActive`. **Finished.**
- `hub/ui/src/__tests__/conversationComposer.test.tsx` (+2 tests),
  `useElapsedSeconds.test.tsx` (**new**, 9 tests), `workingIndicator.test.tsx` (+3 tests, and the
  fake clock pinned to `2026-08-02T00:00:00Z`).

**`524ccc2` — items 4, 7**

- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — new `landedOnRef` and `scrollToNewestRef`;
  landing split into two layout effects, keyed by conversation identity rather than by
  `scrollToNewest`'s identity. **Finished.**
- `hub/ui/src/lib/navigation.ts` — `agentSettingsBackDestination` takes an optional `document`.
- `hub/ui/src/App.tsx` — `useRef` imported; `lastConversationDocument` ref + effect declared **above
  the bootstrap early-returns** (they are conditional, so a hook below them is a rules-of-hooks
  violation); `openDocument` falls back to the remembered value **only** on `agent-settings`.
- `hub/ui/src/__tests__/urlNavigation.test.ts` (+2 tests),
  `conversationControls.test.tsx` (+2 tests).
- `hub/ui/src/__tests__/App-mount.test.tsx` — only the `userEvent` import churn; **no net change**
  beyond what git shows (a test was added then removed; see Dead ends).

**Build artefacts** — `hub/hub/static/ui/` rebuilt twice via `npm run build` +
`py -3.11 scripts/refresh_ui_bundle.py`. Current asset `index-CC00FgkF.js`.

## Key decisions

1. **Fix the wipe hazard in two layers, not one.** *Rejected:* only changing `conftest`'s
   `setdefault`. *Reason:* the environment is one route to a live database among several (an edited
   conftest, a `.env` discovered from the cwd, a future embedder). The guard therefore lives next to
   the `drop_all` as well as next to the configuration.
2. **Strip `AW_BOOTSTRAP_API_KEY` and `AW_TICKET_SECRET` too**, though neither caused the wipe.
   *Reason:* the first **is** the instance operator credential and the second signs SSE tickets, so
   any spawned agent could read both from its own environment and act as the operator. The comment
   above the existing pops already stated the principle; the list was incomplete.
3. **Commit the two untracked change specs before deleting them.** *Rejected:* deleting straight
   away. *Reason:* deleting an untracked file destroys it, and the memo claims the full text is
   recoverable from git — which would have been false for two of the three.
4. **Remove the default-project mechanism, not just the `proj-default` default.** *Reason:* the
   behaviour already looked retired (a fresh install writes no `AW_BOOTSTRAP_PROJECT_ID`) but
   `init_db` still *read* the variable, so the operator's older `.env` handed the project back on
   every start. Their `.env.backup-2026-08-20` still shows the two lines.
5. **Keep two `question_not_asked` display cases** in `eventSummary.ts` and `agents.ts`. *Rejected:*
   removing every trace. *Reason:* `0082` drops the table but not the `event_logs` rows written
   before it; without the cases an old timeline renders its own event name twice. The feature is
   removed; the ability to read what it already recorded is not the feature. **The operator was told
   and can overrule.**
6. **Derive the working timer from the run's first entry timestamp.** *Rejected:* adding a
   `current_run_id`/`started_at` to `AgentSummary`. *Reason:* the timestamp is already in the
   timeline the pane renders, so no Hub change was needed.
7. **Scope the spec-attachment fix to the agent-settings round trip only.** *Rejected:* remembering
   the document across every non-conversation destination — my first attempt, which broke
   `App-mount.test.tsx`'s `does not resurrect a document when arriving from a project tab`, an
   existing test with the recorded rationale *"the memory is of what is on screen, not a preference
   that outlives leaving the surface."* *Reason:* settings is a detour about the conversation you
   are in, left by a Back button; a project tab is a departure. **This may be only half of what the
   operator meant — see Open questions.**
8. **Excluding `lastRunId` from `anotherRunIsUnderway`** is what keeps the 2026-08-18 lingering-tail
   fix intact: during the tail the completed run's status has not been refetched, so counting it
   would put the counter back under a finished answer.

## Constraints and user directives (verbatim)

- *"Wipe out the db and let's start again."*
- *"Can you also delete the specs that were created. Just create a file for me to remember what I
  was specing please."*
- *"agentweave always comes with default prject drop that too."*
- *"Also the security that we have where it finishes with a question it ask the user something. That
  is not needed to be honest. You can remove that as well"*
- *"take 7 and 4 let's leave all the features aside. I want to work on the fixes first."*
- Chosen via AskUserQuestion: **"Try to carve it back"**, **"Yes, restart it now"**, **"Fix the wipe
  hazard itself"**, **"Only the change specs I was working on"**, **"Delete it too"**.
- Standing, from `CLAUDE.md`: **never touch the Hub on port 8010**; stage paths explicitly; keep the
  two `spec_manifest` twins in sync by hand; never mark a task complete on the strength of a plan
  existing; `hub/hub/static/ui` is committed and must be refreshed with `scripts/refresh_ui_bundle.py`.
- Standing, from memory: commit each completed checkpoint without asking first.

## Dead ends

- **Item 3 (dark mode) was investigated and NOT solved.** `configStore.ts` writes `mode` to
  localStorage and `App.tsx:114-116` reapplies it on mount; `SetupModal` seeds from the store and
  only writes on change. The source path reads correct. **Leading hypothesis, unconfirmed:** the
  operator opens `localhost:8000` sometimes and `127.0.0.1:8000` other times — separate localStorage
  origins, which would explain the theme *and* the session key. Needs the operator's browser.
- **A test that passes without the fix is worthless, and I wrote two.** The scroll test needed three
  attempts: (a) a plain `rerender` never moves `tailSpacer`, because that effect's deps are
  `[timelineEntries.length, isRunning]` — so the bug cannot manifest; (b) `timelineEntry('stream-0')`
  interpolates the id into `2026-08-06T00:00:0${id}Z`, producing `RangeError: Invalid time value`
  from date-fns — **ids must be single digits**; (c) only advancing the entry count *and* a
  prototype-patched `offsetHeight` together reproduces it.
- **An App-level test for the settings round trip was written and removed.** Inside the fully
  mounted `App`, clicking `agent-menu-proj-test-claude` did not resolve a `menuitem` named "Agent
  settings" — `rowMenus.test.tsx` gets it by rendering `Sidebar` directly with its own mocks. The
  behaviour is covered by two `navigation.ts` unit tests instead; **the App-level wiring that
  decides *when* to pass the remembered document is not directly covered.**
- **Hooks placed after the bootstrap early-returns** in `App.tsx` — caught before committing.
  `if (bootstrapState === 'pending') return …` sits around line 160; anything using `useRef`/
  `useEffect` must be above it.
- **A comment between two fallthrough `case` labels** breaks eslint's `no-fallthrough`. Use a
  trailing comment on the case line.
- **`git stash push -- <path>`** is the tool for mutation-checking a fix without disturbing the
  tests; used four times and it worked well.
- **`sed -i '226s/…/'`** silently did nothing when the line number was off by one. Use `Edit`.

## Verification

**Ran, and passed:**

- `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` → **2508 passed, 12 skipped,
  1 xpassed, 0 failures** (11m16s), after fixing the two migration tests below. An earlier run of
  the same suite reported those two as `FAILED`, and they were fixed and re-verified
  (`test_migrations.py` alone: 62 passed, 1 skipped).
- `py -3.11 -m pytest tests/ -q` (CLI) → **404 passed, 3 skipped**.
- `npx vitest run` (UI) → **1172 passed, 118 files**.
- `npx tsc --noEmit` and `npm run lint` → clean.
- `py -3.11 -m ruff check` and `black --check --target-version py311` → clean.
- **Wipe reproduced and then proven fixed** against a canary database, both directions.
- **Six mutation checks** via `git stash push -- <path>`: the 2 composer tests, the 4 timer/indicator
  tests, the 2 navigation tests and the scroll test each confirmed failing without their fix.
- **Live on the 8000 Hub:** `0082` applied, `unasked_questions` gone, `/…/unasked-questions` → 404,
  fresh DB comes up with **0 projects**, `/api/v1/setup/token` returns the credential.

**NOT tested — do not claim otherwise:**

- **Nothing was verified in a real browser this session.** Every UI fix is covered by vitest/jsdom
  only. The scroll bounce, the composer collapse, the timer and the spec attachment have **not been
  seen working by a human**.
- **The browser suite was not run** (unchanged since handoff 0061; its fixtures are also known
  decayed).
- **No screenshots.**
- **Item 7's App-level wiring is untested** (see Dead ends).
- **The `0082` downgrade path was never exercised** — `upgrade` ran live, `downgrade` did not.
- **Nothing pushed, no PR, CI has seen none of this.**

## Git state

- **Branch:** `loop/2026-08-20-spec-corpus-migration`, **17 commits ahead of `master`**, no upstream
  set, nothing pushed.
- **HEAD:** `524ccc2`. **Working tree clean** — `git status --short` is empty.
- This session added 7 commits on top of `1933886`: `53e8b8f`, `5567ed7`, `14a8101`, `6d856b8`,
  `40c3a97`, `ceb0df4`, `524ccc2`. 54 files, +1708 / −2141.
- `master` unchanged at `63ef94e`.

## Next steps

1. **Ask the operator to open the repo as a project again, or do it for them** — the Hub currently
   knows only their home directory. One call, and `.agentweave/project.json` makes it adopt the
   original id:
   ```bash
   curl -s -X POST -H "Authorization: Bearer aw_live_71b0560849ca74d02b882593ad4d10b1" \
     -H "Content-Type: application/json" -d '{"path":"C:/Users/huida/Documents/projects/AgentWeave"}' \
     http://127.0.0.1:8000/api/v1/projects/open
   ```
   Expect `{"id":"proj-5e960453", …}`. Then ask whether to delete `proj-adf8a200` (the home
   directory registered as a project).
2. **Verify the five UI fixes in a real browser.** They are jsdom-verified only. Load
   `http://127.0.0.1:8000`, send a long message (item 2 — the box must shrink back), scroll during a
   run (item 4 — no bounce), navigate away and back mid-run (item 6 — timer keeps its age), stop and
   re-send (item 8 — indicator appears), open a spec then visit agent settings and press Back
   (item 7 — spec still attached).
3. **Build document adoption (finding 17).** Still the largest blocker to using the product: 35
   files on disk, no rows, and `POST /documents` destroys any file it is given. Read the rendered
   payload via `extract_payload` — it already carries `title`, `kind`, `schema_version` and the
   `aw_identity` block — and create the row **without rewriting the file**. Needs its own openspec
   change.
4. **Then the operator's remaining items**, all features: 1 (reasoning chain / "rationalization"
   block), 5 (spec landing page), 9 (agent creates an explore page), 10 (agent messages itself in
   another conversation), 11 (implementer field that auto-assigns on approval).
5. **Push the branch and open a PR** — 17 commits unseen by CI.
6. **Kill the port-8020 throwaway Hub** (`testbed/corpus-import-hub/`), left from handoff 0062.

## Open questions for the user

- **Item 7 — was the complaint about agent settings, or about project tabs and the Spec screen
  too?** Only the settings round trip was fixed. Widening it means overturning
  `App-mount.test.tsx`'s `does not resurrect a document when arriving from a project tab` and its
  recorded rationale. **Asked; not yet answered.**
- **Item 3 — does the URL bar say `localhost:8000` or `127.0.0.1:8000` between sessions?** Separate
  localStorage origins is the leading hypothesis for both the theme and the session loss.
  **Asked; not yet answered.**
- **Should the two retired `question_not_asked` display cases go too?** Kept for historical
  `event_logs` rows. **Told; not objected to.**
- **Delete `proj-adf8a200`** (the operator's home directory, registered as a project)?
- **Retire `openspec/specs/`?** Open since handoff 0062; it still duplicates the same capabilities
  now in `spec/capabilities/`.
- **`D-a13`** (Hub carries an agent's "please add this task" request with one-click accept) and
  **`D-naming`** (`openspec/explorations/2026-08-18-candidate-names.md`) — both still open.

## Read on resume

- `openspec/explorations/2026-08-20-dogfooding-findings.md` — **finding 18 first**; it is the full
  account of the database destruction, including the design point that the spawned-run environment
  is built by subtracting known-bad names and so fails open every time a variable is added.
- `openspec/explorations/2026-08-20-specs-in-flight-at-the-reset.md` — what the operator was
  specifying, and the live measurements that would be expensive to re-establish.
- `hub/tests/conftest.py` — `assert_engine_is_disposable` and `seed_test_project`; the two fixes
  that keep the suite from touching real data and from needing a bootstrap project.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx:250-405` — `handleScroll`, `scrollToNewest`,
  the tail-spacer effect and the two landing effects. The scroll behaviour is subtle and three
  operator complaints have now been fixed in this one region.
- `hub/ui/src/components/agents/AgentTimeline.tsx:108-135` — `lastRunSettled` /
  `anotherRunIsUnderway` / `runVisiblyActive`, the three-way condition behind the working indicator.
- `hub/ui/src/App.tsx:165-250` — the `lastConversationDocument` ref (declared at 169, above the
  bootstrap early-returns) and the `openDocument` fallback at 243-247, which is where item 7 would
  be widened.
