# Handoff: three changes archived, and the spec↔Hub design settled in exploration

**Date:** 2026-08-12T14:29+0100 · **Branch:** hub-native-experience · **HEAD:** `1f20106`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0036-2026-08-12-0907-charter-set-reshaped-and-read-view-shipped.md`
**Status:** **chunk complete.** Working tree clean, 0 unpushed. Nothing half-done.

## Goal

Handoff 0036 left B0 implemented but unarchived, one change proposed and untouched, and a 69-task
umbrella nobody had assessed. This session closed all three, then spent its second half in
**explore mode** settling the design question that has blocked the specification program since
2026-08-03.

The *why* that governs judgement calls here: **an unratified inference written as a decision is
worse than an open question**, because the next session cannot tell them apart. This session found
one, and the correction shaped everything after it.

## Current state

**Nothing is half-done.** Six commits, all pushed, working tree clean.

### 1. `2026-08-11-charter-set-reshape` (B0) — ARCHIVED

The operator created a fresh project, read the nine charters, and answered section 7:
**"No. That's enough."** — 7.4 answered *No*, nothing they used is among the fifteen removed. That
was the question with consequences and the reason the change was held open.

Two deltas synced: `agent-charter` 5 → **7 requirements**, `aw-spec-workflow`'s spec-role
requirement now forbids routing to mechanisms a project lacks. Verified afterwards that the
read-view requirement synced earlier the same day **survived** the second pass over `agent-charter`
— the two deltas touch disjoint requirements.

### 2. `2026-08-11-project-create-names-its-folder` — IMPLEMENTED AND ARCHIVED

Create mode now takes an existing parent (what Browse returns) plus a name (what Browse cannot
return). Target is `<parent>/<name>`; the preview is derived from the same value that is submitted.
Create sends **no name**, letting the backend's existing folder-name fallback supply it.

Bad names are **refused, not sanitised** — `nested/thing` errors rather than silently becoming
`nested-thing`. Portable cases are checked client-side; Windows reserved names and illegal
characters stay the server's to enforce.

Operator verified in the running app: *"You can close those two. They're working."* and, on losing
the separate display name in create mode, *"No i don't. That's okay."*

New: `hub/ui/src/lib/projectTarget.ts` (`pathSeparator`, `joinProjectPath`, `projectNameProblem`).

### 3. Umbrella `2026-07-30-hub-native-experience` — RECONCILED (not archived)

The "69 open tasks is probably bookkeeping" hypothesis was **wrong**, and checking rather than
assuming is what caught it. Phases 9–12 were already reconciled by earlier sessions. Phase 13 had no
closure note, and item-by-item checking found **four genuine gaps**:

| Item | Finding |
|---|---|
| **13.2** | **NOW CLOSED** — see below |
| **13.4** scope enforcement | No agent or charter scope field exists. Every `scope` hit in the Hub is the unrelated "project-scoped" phrasing. A charter *saying* stay in scope is not the runtime enforcing it |
| **13.9** single-agent omission | `agents.py:1023-1039` always emits `### Team`, falling back to "No other agents are registered". The requirement is to omit the roster **entirely** |
| **13.3** remainder | Shipped `Charter` is name + content; "scope, default skills" and "empty charter means full project scope" were never built |
| **13.11** | No effective-composition inspection surface; the `effective_*` symbols are heartbeat status |

13.5, 13.6, 13.7, 13.14 were left **explicitly unassessed** rather than guessed at.

**Phase 15 looks closed and is not.** The approval cards that shipped gate *tool calls and
questions*; 15.1's subject is *task-lifecycle and specification-gate* decisions, which still live on
`TasksBoard.tsx`. 15.2's evidence half is blocked on phase 14 regardless.

**Phase 16.2 is the concrete blocker to archiving.** Eight of ten delta specs are absent from
`openspec/specs/` under their original names — but the successors *renamed* capabilities as they
re-cut them, so absence by name proves nothing. Closing it is a per-requirement mapping against the
current 31 specs, **not** a re-run of the sync. `spec-authoring` and `spec-traceability` are
genuinely unbuilt (they are phase 14).

### 4. Umbrella task 13.2 — IMPLEMENTED (migration 0063)

