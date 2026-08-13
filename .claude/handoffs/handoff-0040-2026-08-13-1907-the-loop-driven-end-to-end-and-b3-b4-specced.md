# Handoff: the whole loop driven end to end, ten defects found, three fixed, B3 and B4 specced

**Date:** 2026-08-13T19:07+0100 · **Branch:** hub-native-experience · **HEAD:** `2afd868`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0039-2026-08-13-1130-three-causes-behind-one-symptom-and-the-spec-flow-completing.md`
**Status:** **chunk complete.** 12 commits this session, 24 unpushed in total, working tree clean.

## Goal

Two things, in sequence. First: finish the document-naming work the previous session left as its
next step. Then the operator asked for something bigger — **drive the entire product loop end to
end** (explore → spec → tasks → build → review → approve), fix what is clearly broken, and record
everything. That run found ten defects and turned into the session's centre of gravity: three are
fixed, the rest are recorded, and the two roadmap changes that address most of them (B3, B4) are now
fully specified.

The *why* matters for judgment calls later: **every serious finding lived between two features, not
inside one.** 1693 unit tests were passing while an agent could not read the specification it was
implementing. That is the argument for the `/e2e-loop` skill existing at all.

## Current state

### Shipped and verified this session

1. **`0fca6a5` + `b79224c` + `193856d` + `6cb5b0c` — a document earns its name.** New documents get a
   Hub-minted placeholder (`spec/changes/amber-griffin/spec.html`); the agent renames by *subject*
   once the interview establishes what it is. Verified live: `indigo-basilisk` →
   `shared-flatmate-expense-command-line-tool`, called unprompted by a real agent in its first turn.
   Also folded in two renderer fixes found by reading the first agent-authored document
   (acceptance criteria now group by requirement; empty open-questions says "None outstanding").
2. **`45a0486` — the end-to-end findings record**,
   `openspec/explorations/2026-08-13-explore-to-development-end-to-end.md`. F1–F10, ranked by cost.
3. **`9cb4a2f` — retirement is cumulative (F7).** `read_identity` never read the stored `retired`
   map back, so a retirement survived exactly one further save.
4. **`0e8d042` — the `/e2e-loop` skill**, `.claude/skills/e2e-loop/{SKILL.md,e2e.py}`. The harness
   moved out of gitignored scratch so it survives the machine.
5. **`72afb3c` — F2 and F3 fixed.** Default Claude posture is now `workspace` (was `acceptEdits`,
   which could edit but never execute); peer- and job-opened conversations inherit the agent's most
   recent overrides so the operator's posture survives a handoff.

### Specified, not implemented

6. **`e1064cc` + `fd27fd1` + `d2dfa34` — B3**, `2026-08-13-a-requirement-knows-its-work`. All four
   open questions answered by the operator; **nothing blocking**.
7. **`2afd868` — B4**, `2026-08-13-a-gate-that-only-evidence-opens`. Depends on B3 phases 1–4.

### The product the E2E run built

`C:\Users\huida\Documents\aw-e2e` (project `proj-471e281a`) — a flatmate expense-splitter CLI with
`init`, `expense`, `correct`, `repay`, `settle`, `balance`. **99 tests passing.** I verified the
settlement arithmetic by hand rather than trusting the agents; it is correct to the cent, including
the rounding remainder landing on the payer. **All of it lives on branch `agentweave/builder`;
`master` has only `README.md`.**

## Files touched

Everything is committed; `git status --short` is empty. Listed by commit.

| path | what |
|---|---|
| `hub/hub/spec_naming.py` | **new** — placeholder minting (colour + mythic animal) and `slugify` |
| `hub/hub/spec_render.py` | acceptance criteria sorted by requirement (stable); "None outstanding" |
| `hub/hub/spec_service.py` | `rename_document`, `_repoint_pending_input`; cumulative `retained(...)` |
| `hub/hub/spec_documents.py` | `move_document`, `_prune_if_empty` |
| `hub/hub/spec_identity.py` | **F7** — `read_retired`, `retained` now accumulates |
| `hub/hub/api/v1/spec.py` | `DocumentCreate.path` optional; `_mint_document_path`; `UNTITLED` |
| `hub/hub/api/v1/agent_actions.py` | `POST /spec/documents/rename` |
| `hub/hub/api/v1/agents.py` | `rename_spec_document` in the described tool surface |
| `hub/hub/launchability.py` | exploring turn notice tells the agent to rename |
| `hub/hub/mcp_server.py` | `rename_spec_document` tool (**above** the `__main__` guard) |
| `hub/hub/runner_commands.py` | **F3** — default posture → `workspace`, fallback when no approver |
| `hub/hub/conversations.py` | **F2** — `inherit_runtime_overrides`, `UNINHERITED_PERMISSION_MODE` |
| `hub/hub/scheduler.py`, `hub/hub/api/v1/messages.py` | wired inheritance into job + peer paths |
| `hub/hub/api/v1/agent_trigger.py` | comment only — operator path deliberately does **not** inherit |
| `hub/tests/test_spec_naming.py`, `test_spec_rename.py`, `test_override_inheritance.py` | **new** |
| `hub/tests/test_spec_render.py`, `test_spec_documents_api.py`, `test_spec_turn_notice.py`, `test_mcp_tool_schemas.py`, `test_mcp_server_stdio_surface.py`, `test_permission_approver.py`, `test_agent_default_permission_mode.py` | updated |
| `hub/ui/src/api/spec.ts` | `path` optional; `useSpecDocumentRename`; removes stale query key |
| `hub/ui/src/components/agents/{ConversationView,NewConversationSurface}.tsx` | stop deriving paths |
| `hub/ui/src/components/spec/SpecPage.tsx` | follows a rename |
| `hub/ui/src/__tests__/specDocumentRename.test.tsx` | **new** |
| `hub/ui/src/__tests__/newConversationSurface.test.tsx` | updated for minted paths |
| `hub/ui/src/lib/specDocumentName.ts` + its test | **deleted** — dead after the UI stopped guessing |
| `hub/hub/static/ui/` | rebuilt, `diff -rq` clean |
| `.claude/skills/e2e-loop/SKILL.md`, `e2e.py` | **new** |
| `openspec/explorations/2026-08-13-explore-to-development-end-to-end.md` | **new** — F1–F10 |
| `openspec/changes/2026-08-13-a-document-earns-its-name/` | complete, implemented |
| `openspec/changes/2026-08-13-a-posture-that-survives-the-handoff/` | complete, implemented |
| `openspec/changes/2026-08-13-a-requirement-knows-its-work/` | **B3 — specified only** |
| `openspec/changes/2026-08-13-a-gate-that-only-evidence-opens/` | **B4 — specified only** |

**Gitignored, not in git status:** `testbed/scratch/e2e.py` (superseded by the skill's copy) and
`testbed/scratch/spec_loop.py`.

## The ten findings, and where each stands

Full detail in `openspec/explorations/2026-08-13-explore-to-development-end-to-end.md`.

| | finding | status |
|---|---|---|
| **F1** | A building agent cannot read the spec it implements — `spec/` is untracked, so absent from every agent worktree. Turn context gives a path but never content. The builder worked from the task's copied text. | **open** — B3 unblocks it |
| **F2** | Peer/job triggers open a new conversation, silently losing the operator's permission posture | **fixed** `72afb3c` |
| **F3** | Default Claude posture could edit but not execute; runner-dependent (Codex unaffected) | **fixed** `72afb3c` |
| **F4** | **Nothing integrates.** Approved work stays on `agentweave/<agent>`; `master` has a README | **open, unowned by any roadmap entry** |
| **F5** | The approved document still says "no implementation exists" after 99 tests pass | **open** — B3 |
| **F6** | A question asked only in prose vanished (description/date on an expense) | **open** |
| **F7** | Retired identifiers forgotten one save later | **fixed** `9cb4a2f` |
| **F8** | Agent ack loops burn runs (one run existed only to say "Acknowledged") | **open** |
| **F9** | Rename moves the path but not the title | **open** |
| **F10** | Delivered tests pass normally, **fail 9 under `PYTHONIOENCODING=utf-8`**; both agents shared a machine so the review was structurally blind | **open** |

**F4 has now blocked two designs.** B3 had to decide whether a footprint on an unmerged branch counts
as evidence; B4 had to decide whether to gate on integration. Third appearance; strongest signal
about what deserves attention next.

## Key decisions

1. **Rename takes a *subject*, not a path.** The Hub slugifies. `validate_spec_path` is the only
   control stopping a write to an arbitrary location beneath `spec/`; a rename accepting a
   destination would put the least trusted caller behind that single guard. A traversal in the
   subject becomes an ordinary hyphenated name (`../../etc/passwd` → `spec/changes/etc-passwd/`),
   verified live.
2. **Placeholders are random and meaningless on purpose.** Rejected: deriving from the title or a
   counter — anything reproducible gets treated as identity within a week, and identity is
   `SpecDocument.id`.
3. **Do not commit `spec/` to the repo** (the operator's initial instinct). Worktrees are created
   from HEAD at first trigger, so an agent would see whatever was committed *then* — trading "spec
   absent" for "**spec silently stale**", which is worse because a stale spec looks authoritative.
4. **Inject the requirements a task is *bound to*, not the document.** Measured on the real
   document: **~286 tokens** for a three-requirement task versus **~1,500** for the whole thing —
   and the 286 does not grow with the product. Rejected navigation-only: this session proved twice
   that guidance an agent must *decide* to act on loses to whatever is already in front of it.
5. **F2 was narrowed after a test caught me.** My first cut made *every* new conversation inherit,
   which broke `test_agent_trigger_overrides` — `agent-conversation-workspace` requires a
   conversation the **operator** starts to begin clean. The test was right; the fix now covers only
   peer- and job-opened conversations, where nobody was at the composer to choose.
6. **`bypassPermissions` is never inherited.** Removing every check is a decision for a thread being
   watched; it must not reach runs the operator did not start.
7. **B4: `verified` means the same at every rigor** — accepted current-digest evidence. Rejected
   letting `contract` be satisfied by recorded-only evidence: promoting a document would then
   silently un-verify requirements, and a coverage count would mean different things on two
   documents in one project.
8. **B4: the gate fires on `approved`, not `completed`.** Evidence is accepted after review and
   review follows completion, so refusing `completed` would deadlock the path to the acceptance it
   blocks for.
9. **B4: an agent cannot change rigor in either direction.** A gate an agent can lower opens itself.
   Enforced by the absence of a route, as approval already is.

## Constraints and user directives (verbatim)

**From this session:**
- *"Test the whole process start to finish. Correct any bugs anything that is clearly broken. Take
  notes on anything that might be improved. Record the whole path"*
- *"It doesn't need to be a full product but at least one feature of it implemented."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet.
  (The user can implement them on their own but for the future we should make hook creation easier
  within the hub, but that's low priority)"*
- Evidence (B3 Q1): *"The evidence can be anything. Test running, screen shots, paths. What ever the
  model thinks it's necessary to show that his work is good."* … *"Should we have a place where all
  evidence will gather? A tree of folders with the evidence and let the user decide how to manage
  evidence retention. User can even chose never and deal with it in their own way."*
- B3 Q2: *"ship both now."* · B3 Q3: *"c"*
- B3 Q4: *"only test agents can accept the evidence. It's sort of a gate as well but the tester agent
  should be the one handling that. If no tester agent then all defers to the operator. Someone might
  want to develop without tester agents and he'll test and accept the bottleneck."*
- On the E2E skill: *"The skill will ask based on the current session (The things that it built) what
  is the full scope of the testing or if it's a fresh session the scope without nudging the user into
  what was built in the current session."*
- On skill autonomy: *"I won't be using to test just the spec creation. I may what to test different
  things. So stopping at operator gates might not make sense because I could be testing something
  else. So this will depend on the scope and user directives"*

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; **never mark a task
  complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **Running `git stash` while a 10-minute pytest run was in flight.** It silently invalidated the
  whole run — the suite was testing a tree I had just reverted. Had to rerun. Never stash during a
  background suite.
- **Assuming a test that contradicts your change is wrong.** `test_agent_trigger_overrides` failed on
  my F2 fix and I nearly overrode it; it was pinning a *shipped requirement*
  (`agent-conversation-workspace`) that a conversation the operator starts begins clean. Read the
  spec before overriding the test.
- **`replace` without checking for a second occurrence.** Two tests in
  `test_agent_default_permission_mode.py` had identical assertion blocks; a bulk replace changed
  both and broke the one that was correct.
- **Reporting a failure before isolating it.** I reported "the suite fails with 9 failures" when the
  failures were caused by an env var *I* had set (`PYTHONIOENCODING=utf-8`). The underlying finding
  (F10) was real, but the framing was wrong until isolated. Change one variable at a time.
- **A `while True` fallback in `mint_placeholder_path`** contradicted the spec I had just written
  ("bounded"). Caught by re-reading my own requirement.
- **Agent ack loops** — builder and reviewer message each other after every step, and each message
  is a scheduled run with real cost. Budget for it when driving multi-agent flows.
- **The e2e harness's `--perm` flag is essential** — without it a Claude builder cannot run tests
  (that was F3, now fixed, but the harness flag remains the way to choose a posture).

**Carried and still true:**
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`openspec` CLI rejects change names starting with a digit** — create and archive by hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`.**
- **`git commit -m @'…'@` is PowerShell syntax and the Bash tool is Git Bash.** Use a heredoc into
  `git commit -F -`.
