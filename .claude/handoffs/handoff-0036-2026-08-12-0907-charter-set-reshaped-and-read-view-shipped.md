# Handoff: the charter set re-shaped, and a read view shipped to make it judgeable

**Date:** 2026-08-12T09:07+0100 · **Branch:** hub-native-experience · **HEAD:** `6916851`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0035-2026-08-11-1635-approval-defect-fixed-and-six-changes-archived.md`
**Status:** **chunk complete.** Working tree clean, 0 unpushed. B0 implemented and verified; one
new change proposed, implemented, verified and archived; one more proposed and untouched.

## Goal

Handoff 0035 left B0 (`2026-08-11-charter-set-reshape`) fully specced with zero implementation. This
session implemented it end to end. The operator then created a fresh project to run its section 7
and found two defects in the process, one of which **blocked that very verification** — so it was
proposed, built and archived inside the same session.

The *why* that governs judgement calls here: **a charter is injected into an agent's turn verbatim,
so it is instruction, not documentation.** Every decision below follows from treating a charter that
names something absent as an active defect rather than stale prose.

## Current state

**Nothing is half-done.** Six commits, all pushed, working tree clean.

### 1. `2026-08-11-charter-set-reshape` (B0) — IMPLEMENTED AND VERIFIED, **NOT ARCHIVED**

Seeded charter set went **21 → 9**. Sections 1–6 all closed; **section 7 (4 tasks) is the operator's
and is the only thing between this change and archive.**

| | |
|---|---|
| **Rewritten (6)** | `tech_lead` (absorbs `architect`), `code_reviewer`, `verifier` (absorbs `qa_engineer`), `guardian`, `security_engineer`, `spec` |
| **New (3)** | `developer`, `underwriter`, `underwriting_approver` |
| **Removed (15)** | six `*_dev`/`*_engineer` variants, `coordinator`, `model_router`, `project_manager`, `explorer`, `implementer`, `context_keeper`, `architect`, `qa_engineer`, `technical_writer` |

**Three places where checking a task's premise found it wrong** — all three are the highest-value
work in the change, and all are recorded in the commit message of `919e3e3`:

1. **Task 2.2 was factually wrong.** It asserted `code_reviewer` "cites nothing absent". Step 5 of
   its zero-trust sequence pointed at `quality.docs_path` and `.agentweave/code-docs/<task-id>.md`.
   Those only exist if a CLI session synced a `quality` block (`hub/hub/api/v1/agents.py:1042`,
   `(session_data or {}).get("quality")`), which a Hub-owned project never does. The step now
   derives intent from the task and says so in the review.
2. **Task 5.1's own wording was too narrow.** Escalation-shaped directives alone caught only 19 of
   21 pre-change charters. `tech_lead` and `context_keeper` used `(that belongs to Technical Writer)`
   and `surface the conflict to Coordinator`. Adding `belongs to` and `surface ... to` took the
   negative control to **21 of 21**.
3. **`guardian` and `security_engineer` overlapped heavily** — old `guardian` line 17 literally
   disclaimed "duplicating the broader classic-security remit of the `security_engineer` role".
   Re-framing `guardian` onto *the standards that outlive one change* (per task 2.4) is what
   dissolves that, rather than shipping two security charters that reference each other.

**The absent-participant test now exists** in `hub/tests/test_agent_facing_text.py`. It is keyed to
the **shape** of the defect — a directive verb followed by a Title-Case roster title — explicitly
*not* to a list of titles, because a title list would pass on the very bug it was written for (the
manifest contains exactly the titles that are legitimately present). Design D6 records this.

**Parked content** lives at
`openspec/changes/2026-08-11-charter-set-reshape/parked-phase-guidance/` — `explorer.md`,
`implementer.md`, `context_keeper.md` (byte-identical copies), plus three verbatim excerpts cut from
`spec.md`, plus a `README.md`. The README also records **what was deleted rather than parked, and
why**, so the directory does not become a dumping ground.

### 2. `2026-08-11-charter-read-view` — PROPOSED, SHIPPED, **ARCHIVED** this session

The operator, trying to run B0's section 7, reported: *"the charter looks good but I don't know what
contains in each from inside the hub so it's hard to judge we need some way to view"*.

Confirmed: `ChartersPage.tsx` clamped content to two lines, and the only other surface was the
pencil → an **edit** dialog with a `<textarea>`. Reading required opening a writable form.

- **A disclosure in the list, not a read-only modal.** The operator's task is comparing *the set*; a
  modal is one-at-a-time by construction. Rows expand independently, several at once.
- **A test caught something the proposal had wrong.** `line-clamp` clamps only what is *painted* —
  the full document stayed in the DOM, so a screen reader would read every charter in full and the
  disclosure would buy its user nothing. Added `charterSummary()` (exported, unit-tested): drops the
  leading `# Heading` because it repeats the charter name directly above it, flattens whitespace,
  cuts at 160 chars on a word boundary.
