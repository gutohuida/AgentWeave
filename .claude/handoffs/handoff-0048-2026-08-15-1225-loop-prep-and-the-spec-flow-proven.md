# Handoff: loop-prep run for real, and the spec flow's authoring half finally observed

**Date:** 2026-08-15T12:25+01:00 · **Branch:** `autonomous/2026-08-15-spec-flow-hardening` ·
**HEAD:** `f31e90e`+ (see git state)
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0047-2026-08-15-1119-driver-proven-six-archived-two-skills.md`
**Status:** interactive session handing over to the unattended driver, which runs until **22:00**.
Tree clean apart from the usual stray `hub/agentweave.db`. Nothing half-done.

## Goal

The operator ran `/loop-prep` and then left, asking the loop to run until 22:00 and to leave
handoffs, resumes and a catch-up file behind. Their intent, verbatim:

> *"I want to finish the integration with the spec. I want the spec/dev flow in agentweave to be
> strong and working. Find all the bugs, correct them, find improvements, frictions and work on
> them."*

## Current state

### What prep found that changed the plan

The spec cluster is **built, not half-built**. Checking code rather than `tasks.md` showed the
change with the worst ratio — `the-tool-list-matches-the-tools`, 6 done / 17 open — was already
implemented and green. The real blocker across all 14 in-flight changes is that ~40 open tasks are
**operator judgement calls**, which a loop structurally cannot tick. That is why nothing can be
archived, and it is what `q3` exists to unblock.

### Shipped this session

1. **A stand-down guard on the driver** (`a40ac5b`). The operator chose session + backup driver, but
   nothing stopped them colliding — the task fires on its interval regardless. A firing now skips if
   `last_heartbeat` is under 25 minutes old, and deliberately does **not** unregister, since
   standing down is a skip not a stop. Every failure mode defaults to proceeding. Verified against
   the real script with `claude` stubbed, five cases; then **verified in production** at 11:52:35,
   which stood down against a 0.6-minute-old heartbeat.
2. **`submit_spec_document` described with the arguments it actually takes** (`95f8fa4`). The
   surface said `(path, document)`; the tool has never had a `document` parameter. Two new tests
   compare described arguments against the real schema; mutation-checked. **18 of 19 entries were
   correct — this was the only drift, and it was the same tool that already cost a completed
   interview.**
3. **The spec flow's authoring half proven** (`f31e90e`), for the first time ever — see below.
4. **`STATE.json` seeded** with 9 queue items, 13 limits, 4 open decisions, environment and dead
   ends, from an interview rather than from the last handoff.

### The milestone: an agent wrote a specification

`2026-08-12-hub-owns-the-spec-document` 17.6 and `the-tool-list-matches-the-tools` 5.1 both record
that nobody had ever watched an agent call `submit_spec_document`. In `aw-loop10`:

| | run 1 `run-d3b6f7c5` | run 2 `run-462fb78e` |
|---|---|---|
| duration / cost | 72s / $0.27 | 140s / $0.47 |
| outcome | interviewed in prose, wrote nothing | **wrote the document** |

Run 1 writing nothing was **correct** — `SPEC_PHASE_DUTIES` says interview in your reply, not
through a tool. Run 2, after the operator answered, minted 8 requirements into a 23KB document that
raised two open questions nobody asked, one of which genuinely contradicts a requirement it had
just written. Full detail in `.claude/autonomous/2026-08-15-spec-flow-findings.md`.

### Suites, measured on both sides

Before: hub 631 + 686 + 712 passed / 11 skipped across three chunks; CLI 360 passed, 3 skipped.
After: hub 631 + 686 + **714**; CLI 360. This also settles handoff 0047's outstanding *"the full
suite has not been run since `55bfadb`"*.

## Files touched

| path | what |
|---|---|
| `.claude/skills/autonomous-session/scripts/run-iteration.ps1` | heartbeat stand-down guard. Finished, verified in production. |
| `hub/hub/api/v1/agents.py` | `submit_spec_document` entry corrected; `SpecKind` imported for its `Literal` values. Finished. |
| `hub/tests/test_tool_surface_matches_server.py` | `_described_signatures()`, `_schemas()`, and two argument-agreement tests. Finished. |
| `openspec/changes/2026-08-13-the-tool-list-matches-the-tools/tasks.md` | 6 done / 17 open → **22 / 4**; only §5 human-only remains. |
| `.claude/autonomous/STATE.json` | the loop's brief. Live — the driver rewrites it every iteration. |
| `.claude/autonomous/2026-08-15-spec-flow-findings.md` | what driving the flow showed. |
| `.claude/autonomous/2026-08-15-judgement-evidence.md` | artefacts for the human-only tasks. |

## Key decisions

1. **Prep interviewed intent before reading the handoff.** A brief built from what was last shipped
   proposes more of the same. The operator's answer redirected the whole run away from handoff
   0047's recommended queue (L9-2 exploration).
2. **The driver stands down rather than unregisters** when a live session holds the branch. Rejected
   unregistering: the session being backed up may die at any moment, and the next firing is what
   picks the work up.
3. **Every heartbeat failure mode defaults to running.** A backup that defers to a file it cannot
   read is no backup.
4. **`q3` created as a queue item that did not exist before.** The ~40 judgement calls are the
   actual blocker; capturing their artefacts converts a permanent stall into one 20-minute sitting.
5. **A fresh project rather than reusing loop 9.** First-run friction can only be seen once.
6. **Four suspected defects written up as non-defects.** An empty conversation, a roster with no run
   attached, mojibake, and statement-less requirements were all my own query errors. Recorded so
   they are not re-filed — three of them would have looked like serious bugs to anyone reading the
   output without opening the endpoint.

## Constraints and user directives (verbatim)

**From this session:**
- *"I want to finish the integration with the spec… Find all the bugs, correct them, find
  improvements, frictions and work on them."*
- *"It will run until 14h"* — then, on leaving: *"Run the loop until 10PM. Don't need to keep this
  session open if this is going to be a problem. Still follow what we defined. Don't forget handoffs
  and resumes and also the final file so I can catchup on everything that happened. With this
  intensive use you might run into quota limits. If this happens program a restart for the next
  window."*
- *"No new features just QoL improvements"* — for the improvements phase.
- On the market research: *"Be honest about it. My intention is not to drop agentweave but we can
  always evolve it and pivot it like we did from previous versions to this one."*
- *"Open as many aw-loop test you would like."*
- Limits: **"Standard limits only."**

**Carried and still binding:** the `ci.yml` question is settled (*"just push the branch"*) — do not
raise it. Every `tasks.md` splits agent-verifiable from human-only and emits a user test guide. G5
is a non-goal. Requeue is *"any failed run, capped at 3"*. Derive constants, do not tune them.
Evidence can be anything the model thinks shows its work is good; only test agents accept it, else
it defers to the operator. Narrowing command execution is hook work. Never `.agentweave/`,
`agentweave.yml` or `spec/` at the repo root; openspec, never aw-spec. Stage paths explicitly and
never suppress stderr on staging. Never mark a task complete on the strength of a plan existing.
Commit each checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**

- **Git Bash `date` prints UTC but labels it `+0100`** — an hour earlier than real local time. A
  heartbeat stamped from it lands in the *future*, the driver computes a negative age and stands
  down until real time catches up. This nearly cost ~70 minutes of the run. **Stamp
  `last_heartbeat` from PowerShell or Python, never from Git Bash.**
- **The chat endpoint returns `entries`, not `messages`.** Parsing for `messages` returns empty and
  looks exactly like a run that left no trace.
- **The agent roster has no `last_run_id`.** Printing one shows `None` and reads as a detached run.
- **The spec `requirements` index returns no `statement`** — by design; statements come from
  `read_spec_document`.
- **Spec routes are `/projects/{id}/project/spec/…`** — singular inside plural, because `spec.py`'s
  router carries its own `/project` prefix. Not a bug; do not "fix" it.
- **`POST /projects/create` refuses an existing directory** — use `/open`. The message is correct
  but does not name the alternative.
- **`printf '%s'` and bash single quotes both eat backslashes** in Windows-path JSON. Build the
  body with Python and post it with `-d @file`.

**Re-confirmed:** keep `.ps1` ASCII-only; `pytest hub/tests/` needs three file chunks; start the Hub
detached via `Win32_Process.Create`; event rows are in `event_logs`, payload column `data`; the Hub
API key is in `hub/.env`.

## Verification

**Ran, with real output:**
- Full suite both sides of the change — figures above. All green.
- `ruff check hub/ src/` clean; `black --check` on both touched files unchanged.
- The 173 tests touching the tool surface or spec context — passed.
- **Mutation checks on both new tests:** restoring `(path, document)` fails them with the phantom
  `document` and the missing `kind`/`title`, while all five pre-existing tests still pass.
- **The driver guard, five cases** against the real script with `claude` stubbed, **plus a
  production stand-down** at 11:52:35.
- `npx openspec validate --specs --strict` 30 passed; `--changes --strict` 14 passed.
- The Hub was restarted onto current code first — it had been one commit stale since 00:40.

**NOT run, and it matters:**
- **The propose → approve → build → evidence → merge half has not been touched.** The document sits
  in `exploring`. This is now the longest-standing untested claim in the product.
- `npx vitest run` and `npx tsc --noEmit` — no UI source changed.
- Loop 9's approve→merge half, still unexercised.
- `/loop-prep` itself has now been exercised once — this session. `/autonomous-session` Step 1 still
  has not been.

## Git state

Branch `autonomous/2026-08-15-spec-flow-hardening`, cut fresh from `hub-native-experience` at
`a40ac5b` and pushed. Commits: `dccb711` seed, `95f8fa4` tool surface, `f31e90e` spec-flow records,
plus the heartbeat correction. Working tree clean except `?? hub/agentweave.db`.

**Live environment:** Hub on `:8010`, restarted 11:46:56 onto current code. `AgentWeaveAutonomousSession`
Scheduled Task **registered**, firing every 15 min, `StopAt 2026-08-15T22:00:00`, `MultipleInstances=IgnoreNew`,
`ExecutionTimeLimit=PT2H`.

**Projects:** `aw-loop10` (`proj-ff695d96`) added at `C:\Users\huida\Documents\aw-loop10`, with
`speccer`/`builder` (claude) and `verifier` (codex, holds `can_accept_evidence`). Keep
`aw-loop6`–`aw-loop9` as before.

## Next steps

1. **Take the document through propose → approve → tasks → build → evidence → accept → merge.**
   This is `q2`'s remaining half and the product's central untested claim.
2. **Keep `2026-08-15-overnight-catchup.md` current every iteration** — the operator asked for it by
   name, and an iteration that dies on quota must still leave it readable.
3. `q5` triage, `q6` QoL (the `context_warning` flood is the first candidate), `q7` the honest
   market read.

## Open questions for the user

Live in `STATE.json` under `decisions_for_user`: the ~40 judgement calls themselves (`d1`), whether
`hub-native-experience`'s 69 open tasks are dropped/split/resumed (`d2`), the two carried surface
questions (`d3`), and whether `.claude/handoffs/` stays tracked at 134 files (`d4`).

## Read on resume

- `.claude/autonomous/STATE.json` — the loop's position. Read this **first**.
- `.claude/autonomous/2026-08-15-overnight-catchup.md` — what happened, newest first.
- `.claude/autonomous/2026-08-15-spec-flow-findings.md` — including the four non-defects.
- `.claude/autonomous/2026-08-15-judgement-evidence.md` — the artefacts awaiting the operator.