- **`vitest` full-suite runs flake** on `chartersUi` / `runnersUi` with 5s per-test timeouts under
  load; both pass in isolation and at `HEAD`.

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1702 passed, 10 skipped** at `72afb3c`. Earlier gates: 1688 (rename),
  1693 (retirement fix).
- `pytest tests/ -q` — **360 passed, 3 skipped**.
- `npx tsc --noEmit` — clean. `npx vitest run` — **828 passed**, minus the two known flaky files.
- `ruff check hub/ src/` and `black` — clean on every file touched.
- `npx openspec validate --changes --strict` — **14 passed**; `--specs --strict` — 30 passed.
- **Live against the running Hub:** minted placeholders (`russet-thunderbird`, `indigo-salamander` —
  two identical titles, two distinct names); rename moved the file and pruned the old directory;
  refusals for `???`, an occupied name, and an approved document; `../../../etc/passwd` became
  `spec/changes/etc-passwd/spec.html`.
- **The E2E product, verified by me not by the agents:** 99 tests pass; settlement arithmetic
  recomputed by hand and correct; `balance`, `correct` audit trail and validation exercised directly.

**NOT run, and it matters:**
- **The running Hub does NOT have the F2/F3 fix.** It started at **15:40**, before `72afb3c`.
  Anything testing the new permission posture must restart it first.