- **No markdown renderer added.** `hub/ui` has none; a renderer brings a sanitisation question for
  operator-authored text; and verbatim display is byte-for-byte what the agent receives.
  **The operator answered section 4.1 — "That is enough" — so D2's deferral stands and no renderer
  follow-up is owed.**

### 3. `2026-08-11-project-create-names-its-folder` — PROPOSED ONLY, zero implementation

The other defect from the fresh-project walkthrough, in the operator's words: *"When creating a
project you can just chose a folder. You have to chose a folder then write after /folder_name this
is bad practice. Make the project name be the folder name"*.

**Verified root cause:** `create_new` refuses a target that exists
(`hub/hub/project_lifecycle.py:99-100`) and then creates it (`:108`), while **both** browse
affordances return a directory that exists. **In create mode the picker can never produce a valid
answer.** It is structural, not cosmetic.

**Important and easy to miss:** the behaviour the operator asked for **already exists** —
`hub/hub/project_lifecycle.py:85` does `name=name or canonical.path.name`. Leaving "Display name"
blank already names the project after the folder. The form simply never says so. Most of that change
is making a correct behaviour *visible*, not adding one — which is why **task 1.1 verifies the
backend needs no change before anything is built on that assumption.**

### Board — 5 active changes

| change | open | needs |
|---|---|---|
| `2026-07-30-hub-native-experience` | 69 | long-running umbrella; untouched for several sessions |
| `2026-08-11-project-create-names-its-folder` | 24 | **agent work — fully specced, no unknowns** |
| `2026-08-11-charter-set-reshape` | 4 | **operator only — section 7, then archive** |
| `2026-08-10-blocked-and-conversation-binding` | 4 | operator, over a day's real use |
| `2026-08-11-declining-a-question` | 2 | operator, same |

`openspec/specs/` is **31 capabilities**; `openspec/changes/archive/` holds **58**.

## Files touched

Working tree **clean**, **0 unpushed**. Six commits: `7610e99`, `919e3e3`, `3f5cf2b`, `5043f62`,
`cead032`, `6916851`.

| path | what | done? |
|---|---|---|
| `hub/hub/data/charters/tech_lead.md` | rewritten; absorbs `architect` | yes |
| `hub/hub/data/charters/code_reviewer.md` | rewritten; decision-doc citation removed | yes |
| `hub/hub/data/charters/verifier.md` | rewritten; absorbs `qa_engineer` | yes |
| `hub/hub/data/charters/guardian.md` | rewritten onto durable standards | yes |
| `hub/hub/data/charters/security_engineer.md` | rewritten; absorbs guardian's AI-security content | yes |
| `hub/hub/data/charters/spec.md` | largest rewrite; judgment kept, procedure cut | yes |
| `hub/hub/data/charters/developer.md` | **new** — replaces six variants, carries a Scope line | yes |
| `hub/hub/data/charters/underwriter.md` | **new** — non-software pair, half 1 | yes |
| `hub/hub/data/charters/underwriting_approver.md` | **new** — non-software pair, half 2 | yes |
| `hub/hub/data/charters/charters.json` | re-keyed to 9 entries | yes |
| 15 × `hub/hub/data/charters/*.md` | **deleted** (`git rm`) | yes |
| `hub/tests/test_agent_facing_text.py` | +4 assertions, +2 `REMOVED_SUBSYSTEMS` needles | yes |
| `hub/tests/test_charters_api.py` | +3 tests (inertness, both-directions, unique names) | yes |
| `hub/tests/test_agents_self_registered.py` | `"Backend Developer"` lookup → first seeded charter | yes |
| `hub/ui/src/components/charters/ChartersPage.tsx` | disclosure + read region + `charterSummary()` | yes |
| `hub/ui/src/__tests__/charterReadView.test.tsx` | **new**, 17 tests | yes |
| `hub/hub/static/ui/**` | rebuilt, `diff -rq` identical | yes |
| `openspec/specs/agent-charter/spec.md` | read-view delta synced in (1 requirement modified) | yes |
| `openspec/changes/2026-08-11-charter-set-reshape/{tasks,design}.md` | 29 of 33 closed; D4 path corrected | yes |
| `openspec/changes/2026-08-11-charter-set-reshape/parked-phase-guidance/` | **new**, 7 files | yes |
| `openspec/changes/archive/2026-08-11-charter-read-view/` | **new then archived**, 4 artefacts | yes |
| `openspec/changes/2026-08-11-project-create-names-its-folder/` | **new**, 4 artefacts, unimplemented | proposal only |
| `testbed/scratch/charter_seed_probe.py` | seeding probe — **gitignored**, intentionally uncommitted | kept |

