# Autonomous run — 2026-08-29, decided fixes and a drive

**Branch:** `autonomous/2026-08-29-decided-fixes-and-drive` from `master` at `b2d565e`
**Runner:** `claude` (Opus 5) · **Posture:** `unattended-full-access`
**Armed:** 2026-08-29 ~12:35 local · **Stop at:** 2026-08-29 20:00 local
**Brief:** `.claude/autonomous/STATE.json` · **Findings:** `scripts/drive/FINDINGS.md`

Newest entry at the **bottom**.

---

## Iteration 0 — arming (interactive session, operator present then departing)

The operator's words: *"Schedule a autonomous run to fix those issues and then drive a e2e loop and
fix issues that you can. Run untill 20:00. After scheduling run a handoff in this session."*

### What "those issues" are, and why none of them needs a decision

Four findings, every one with the operator's own decision already behind it. The brief quotes each
decision at the queue item so the run implements rather than re-litigates:

| | Decision, in the operator's words |
|---|---|
| **F116** | New this session. Fix shape is the one the finding names; pre-authorised as D1. |
| **F111 + F3** | *"No it does not belong in the product."* Self-registration is removed, not reworded. |
| **F113** | *"Clean."* — `blocking` gets the closure finding; the additive alternative is rejected and recorded as rejected. |
| **F115** | *"Worktree is a cwd — fix the honesty."* Native mode does **not** confine writes. |

F115's decision was taken with `AskUserQuestion` in the last minute before the operator left,
specifically because it was the one thing that would have stalled the run.

### Limits set for this run

Beyond the standing directives (all quoted in `STATE.json.limits`), two matter most:

1. **Do not merge to master.** This session merged 34 commits to master today with the operator
   present and CI green on all nine cells. An unattended run pushes its branch and stops there.
2. **The 17:00 rule.** The operator asked for the fixes *and* a drive. If the queue has not reached
   `E2E-DRIVE` by 17:00 local, park the spec loop in flight at a clean boundary — a completed round,
   committed — and start the drive anyway. Reaching the drive is part of the ask.

### What was prepared so the run would not have to

- **The four findings are written up in full** in `FINDINGS.md`, each with its live reproduction:
  F115 has four run rows and the sqlite query that proves all four recorded the same
  `workspace_dir`; F116 has both request shapes and both responses; F113 has the three-call
  reproduction; F111 has the search that proves no shipped client calls the route.
- **A working drive harness exists** — `scripts/drive/t_row13_row14.py`, written and run this
  session, with the two traps documented in-file (the question schema has no `status` string, and
  permission posture travels in `overrides`). The run reuses it rather than rediscovering them.
- **Green-at-arming is CI, not a local run.** Run `33247142872` at `c994af5` passed all nine cells
  including both 3.12 legs, which cannot be reproduced on this machine. Everything committed since
  touches only `scripts/drive/*.md` and two new drive scripts no test imports.
- **The F109 flake is named in `known_flakes`** with its three affected tests, so a red cell there
  is re-run rather than misattributed — and with an explicit *do not re-propose the fix*, because
  the operator declined it today.

### Four pre-authorised defaults

So the run does not park on a question at 3pm: D1 (proceed with forbidding extras), D2 (drop the
`contact_mode` column only if nothing live reads it), D3 (**not** pre-authorised as a design — if
no honest detection point fires in *default* posture, ship F115's other three parts and write part
2 up as its own finding, because a detector that misses the case the finding is about reads as
coverage), D4 (the stray root files are gone; nothing to do).

### Driver

Windows Scheduled Task, not `ScheduleWakeup` and not `CronCreate` — both die with the interactive
session, measured 2026-08-15 when a nine-hour run got forty minutes. Each firing is a fresh
`claude -p` process that reads `STATE.json`, does one iteration, commits, pushes, exits.

### What a reviewer should distrust in this entry

Nothing was implemented at arming. The claim that the four decisions are settled rests on this
session's transcript, and the F115 decision in particular was taken in one question with the
operator on their way out — if the implementation surfaces a consequence the question did not
cover, that is the place to look first.

---

## Iteration 1 — F116-R1: explore and propose (13:01 local)

