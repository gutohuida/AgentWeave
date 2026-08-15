# Catch-up — 2026-08-15 run

**Read this first.** Newest entry at the top. Every iteration appends here before it commits, so
this stays current even if an iteration dies on a quota limit.

Run window: **12:21 → 22:00 BST**, branch `autonomous/2026-08-15-spec-flow-hardening`, cut from
`hub-native-experience` at `a40ac5b`.

Operator's intent, verbatim: *"I want to finish the integration with the spec. I want the spec/dev
flow in agentweave to be strong and working. Find all the bugs, correct them, find improvements,
frictions and work on them."*

---

## Needs your decision

Nothing blocks the loop. These are yours whenever you get to them — full text in `STATE.json`
under `decisions_for_user`.

| | question |
|---|---|
| **d1** | The ~40 human-only judgement calls. `2026-08-15-judgement-evidence.md` now holds the artefacts so you can answer them without re-driving the product. **This is what unblocks archiving 13 of the 14 in-flight changes.** |
| **d2** | `2026-07-30-hub-native-experience` has 69 open tasks and looks partly superseded. Drop, split, or resume? |
| **d3** | Carried: does an abandoned queue entry read as "the Hub gave up"? Do two exit codes on one event read as informative or noise? |
| **d4** | Carried: should `.claude/handoffs/` stay tracked, now 134 files? |
| **d5** | New: the spec flow's own review step caught a real conflict between two `MUST` requirements (FR-7 vs FR-9) in the test document. Worth a wording decision even though the document itself is throwaway — full text in `STATE.json`. |

---

## The short version so far

**The whole spec flow has now been driven end to end, for the first time, and it works** — with two
real defects found along the way. Interview → document → propose → approve → task → build →
`record_evidence` → `verifier` accept/reject → task approve → merge → reachable-from-`main`, all
exercised for real against a live `notify-window` codebase. `verifier` rejected one of six evidence
rows with a genuinely correct catch: a conflict between two `MUST` requirements in the same document
(**d5**, above). The merge silently skipped once (no `main_branch` configured) and then genuinely
landed on `master`, verified independently with plain `git log`/`git branch --contains` outside the
Hub entirely.