## Key decisions

1. **A charter answers "what am I accountable for"; a phase answers "what am I doing right now."**
   The whole 21→9 sort is mechanical once this test is applied (design D1).
2. **Software specialisation is scope, not identity (D2).** `backend_dev` and `frontend_dev` are
   answerable for the same thing. One `developer` with an operator-filled Scope line, and **no "you
   are not responsible for" list** — the old variants told a lone developer agent half its work
   belonged to someone who did not exist.
3. **Coordination charters go because the guarantee moved into code (D3).** A prose instruction beside
   a code guarantee is strictly worse than either alone.
4. **Removed activity content is parked, not deleted (D4).** *Recoverable is not the same as
   findable* — nobody greps a deleted file they do not know existed.
5. **Underwriting ships as a pair (D5).** One capable model can perform every activity in a dev
   workflow, which makes charters look like topic labels; a separation of duties is what shows a
   charter carrying a guarantee. Each names the **step** it may not perform; **neither names the
   other as a party to contact** (task 3.4 verified this by grep).
6. **The absent-participant test asserts on directive shape, never a title list (D6).** A title list
   would pass on today's bug.
7. **The inertness assertion is a positive invariant, not a reference to the parked path** — that
   path moves when the change is archived. It asserts every manifest key resolves to a file directly
   inside `hub/hub/data/charters/`.
8. **Read view is a disclosure, not a modal (read-view D1).** A modal fixes the smaller half and
   leaves comparing nine charters exactly as hard.
9. **No markdown renderer (read-view D2)** — confirmed by the operator's "That is enough".
10. **Create mode takes a parent + a name; open mode keeps its directory field** (project-create D1).
    Rejected widening `create_new` to accept an existing empty directory — that fixes a form by
    weakening a deliberate safety boundary.
11. **A bad project name is refused, never sanitised** (project-create D3). Rewriting `my/project`
    into `my-project` creates a directory the operator did not ask for at a path they did not see.

## Constraints and user directives (verbatim)

**From this session:**
- *"When creating a project you can just chose a folder. You have to chose a folder then write after
  /folder_name this is bad practice Make the project name be the folder name"*
- *"Also the charter looks good but I don't know what contains in each from inside the hub so it's
  hard to judge we need some way to view"*
- *"That is enough. We can archive this change"* — read as answering read-view section 4.1 and
  authorising the archive of **`charter-read-view`**. **`charter-set-reshape` was deliberately left
  open**, because its section 7 asks whether anything the operator actually used is among the fifteen
  removed, and that had not been answered.
- *"Whats next?"* — again wanting a short prioritised answer, not a survey.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*, not a draft PR. **Do not raise it
  again.**
- **Handoff cadence:** only when asked, or when an openspec change is done.
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and wall-clock. Wants short
  prioritised answers and forward motion, **not** another question modal.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task complete
  on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**

- **I used PowerShell here-string syntax (`-m @'...'@`) in the Bash tool** and committed a message
  with a literal `@` as its subject line. The Bash tool is Git Bash. **Use a heredoc into a file and
  `git commit -F`** — that is what worked every time afterwards.
- **Git Bash mangles `/tmp` in *arguments* but not in string literals inside a script.** A probe with
  `CHARTER_DIR = Path("/tmp/oldcharters")` silently scanned a nonexistent `C:\tmp\oldcharters` and
  reported **0 matches**, which looked exactly like "the assertion does not fire". Cost real time and
  nearly caused a correct assertion to be rewritten. **Pass paths as `sys.argv`,** which Git Bash
  converts properly.