- **No human verification of F2/F3.** Four checks in that change's tasks §4, including the one only
  the operator can make — see Open questions.
- **B3 and B4 are specified and entirely unimplemented.** No code, no migrations, no tests.
- **F10 was not fixed** — the delivered E2E product's tests still fail under UTF-8.

## Git state

Branch `hub-native-experience`, HEAD **`2afd868`**, working tree **clean**, **24 unpushed commits**
(12 from this session). `.claude/handoffs/` is tracked.

**Live environment:** Hub on `:8010`, **PID 4164**, started 15:40, health `ok` — **predates the
F2/F3 commit**. Find the real PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`.

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4` (`proj-477dab47`), and
**`aw-e2e` (`proj-471e281a`, at `C:\Users\huida\Documents\aw-e2e`)** — this session's end-to-end run,
with the built CLI on branch `agentweave/builder`. Kept deliberately; it is the only worked example
of the full loop and the fixture B3's migration tests should use.

## Next steps

1. **Restart the Hub onto `2afd868`** (WMI command in Dead ends), confirm health `ok`, then run the
   four human-only checks in
   `openspec/changes/2026-08-13-a-posture-that-survives-the-handoff/tasks.md` §4 — most importantly
   §4.4: watch one real build turn and judge whether what an agent now runs unattended is acceptable.
   **The posture is a path boundary, not a sandbox:** a command containing no absolute path is
   allowed, including `pip install` and network access.