**Branch and log reconciled.** `STATE.json`'s `parent_sha` said `00fb5e5`; the branch was already
cut and sits three commits past it (`956ab07`, `8e1dd96`, `eaf68d0` — all arming bookkeeping). The
log header says "from master at `b2d565e`". Both are describing the same branch at different moments
of the arming session; nothing has diverged and `origin/master` is still at `b2d565e`. No `iteration`
or `last_heartbeat` field existed yet — iteration 1 added both.

**Delivered:** `openspec/changes/2026-08-29-an-unknown-field-is-named/` — proposal, design, tasks,
and a delta for a new `api-request-strictness` capability. `openspec validate --strict` passes.

### What round 1 measured rather than assumed

The queue item asked which other request models allow extras and whether the lax setting is a
default or a choice. Round 1 answered by walking the **running app's routes** — every `APIRoute`
with `POST`/`PUT`/`PATCH`, body annotation unwrapped to its `BaseModel` subclasses, `model_config`
read off each:

**36 forbid extras. 19 do not.** Nothing in `hub/hub/` sets `extra` to a lax value on a request
model. The only two non-default lax settings in the package are `config.py:21` (environment parsing)
and `spec_payload.py:68` (stored-payload parsing) — neither a request body.

The sharpest evidence that this is omission rather than policy: **`EvidenceRecord` exists twice with
an identical field list** — `agent_actions.py:826` forbids, `api/v1/spec.py:329` does not.
`EvidenceDecision` is the same pair. Inside `api/v1/spec.py` alone, eight models forbid and five do
not.

### The find that changes the shape of the fix

`hub/hub/schemas/spec.py:13`'s `SpecDocumentCreate` is lax **on purpose**, says so in its docstring,
and is backed by a requirement that shipped 2026-08-12:
`openspec/specs/agent-document-creation/spec.md:50-58` requires that an agent supplying a path is
answered by *minting one anyway* — "unexpressible rather than merely refused". A 422 mints nothing.

**A blanket sweep would breach a shipped requirement.** That is the round-3-shaped failure this
repository keeps producing, caught in round 1 only because the audit read docstrings instead of
counting models. So the rule proposed is not "every request model forbids extras" but "every request
model forbids extras **or says in the code why it does not**", with an enforcement test that carries
the exemption list.

### The answer to "one model or a shared base"

**Shared base** — `RequestModel` in `hub/hub/schemas/common.py`, plus a test that walks the routes.
Forbidding on `TriggerAgentRequest` alone leaves 18 of the 19 and does not touch F116's actual
complaint. `model_config = {"extra": "forbid"}` written 36 times has *already* failed as a
mechanism: it is invisible when absent, which is exactly how `TriggerAgentRequest` came to be lax
with 36 strict siblings in the tree. A base class is visible when absent and a test can see it.

### D1 resolved, and the breaking change stated

D1's `raise_it_if` was "the audit finds a request model where extras are load-bearing, or a shipped
client that relies on the tolerance". The audit found **one** load-bearing case —
`SpecDocumentCreate` — and it is exempted by name rather than swept. **No shipped client relies on
the tolerance**, verified caller by caller: `transport/http.py`'s log, heartbeat and session-sync
bodies carry declared fields only; the three UI `agent/trigger` call sites likewise; and
`http.py:161` already strips eight identity fields *because* most schemas forbid extras. Proceeding
under D1.

Two lax routes get **better**: `post_agent_output` already catches 400/422 and retries with a legacy
body, a fallback that today never fires against a lax Hub — so structure is silently dropped instead.

### Two hazards handed to round 2 rather than waved away

- `ContextUsageCreate.normalize_legacy` is `mode="before"` and rewrites legacy keys, so ordering
  *should* preserve it — but the design says to **prove that by running it**, not by reading
  pydantic's docs. If extras were checked first, every legacy context-usage body would start
  failing, and that is the one way this change breaks something quietly.
- Whether `api-request-strictness` deserves its own capability document. The delta directory is the
  expensive thing to move after a sync, so round 2 decides it before implementation.

### What a reviewer should distrust in this entry

The counts. 36/19 is the entire argument, and round 1 produced them from one script run in one
process. Task 1.1 exists to make round 2 re-derive them independently rather than read this table —
if the population differs, the proposal is wrong before anything else is checked.

Nothing was implemented. No test was written or run; F116 is still open and still reproducible.
