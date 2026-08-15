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
| **d1** | The ~40 human-only judgement calls. `2026-08-15-judgement-evidence.md` now holds the artefacts so you can answer them without re-driving the product. **This is what unblocks archiving 13 of the 14 in-flight changes.** `2026-08-15-triage.md` now confirms exactly which 13 — see below. |
| **d2** | `2026-07-30-hub-native-experience` has 69 open tasks and looks partly superseded. `2026-08-15-triage.md` now has a concrete proposal: don't resume the whole thing, don't archive it either — map section 14 to its successors (nobody has yet), then split what's genuinely still open in 13/14/15 into new change(s), then archive the umbrella. |
| **d3** | Carried: does an abandoned queue entry read as "the Hub gave up"? Do two exit codes on one event read as informative or noise? |
| **d4** | Carried: should `.claude/handoffs/` stay tracked, now 134 files? |
| **d5** | New: the spec flow's own review step caught a real conflict between two `MUST` requirements (FR-7 vs FR-9) in the test document. Worth a wording decision even though the document itself is throwaway — full text in `STATE.json`. |

---

## 15:23 — driver iteration: q6, first QoL fix (duplicate context-usage rows)

Picked up the branch and found a dirty tree: `hub/hub/api/v1/agents.py`,
`hub/hub/output_recording.py`, and `hub/tests/test_context_usage.py` had uncommitted changes with
no matching log entry or `STATE.json` note. Reconciling here rather than guessing: some earlier
iteration started a `q6` QoL fix and died (most likely a quota cutoff, per `quota_policy`) before
committing or logging. The change was complete and self-consistent, not a half-edit, so I verified
it properly rather than discarding it.

**The fix:** `record_context_usage` (`hub/hub/output_recording.py`) persisted and broadcast a new
`context_warning` row every time an agent posted a context-usage reading with a newer
`observed_at`, even when the measurement itself (tokens, percent, model, etc.) was identical to the
latest persisted row. The docstring/comment attached to the fix cites a real activity log that was
65% duplicate rows of an unchanged number this way — a genuine QoL friction (a noisy, padded
activity feed), consistent with `q6`'s instruction to prefer frictions actually observed over
invented ones. Fix: compare the new payload to the latest persisted one field-by-field (excluding
`observed_at`); if identical, still update freshness (so the checkpoint trigger still sees it) but
skip the persist+broadcast, and return `"unchanged"` (surfaced via the API as
`{"status": "ignored", "reason": "unchanged"}`, distinct from the existing `"reason": "stale"`).