- **`sed -i` with `\\s` in the replacement ate the backslashes**, producing `s+` instead of `\s+`.
  Then a Python heredoc writing `\\b` produced literal **backspace characters** (`\x08`) in the test
  file. **For regex-bearing edits, use the Edit tool or `chr(92)`,** not sed and not nested escaping.
- **`line-clamp` clamps only what is painted.** The full document stays in the DOM. Any test asserting
  "collapsed content is absent" fails, and any accessibility claim based on the clamp is false.
- **A test needle chosen inside the truncation window gives a false failure.** `charterSummary()` cuts
  at 160 chars; asserting on a phrase that survives the cut looked like the summary was broken.
- **`black --check` still flags four files this session never touched** — `test_accounting_budget.py`,
  `test_task_transitions.py`, `test_project_workspace_unavailable.py`, `test_agent_trigger.py`.
  Pre-existing drift, **left alone deliberately.**

**Carried and still true:**
- **The Bash tool's cwd persists across calls.** Bit twice again this session. Use absolute paths or
  re-`cd`.
- **A background shell started with the Bash tool dies at session teardown.** Start the Hub via WMI:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
  Find the real PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`.
- **`openspec` CLI rejects change names starting with a digit** — every change here is digit-initial,
  so `openspec new change` and the archive skill's status step cannot be used. Create and archive by
  hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. Default `python` has no
  pytest; use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check. **`npx tsc`/`npx vitest` fail
  outside `hub/ui`.**
- **Nine UI test files mock `@/api/questions` and seven mock `@/api/permissions` without
  `importOriginal`** — adding one export to either breaks dozens of tests. `charterReadView.test.tsx`
  deliberately uses `importOriginal` to avoid joining that set.
- **`hub/data/agentweave.db` is the live database.** Project `proj-cddb0827`, named **Testbed**.
- **`openspec validate --strict` only inspects a requirement's OPENING LINE for SHALL/MUST.**

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1512 passed, 10 skipped.** Arithmetic against the 1514 baseline: −24
  (12 fewer charter files × 2 parametrized honesty tests), +18 (9 files × 2 new parametrized
  assertions), +4 standalone.
- `pytest tests/ -q` — **372 passed, 3 skipped**, exactly the baseline; no CLI code touched.
- `npx vitest run` — **784 passed across 81 files** (767/80 baseline, +17 in one new file).
  `npx tsc --noEmit` exit 0.
- `ruff check hub/ src/` — all checks passed. `black` applied to the two test files it flagged.
- `npx openspec validate --specs --strict` — **31 passed**; `--changes --strict` — **5 passed**.
- **Negative control for all four new assertions against the pre-change charter text** (extracted
  from `git show 7610e99`): addresses-a-roster-title **21/21 files would fail**; names-an-aw-skill
  **1/21** (`spec.md`); `shared/design-` **2/21**; `shared/plan-` **2/21**; the non-software pair is
  absent from the pre-change manifest. **0 of 9 post-change files flagged.**
- **Negative control on the inertness assertion:** a manifest key crafted to reach the parked
  directory fails three of its four checks; a real key passes all four.
- **Scratch-database seeding probe** (`testbed/scratch/charter_seed_probe.py`) — **12/12 checks.** A
  fresh project seeds exactly nine byte-for-byte; a project holding the old 21 survives two
  `init_db()` restarts with nothing added, removed or rewritten, including an operator-edited
  charter. The live DB was SHA-256 fingerprinted before the Hub was imported and re-checked after —
  byte-identical.
- **Defect-inventory grep over the nine shipped charters** — zero hits on `aw-spec-`, `shared/`,
  `spec/index.json`, `agentweave.yml`, `roles.json`, `watchdog`, `principal`, and each of the fifteen
  removed charters' display titles.
- **Spec-sync round-trip gate** — all 31 main specs parse and reassemble byte-identically before the
  read-view delta was applied.

**NOT run, and deliberately:**
- **The operator has not answered `charter-set-reshape` section 7** (4 tasks). In particular 7.4 —
  *"is anything you actually used among the fifteen removed?"* — is unanswered, and it is the one
  with real consequences.
- **`project-create-names-its-folder` is a proposal only — zero implementation, zero verification.**
- **The Hub was not restarted after the UI rebuild**, so the operator has not seen the charter read
  view on screen. Backend, component tests and build artefact all pass; the live app was not
  exercised.
- **No agent process was spawned against any of the nine new charters.** They are verified as *text*
  (greps and assertions), not by watching a real agent behave under one.
- **`blocked-and-conversation-binding` and `declining-a-question`** untouched — 6 tasks needing a day
  of real use.
- **`2026-07-30-hub-native-experience` (69 open) was not touched or assessed.**
- **`black` was not run over the four pre-existing drift files.**

## Git state

Branch `hub-native-experience`, HEAD **`6916851`**, working tree **clean**, **0 unpushed**
(`origin/hub-native-experience` is at HEAD).

`.claude/handoffs/` is **tracked, not gitignored** — 122 files. Still worth deciding; they are
session notes, so ignoring them is usually right.

No Hub process was started this session.

## Next steps

1. **Implement `openspec/changes/2026-08-11-project-create-names-its-folder`, starting with task
   1.1.** Read `design.md` D1–D5 first. Task 1.1 is a *premise check*, not a formality: confirm
   against the running code that `POST` create already accepts a composed target
   (`hub/hub/api/v1/projects.py:279`, `create_new(body.path, name=body.name)`) and already defaults
   the project name from the folder (`hub/hub/project_lifecycle.py:85`). If either is false, backend
   work is in scope and the task list is wrong. Then task 2.1: in
   `hub/ui/src/components/projects/ProjectManagerModal.tsx`, replace create mode's single path field
   with a parent-directory field plus a project-name field, leaving open mode's shape alone.
2. **Ask the operator `charter-set-reshape` section 7** — four questions, listed verbatim under Open
   questions below. Their answers close the change; then sync its two deltas
   (`agent-charter`, `aw-spec-workflow`) with `testbed/scratch/sync_delta.py` and archive it.
   **Note the ordering constraint:** `charter-set-reshape`'s `agent-charter` delta touches different
   requirements than the read-view delta already synced, so it applies cleanly — but it must not be
   synced before section 7 is answered.
3. **Assess `2026-07-30-hub-native-experience` (69 open).** Untouched for several sessions; five
   changes turned out to be already-done when a comparable backlog was last checked.
4. **Remaining roadmap:** A2 (shell conformance audit), then B2–B7.

## Open questions for the user

1. **`charter-set-reshape` section 7, verbatim:**
   - 7.1 Does nine charters read as a set you would pick from, or as a set with something missing?
   - 7.2 Does `developer` with an empty scope line read as incomplete, or as inviting?
   - 7.3 Do the two underwriting charters make the point they are there to make, or read as noise in
     a software tool?
   - 7.4 **Is anything you actually used among the fifteen removed?** — the one with teeth.
2. Carried: should `.claude/handoffs/` stay tracked (**122 files, confirmed not gitignored**);
   `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.