2. **Implement B3 phase 1–2** (`openspec/changes/2026-08-13-a-requirement-knows-its-work/tasks.md`).
   Phase 2 alone answers "which requirements have no work?" and makes requirement injection
   possible. Start at task 1.1: add the `spec_requirements` model and migration `0066` (current head
   is `0065`).
3. **Decide who owns integration (F4).** It has now blocked two designs. Nothing in the A–B7 roadmap
   creates it.
4. Implement B4 after B3 phase 4.
5. Optional cleanups: F9 (rename does not update the title) is small and sits in code shipped today.

## Open questions for the user

1. **Does the wider execution surface need narrowing now, or does it wait for hooks?** The operator
   said hooks, and that they are unimplemented. Worth knowing whether the interim default is
   acceptable. Note the rule already recorded in
   `openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`: **no capability may exist
   only in a hook.**
2. **Who owns integration (F4)?** Blocking question 3 above.
3. Carried: should `.claude/handoffs/` stay tracked (**now 126 files including `LATEST.md`**)?

## Read on resume

- `openspec/explorations/2026-08-13-explore-to-development-end-to-end.md` — F1–F10 with evidence.
  The single most important file from this session.
- `openspec/changes/2026-08-13-a-requirement-knows-its-work/tasks.md` — B3, the next implementation.
  Its `proposal.md` carries the four decisions the operator made.
- `openspec/changes/2026-08-13-a-posture-that-survives-the-handoff/tasks.md` — §4 is what next step 1
  executes.
- `.claude/skills/e2e-loop/SKILL.md` — how to drive the loop again; encodes the method, not just the
  harness.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — where B3/B4 sit,
  and what remains (B5, B7).
- `hub/hub/mcp_server.py` `_decide` (~line 603) — what the workspace posture actually permits, which
  next step 1 asks the operator to judge.