`ix_agents_project_name` was a plain index since migration 0004; it is now unique, and `models.py`
matches. **What it fixes is a race, not a missing check** — registration already refuses duplicates
with 409 at `api/v1/agents.py:627` and `:1152`, but both SELECT then INSERT, and two concurrent
registrations interleave through that gap.

**Pre-existing duplicates are renamed, not deleted.** Failing the upgrade leaves the operator with a
Hub that will not start and no UI to repair it; deleting destroys history, since an agent owns
conversations, runs, tasks and messages by `id`. Oldest row keeps the name; later ones become
`<name>-2`, truncated to satisfy `AGENT_NAME_RE`.

Applied to the **live database**: head `0062 → 0063`, index unique, 3 agents intact
(`claude-1`, `claude-test-1`, `codex-1`), none renamed.

### 5. `openspec/explorations/2026-08-12-spec-hub-integration.md` — WRITTEN

The second half of the session, in explore mode. **Read this file before doing any spec work.** It
is deliberately structured as three sections that must not be conflated: **operator decisions**,
**proposed and agreed**, **open**.

Headline decisions (operator's own words are in the file):

- HTML stays; **the Hub is the only way it is used** — opening from outside is "the wrong path".
  This single decision makes task status **derived**, not written back into the file.
- Users do not hand-edit; the document is a **surface** with controls. Hand-edits are detected by
  digest and the **Hub never silently wins** — it surfaces both and waits.
- The spec **creates** tasks. Review is **adversarial and independent** — a different agent.
- Rejections carry **reasons**, so model and worker performance is measurable. **Reviewer**
  performance too.
- The spec charter is **good practice, not required** → *nothing load-bearing may live in a charter*.
- **JSON in, HTML out.** The agent emits a structured payload; the Hub renders. The Hub mints
  requirement IDs, not the agent.
- Abandoned explore documents are acceptable — an **idea backlog**, not litter.

### Board — 3 active changes

| change | open | needs |
|---|---|---|
| `2026-07-30-hub-native-experience` | 69 | phase 14 decided, then 16.2's mapping. Phase 13's gaps are independent |
| `2026-08-10-blocked-and-conversation-binding` | 4 | operator, over a day's real use |
| `2026-08-11-declining-a-question` | 2 | operator, same |

`openspec/specs/` is **31 capabilities**; `openspec/changes/archive/` holds **60**.

## Files touched

Working tree **clean**, **0 unpushed**. Six commits: `8cd38d9`, `324fedb`, `366c09d`, `ac0e2f7`,
`d5951d3`, `1f20106`.

| path | what | done? |
|---|---|---|
| `hub/ui/src/lib/projectTarget.ts` | **new** — separator detection, path join, name validation | yes |
| `hub/ui/src/components/projects/ProjectManagerModal.tsx` | create mode split into parent + name; preview derived; display name now open-mode only; `aria-label` added to it | yes |
| `hub/ui/src/__tests__/projectCreateTarget.test.tsx` | **new**, 21 tests | yes |
| `hub/hub/migrations/versions/0063_unique_agent_name_per_project.py` | **new**, guarded, renames duplicates | yes |
| `hub/hub/db/models.py` | `ix_agents_project_name` gains `unique=True` | yes |
| `hub/tests/test_migrations.py` | 9 head assertions → `0063`; +5 tests with a schema-driven insert helper | yes |
| `hub/tests/test_project_persistence.py` | 1 head assertion → `0063` | yes |
| `hub/hub/static/ui/**` | rebuilt, `diff -rq` identical | yes |
| `openspec/specs/agent-charter/spec.md` | 5 → 7 requirements | yes |
| `openspec/specs/aw-spec-workflow/spec.md` | spec-role requirement rewritten | yes |
| `openspec/specs/local-project-workspace/spec.md` | creation + browsing requirements rewritten | yes |
| `openspec/changes/2026-07-30-hub-native-experience/tasks.md` | reconciliation notes for phases 13, 15, 16 | yes |
| `openspec/changes/archive/2026-08-11-charter-set-reshape/` | archived | yes |
| `openspec/changes/archive/2026-08-11-project-create-names-its-folder/` | archived | yes |
| `openspec/explorations/2026-08-12-spec-hub-integration.md` | **new** — the design capture | yes |
| `testbed/scratch/charter_seed_probe.py` | seeding probe — **gitignored**, uncommitted | kept |

## Key decisions

1. **Checkboxes stay unchecked in the umbrella; prose notes record closure.** That is the file's own
   pre-existing reconciliation rule, not a new invention.
2. **Migration 0063 renames duplicate agent names rather than deleting or failing.** Relationships
   reference `agents.id`, never the name, so renaming is non-destructive.
3. **The 0063 tests build agent rows from `PRAGMA table_info`** rather than a fixed column list, so a
   later migration adding a required column does not turn them into a puzzle about the agents schema.
4. **Project creation sends no `name`**, making the backend's existing fallback visible instead of
   duplicating it client-side.
5. **A bad project name is refused, never sanitised.**
6. **The exploration separates operator decisions from agent proposals** — see Dead ends for why.

## Constraints and user directives (verbatim)

**From this session:**
- *"No. That's enough."* — B0 section 7; 7.4 answered No.
- *"You can close those two. They're working."* — project creation 5.1/5.2.
- *"No i don't. That's okay."* — does not miss the display name in create mode.
- *"I'm not sure I made that call. Could've been hallucinated or buried in something else"* — on the
  phase-on-document decision. **They were right.**
- *"I want more like an adversarial position from testers where they trust nothing that's why a
  different agent should review."*
- *"I don't want to review every little thing. AI is here to assist me. But there are some things
  that can only be approved by the user."*
- *"Not necessarily I want to use the charter for spec. Is good practice but I can skip it."*
- *"Wait I want to explore and deep dive into this before writing anything."*

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **Handoff cadence:** only when asked, or when an openspec change is done.
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion, **not**
  question modals.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task complete
  on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session — the one that matters most:**

- **An exploration wrote "Resolved by…" for a question the operator was never asked**, and three
  sessions later it read as ratified. This agent presented it to them as "already ruled out". The
  operator's instinct caught it. `2026-08-10-charters-phases-and-the-spec-on-ramp.md` contains
  **zero operator attributions**, and its own *Open, carried forward* list still asks *"Is 'explore'
  a phase, or just the absence of one?"* — the very question the resolution appeared to close.
  **Check attribution before repeating a prior exploration's conclusion as settled.**
- **"Restore the aw-spec skills" was wrong advice**, given earlier the same day.
  `.claude/skills/` is Claude-only; a Codex agent can never invoke them. Corrected in the exploration.
- **`git commit -m @'…'@` is PowerShell syntax and the Bash tool is Git Bash** — it produced a commit
  whose subject was a literal `@`. Use a heredoc into a file and `git commit -F`.
- **Git Bash converts `/tmp` in *arguments* but not in string literals inside a script.** A probe with
  `Path("/tmp/oldcharters")` silently scanned a nonexistent `C:\tmp\...` and reported 0 matches,
  which looked exactly like a working assertion failing to fire. **Pass paths via `sys.argv`.**
- **`sed -i` ate `\\s`, and a Python heredoc turned `\\b` into literal backspace characters
  (`\x08`)** in a test file. For regex-bearing edits use the Edit tool or `chr(92)`.
- **`line-clamp` clamps only what is painted** — the full text stays in the DOM.
- **`projects` is not created by the migration chain** (it comes from `create_all`), so a
  from-scratch alembic run has `agents` but no `projects`. Migration tests must not insert into it.
- **A blind `"0062"` → `"0063"` replace also hit two assertion *message* strings**, leaving them
  saying `expected alembic_version=0062`. Check the diff after a mechanical replace.

**Carried and still true:**
- **The Bash tool's cwd persists across calls.** Bit again this session. Use absolute paths.
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
  Find the real PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen` — `Invoke-CimMethod`
  returns the `cmd.exe` wrapper's PID.
- **`openspec` CLI rejects change names starting with a digit** — create and archive by hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. Use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check. **`npx tsc`/`npx vitest` fail
  outside `hub/ui`.**
- **Nine UI test files mock `@/api/questions` and seven mock `@/api/permissions` without
  `importOriginal`.** New test files should use `importOriginal` to avoid joining that set.
- **`hub/data/agentweave.db` is the live database.** Project `proj-cddb0827`, named **Testbed**.
- **`black --check` flags four pre-existing files this session never touched** — left alone.

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1517 passed, 10 skipped** (1512 + 5 new migration tests).
- `pytest tests/ -q` — **372 passed, 3 skipped**, baseline.
- `npx vitest run` — **805 passed across 82 files** (784/81 before). `npx tsc --noEmit` exit 0.
- `ruff check hub/ src/` — passed. `black` applied to every file touched.
- `npx openspec validate --specs --strict` — **31 passed**; `--changes --strict` — **3 passed**.
- **Migration 0063 applied to the live database**: head `0063`, `PRAGMA index_list` reports
  `unique=1`, 3 agents intact and unrenamed.
- **Hub restarted twice by exact PID**, serving the current build — HTML references
  `index-Dc8iDkRa.js` / `index-CtWaK2H-.css`, matching `hub/hub/static/ui/assets` exactly.
- **Spec-sync round-trip gate** over all 31 main specs before each of the two syncs.

**NOT run, and deliberately:**
- **The project-creation change was never exercised by this agent in the running app.** Sections 5
  and 6 were closed on the operator's report. No agent opened a host folder dialog.
- **No agent process has been spawned against any of the nine charters.** They are verified as text.
- **Nothing from the exploration is implemented.** It is a design document; no code exists for any of
  it.
- **`blocked-and-conversation-binding` and `declining-a-question`** untouched — 6 tasks needing a day
  of real use.
- **Phase 13's four remaining gaps, phase 15, and phase 16.2** are recorded, not fixed.

## Git state

Branch `hub-native-experience`, HEAD **`1f20106`**, working tree **clean**, **0 unpushed**.

Hub running as PID **20784** on `:8010`, started 2026-08-12 ~10:00, serving the 0063 schema and the
current UI build. `.claude/handoffs/` is **tracked, not gitignored** — 123 files.

## Next steps

1. **Turn the exploration into a proposal.** Read
   `openspec/explorations/2026-08-12-spec-hub-integration.md` first — all of it, including §3 Open.
   The first implementable slice is the one the 2026-08-03 authority exploration named: **portable
   document authority and stable requirement identity**. Concretely: the JSON payload schema, the
   Hub-side renderer, and Hub-minted requirement IDs. **Do not freeze the format contract** — §3 item
   5 says traceability and gates must state their requirements on it first, or every document needs
   migrating later.
2. **Or close phase 13's remaining gaps**, which are small, concrete and independent of the spec
   program. `13.9` is the cheapest: `hub/hub/api/v1/agents.py:1023-1039` should omit the `### Team`
   block entirely for a single-agent project rather than emitting "No other agents are registered".
3. **Or clear the last 6 operator tasks** on `blocked-and-conversation-binding` and
   `declining-a-question`, which archives two more changes.
4. **Not yet:** phase 16.2's mapping. It is the umbrella's blocker but it is downstream of phase 14
   existing at all.

## Open questions for the user

1. **Everything in §3 of the exploration** — reconciliation mechanics, the rejection category
   vocabulary, reviewer metrics beyond counts, and whether the spec phase machine shares an
   implementation with B1's transition machine (explicitly flagged as blocking nothing).
2. Carried: should `.claude/handoffs/` stay tracked (**123 files**);
   `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.
3. Carried from 0035, still unconfirmed: **should dismissing a *pending* permission request be
   allowed?** Currently refused with 409.
4. **Resolved this session, do not re-ask:** whether to keep HTML (yes); whether the Hub or the agent
   writes it (Hub, from JSON); whether explore starts from a pill or a document (document, via an
   entry point that may look like a pill); whether abandoned documents are acceptable (yes).

## Read on resume

- **`openspec/explorations/2026-08-12-spec-hub-integration.md`** — the whole design. Its three-way
  split is load-bearing: do not promote a §2 item to a §1 decision, and do not treat §3 as settled.
- **This file's "Dead ends"**, particularly the unratified-decision trap — it is the reason the
  exploration is structured the way it is.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — the phase 13/15/16 reconciliation
  notes, if any umbrella work is picked up.
- `hub/hub/api/v1/agents.py:1023-1039` — the `### Team` block, which is next-step 2.
- `hub/hub/api/v1/spec.py` and `hub/ui/src/components/spec/` — the existing spec surface the new
  design has to replace or absorb.
- `testbed/scratch/sync_delta.py` — **gitignored but reusable**; carries the round-trip gate and the
  `spec-chat-session` skip with its evidence.