**Verified, not just read:** confirmed the new regression test
(`test_repeated_unchanged_reading_does_not_duplicate_the_activity_log`) fails against the
pre-fix source (copied `HEAD`'s `output_recording.py`/`agents.py` back in, reran — `AssertionError:
'ok' != 'ignored'`) and passes against the fix. Ran the full `test_context_usage.py` (8 passed),
plus `test_context_usage_measurement.py`, `test_checkpoint_cutover.py`,
`test_agent_trigger_overrides.py`, `test_bola.py` (60 passed total) to catch anything downstream of
`record_context_usage` or the context-usage endpoint. All green.

Committed as its own commit. `q6` stays in flight — one fix per iteration per `next_action`'s
instruction; more frictions remain queued in `2026-08-15-spec-flow-findings.md`.

---

## 14:54 — driver iteration: q5, the 14-change triage

`q4` is fully closed (three defects, three regression tests) and the branch turned to `q5`:
triage the 14 in-flight `openspec` changes, one line each — archive, resume, or drop — into the new
`2026-08-15-triage.md`. Read every open task in every `tasks.md` in full (not just counted them),
same discipline `q1` established: a checkbox count is not evidence.

**Result: 13 of the 14 have nothing left for a loop to do.** Every open task in them is a human
judgement call (things like "is the placeholder pleasant?", "does the rename feel timely?") — code
is done, tests pass, and the only thing standing between them and the archive is you answering **d1**
in `2026-08-15-judgement-evidence.md`. One new gap surfaced while cross-checking: that file is
missing `the-spec-tool-reaches-the-agent` entirely — not answered, not even listed as pending. Flag
for whoever runs the next judgement-evidence session.

**One change, `2026-08-12-hub-owns-the-spec-document`, has two small non-judgement items** among its
8 open tasks: 12.3 (bind the spec charter by default) was *deliberately* left uncoded because the
obvious implementation makes "no charter bound" unreachable during spec work — it needs a decision
on `D9` before it needs a line of code. 16.8 (refusing event modification/deletion) is a documented
test-only gap: no code path offers either action, so there's nothing to fix, only an assertion of
absence to write.

**`2026-07-30-hub-native-experience` (the big one, 69 open of 188) got the close read its queue entry
asked for.** Its own `tasks.md` already carries five rounds of dated reconciliation notes written by
earlier work (2026-08-02 through 2026-08-12) — sections 9–12 are fully closed by successor changes
already sitting in `archive/`, left unchecked on purpose ("the reconciliation rule"). Section 13 is
mostly done, with three items (13.4 scope enforcement, 13.9 single-agent Team-block omission, 13.11
composition inspection) confirmed still genuinely missing from the tree. Section 14 is marked
superseded but — unlike 9–13 — nobody has ever mapped its 19 items one-by-one to whichever
2026-08-13 change actually delivered each; that mapping pass is the concrete next step before **d2**
can be decided. Section 15 (task-lifecycle approval gates in the composer) is confirmed genuinely
open — permission/question cards exist, task-lifecycle decisions still don't route through them.
Full detail and the `d2` proposal in `2026-08-15-triage.md`.

**No archiving was done this iteration** — `next_action` was explicit not to, pending your read of
`d1`/`d2`. Next queue item is `q6`, QoL improvements, once picked up.

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

**All three `q4` defects are now fixed.** Approving a task gave no signal when (a) a requirement it
serves has rejected evidence sitting under it — fixed 13:43 — or (b) the merge that approval promises
("approving is what merges it") was actually skipped — fixed 13:29. Both were silent successes that
should not have been silent. The third, (c), was a real duplication bug rather than a signal gap: a
task board task with the right `requirement_ids` did not satisfy `propose`'s completeness check —
only the document's own declared `tasks[]` did — so nothing stopped an operator or agent
hand-creating board tasks before approval and then getting a second, overlapping set minted on
approval, with nothing reconciling the two. Fixed this iteration — see below.

**One genuine bug found and fixed earlier**, in the change that exists to prevent exactly it: the
tool list told agents `submit_spec_document(path, document)`, a signature the tool has never had.

**Four things that looked like serious bugs were my own query errors** — written up as such in
`2026-08-15-spec-flow-findings.md` so nobody re-files them.

---

## 13:43 — driver iteration: approve's response stops being silent about rejected evidence

Picked up `q4` defect (1), the sibling to 13:29's merge-visibility fix and the one this branch's
`next_action` left a concrete starting point for: `PATCH`/`GET .../tasks/{id}` gave no indication
when a requirement a task serves has rejected evidence sitting under it, even though
`TaskResponse.requirement_links[]` already carried a `state` per requirement. That vocabulary
(`unserved`/`not_started`/`in_progress`/`evidence_awaiting_review`/`stale`/`drifting`/`verified`,
from `requirement_coverage.py`) has no value for "tried and rejected" — a requirement whose only
evidence was rejected falls through `_state()`'s precedence to `in_progress`, identical to one
nobody has ever attempted.

**Done**

- Added three fields per `requirement_links[]` entry in `hub/hub/api/v1/tasks.py`
  `_attach_requirements`: `has_rejected_evidence` (bool), `rejected_evidence_count`, and
  `latest_rejection_reason`. Populated by one batched query per page (same discipline as
  `_latest_integrations_by_task`): join `RequirementEvidence` (`review_state == 'rejected'`) to
  `EvidenceReview` (`decision == 'rejected'`, ordered newest first for the reason), filtered to
  evidence whose `digest` matches the requirement's *current* digest — same staleness discipline
  `requirement_coverage._state` already uses, so a rejection against a since-reworded requirement
  does not read as a live warning.
- Updated the `requirement_links` doc comment in `hub/hub/schemas/tasks.py` to name the new fields
  and the gap they close. `requirement_links` is `List[Any]` (dict-shaped), so no schema class
  changes were needed.
- New `hub/tests/test_task_rejected_evidence_signal.py`, three tests: a rejected current-digest
  evidence row is named on both `GET /tasks/{id}` and `GET /tasks`; a requirement nobody has
  attempted carries no rejection signal (`False`/`0`/`null`); a later *accepted* resubmission does
  not erase an earlier rejection's signal (coverage moves to `verified`, but the count still names
  the rejected attempt — the two facts are independent, same reasoning as `requirement_coverage`'s
  own doc comment on integration vs. state). **Verified the regression is real**: stashed the
  `tasks.py`/`schemas/tasks.py` changes, reran the three tests — all three failed with `KeyError`
  on the pre-fix code — then restored the fix and confirmed all three pass.
- Ran the full `-k "task or requirement or evidence"` slice of `hub/tests/` (449 tests) against the
  fix: all pass, no regressions. `ruff check` clean on all three touched/added files.
- Did not touch `requirement_gate.py`'s blocking behaviour — signal-only fix, same discipline as
  defect (2).

**Found while wrapping up**: `2026-08-15-spec-flow-findings.md` actually documents a *third* `q4`
defect that this branch's `STATE.json` had never carried into `next_action` or the queue — the
`propose`-completeness/board-task duplication bug (see the short version above, item (c)). Filed it
into `next_action` below so the next iteration picks it up rather than re-discovering it from the
findings file.

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