3. Carried from 0035, still unconfirmed: **should dismissing a *pending* permission request be
   allowed?** Currently refused with 409. The operator was told and has not objected or confirmed.
4. **Resolved this session, do not re-ask:** whether to add a markdown renderer (no — *"That is
   enough"*); which of the two walkthrough defects to fix first (the read view, because it blocked
   section 7).

## Read on resume

- **This file's "Dead ends" first** — the `/tmp` path-mangling trap cost real time and made a working
  assertion look broken, and the PowerShell-heredoc-in-Bash mistake corrupted a commit message.
- `openspec/changes/2026-08-11-project-create-names-its-folder/design.md` — D1–D5, and `tasks.md`
  §1–§2, which are next-step 1.
- `hub/ui/src/components/projects/ProjectManagerModal.tsx` — the file next-step 1 edits; note it is
  shared by both create and open mode, and open mode must not change.
- `hub/hub/project_lifecycle.py:85` and `:95-120` — the two facts the whole project-create change
  rests on: the folder-name fallback, and that `create_new` requires a nonexistent target.
- `hub/tests/test_agent_facing_text.py` — the absent-participant pattern and `NOT_A_PARTY`, if any
  charter text is ever touched again.
- `testbed/scratch/sync_delta.py` — **gitignored but reusable.** Needed to archive
  `charter-set-reshape`; it carries the round-trip gate and the `spec-chat-session` skip with its
  evidence.