**Two UX gaps filed for the fix queue**: approving a task gives no signal when (a) a requirement it
serves has rejected evidence sitting under it, or (b) the merge that approval promises ("approving is
what merges it") was actually skipped. Both are silent successes that should not be silent — full
detail and the file/line to start from are in `STATE.json`'s `next_action`.

**One genuine bug found and fixed earlier**, in the change that exists to prevent exactly it: the
tool list told agents `submit_spec_document(path, document)`, a signature the tool has never had.

**Four things that looked like serious bugs were my own query errors** — written up as such in
`2026-08-15-spec-flow-findings.md` so nobody re-files them.

---

## 13:29 — driver iteration: approve's response stops being silent about the merge

Picked up `q4`'s first filed defect (2): approving a task ("approving is what merges it") gave no
signal in the PATCH/GET response about whether the merge actually happened — only a separate
`GET /tasks/{id}/integrations` call showed that.

**Done**

- Added `TaskIntegrationSummary` (`outcome`, `reason`, `commit_sha`, `target_branch`, `created_at`)
  and a `latest_integration: Optional[TaskIntegrationSummary]` field on `TaskResponse`
  (`hub/hub/schemas/tasks.py`).
- Populated it in `hub/hub/api/v1/tasks.py` for `GET /tasks`, `GET /tasks/{id}`, and the PATCH
  transition response (`update_task_for_actor`) via a new batched `_latest_integrations_by_task`
  helper (same shape as the existing `_latest_heartbeats_by_agent`). Left `create_task_for_actor`
  alone — a just-created task cannot have an integration row, by construction (entry statuses only).
- Three new regression tests in `hub/tests/test_task_integration.py`: a merge is echoed onto the
  approve response and onto plain `GET`, a skip (no `main_branch` configured) is echoed too, and a
  never-approved task reads `null` rather than an invented skip. **Verified the regression is real**
  by stashing the fix and re-running just these three — all three fail with `KeyError:
  'latest_integration'` on the old code, confirming they test something that did not exist before.
  Un-stashed and they pass again.
- Full `hub/tests/` filtered to `-k task` (283 tests, the load-bearing surface for this change) and
  the whole of `test_task_integration.py`, `test_tasks.py`, `test_task_transitions.py`,
  `test_task_transition_service.py`, `test_requirement_gate.py`, `test_requirement_coverage.py`,
  `test_mcp_server.py`, `test_mcp_body_contract.py`, `test_mcp_tool_schemas.py`,
  `test_tool_surface_matches_server.py`, `test_spec_declared_tasks.py`,
  `test_task_spec_document_context.py` — all green, no regressions. `ruff check` clean on both
  edited files.
- Deliberately left the Hub UI untouched — the queue entry scoped this to the API response and a
  regression test, not a rendered surface. If the operator wants the merge outcome visible on a task
  card, that is a small follow-up, not implied by this fix.

**Found while investigating item (1)** (the sibling defect — approve gives no signal when a
requirement's evidence was *rejected*, at rigor below `gate`): `TaskResponse.requirement_links[]`
already carries a `state` per requirement (`hub/hub/api/v1/tasks.py` `_attach_requirements`, backed
by `SpecRequirement.state` / `requirement_coverage.py`), but that vocabulary has no value for
"evidence was rejected" — only `unserved`, `not_started`, `in_progress`, `evidence_awaiting_review`,
`stale`, `drifting`, `verified`. A requirement whose only evidence was rejected reads identically to
one that was never attempted (`in_progress`), which is the actual gap item (1) names. The review
state itself (`accepted`/`awaiting`/`rejected`) lives on `RequirementEvidence.review_state`
(`hub/hub/db/models.py` ~1883, `hub/hub/requirement_evidence.py` ~54-56), one join away from
`requirement_links`, and is not surfaced anywhere on the task response today. This is the concrete
starting point for item (1) — see `next_action`.

**Next**: item (1) — surface, per requirement in `requirement_links`, whether it has rejected
evidence sitting under it (distinct from never-attempted), likely as an added field per link (e.g.
`has_rejected_evidence` or a small nested summary) populated from the same batched query
`_attach_requirements` already runs, joined against `RequirementEvidence` filtered to
`review_state == 'rejected'` for the requirement's current digest. Needs its own fail-before/
pass-after regression test using the existing `test_task_integration.py` or a sibling
`test_requirement_gate.py`-style fixture. Do not touch `requirement_gate.py`'s blocking behaviour —
this is a signal-only fix, same as (2) was.

---

## 12:59 — driver iteration: propose → merge → reachable-from-main, proven

Picked up a `builder` run (`run-84f3535c`) the previous driver iteration had correctly left in
flight and had not yet seen finish — committed its uncommitted findings text first (the tree was
dirty, but the content was real, not abandoned work).

**Done**

- Triggered `verifier` (`run-16b86c08`, ~4 min) to review the 6 pieces of evidence `builder` had
  recorded. 5 accepted, 1 rejected with real reasoning — see d5.
- Moved the task `completed` → `under_review` → `approved`. Approved instantly despite the
  rejection: the document is at the default `rigor: sketch`, which the approval gate deliberately
  does not block on — confirmed in `hub/hub/requirement_gate.py`, not a bug, but the operator gets
  no signal either way (filed).
- First merge attempt silently skipped (`aw-loop10` had no `main_branch` set). Set it to `master`
  via `PUT /projects/{id}/settings`, retried the integration, and it genuinely merged — verified
  independently with `git log`/`git branch --contains` directly in
  `C:\Users\huida\Documents\aw-loop10`, outside the Hub. Evidence footprints flipped to
  `reachable_from_main: true` automatically.
- Added `hub/agentweave.db` (the recurring stray 0-byte file named in seven prior handoffs) and
  `.claude/autonomous/scratch/` (API request/response scratch, not durable output) to `.gitignore`
  so they stop showing up as uncommitted state every iteration.
- Refreshed `last_heartbeat` from PowerShell mid-iteration (not Git Bash — see `dead_ends`) so a
  concurrent driver firing does not take over the branch.

**Found** — both filed for the fix queue, both "silent success that shouldn't be silent," neither a
gate-logic bug:

- `approve`'s response carries no signal when a requirement it serves has rejected evidence, at any
  rigor below `gate`.
- `approve`'s response carries no signal about whether the merge it triggers actually happened —
  only a separate `GET /tasks/{id}/integrations` call shows that.

**Next**: pick up the merge-signal fix first (more contained), then the evidence-signal one. Full
detail in `STATE.json`'s `next_action`. `task-0d3c8cb5` and `task-553c2c37` (the other two tasks
this document produced) are still `pending` if more coverage of the same document is ever wanted,
but the core untested claim is now closed.

---

## 12:21 — handover from the interactive session

**Done**

- `/loop-prep` run properly: intent interviewed *before* reading the handoff, so the queue is not
  an echo of last session's. Environment measured, not assumed — the Hub had been running since
  00:40 and was one real commit stale, so it was restarted onto current code.
- **Driver stand-down guard** (`a40ac5b`). You chose session + backup driver; nothing stopped the
  two colliding on one branch. A firing now skips when `last_heartbeat` is under 25 minutes old.
  Verified five ways with a stubbed `claude`, then **verified for real** at 11:52:35.
- **`submit_spec_document` fixed** (`95f8fa4`). Two new tests compare every described argument
  against the real schema; mutation-checked. 18 of 19 tool entries were already correct.
  `the-tool-list-matches-the-tools` went from 6 done / 17 open to **22 / 4**.
- **Spec flow driven live** in a fresh project `aw-loop10` (`f31e90e`). Run 1 interviewed you in
  prose and wrote nothing — which is *correct*, per `SPEC_PHASE_DUTIES`. Run 2, after your answers,
  called `submit_spec_document` and wrote the document. Total cost $0.74.
- Full suites measured **both sides**: hub 631+686+712 → 631+686+**714**, CLI 360 both. This also
  settles handoff 0047's outstanding "full suite not run since `55bfadb`".
- Handoff `0048` written and chained to `0047`.

**Found**

- The activity log is **65% duplicate `context_warning` rows** — 15 of 23 events, the same
  measurement repeated up to four times in two seconds. Real friction, filed for the QoL phase.
- `POST /projects/create` correctly refuses an existing directory but does not name `/open` as the
  alternative.
- The minted spec directory name is 66 characters, and kept the agent's *first* phrasing while the
  document title was later refined to something better. Path and title now disagree in quality.

**Nearly went wrong**

Git Bash `date` on this machine prints UTC while labelling it `+0100`. The handover heartbeat was
therefore stamped an hour in the future; the driver would have computed a negative age, concluded a
live session held the branch, and stood down until ~13:31 — losing roughly seventy minutes of the
run you asked for. Caught by cross-checking against PowerShell, fixed, and recorded in `dead_ends`.

**Next**

Take the document through propose → approve → tasks → build → `record_evidence` → accept →
approve → merge, and confirm the work is genuinely reachable from main.
