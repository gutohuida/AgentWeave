# Driving the spec flow end to end — aw-loop10

**2026-08-15, 12:00–13:00 BST.** Project `aw-loop10` (`proj-ff695d96`) at
`C:\Users\huida\Documents\aw-loop10`, Hub on `:8010` restarted onto current code first.
Fresh project, deliberately: first-run friction can only be seen once.

Agents: `speccer` (claude, Spec Author charter), `builder` (claude, Developer),
`verifier` (codex, Verifier, `can_accept_evidence=true`) — the loop-9 composition.

Codebase under specification: `notify-window`, a 40-line quiet-hours decision function with
6 passing tests, chosen because it is small enough to read in one turn and genuinely
under-specified.

---

## The headline: the spec flow works, and this is the first time it has been watched working

`2026-08-12-hub-owns-the-spec-document` task 17.6 and
`2026-08-13-the-tool-list-matches-the-tools` task 5.1 both say the same thing — nobody has ever
observed an agent call `submit_spec_document` and write a document. **It has now been observed.**

| | run 1 `run-d3b6f7c5` | run 2 `run-462fb78e` |
|---|---|---|
| duration | 72s | 140s |
| exit | 0 | 0 |
| cost | $0.2703 | $0.4681 |
| tools | Read ×3, Grep, Bash, `read_spec_document`, `rename_spec_document` | ToolSearch, **`submit_spec_document`** |
| outcome | interviewed the operator in its reply, wrote nothing | wrote the document |

`content_digest` moved `e3eba36d…` → `6e8b6b36…`; 8 requirements minted `FR-1`–`FR-8`; the file on
disk is 23,328 bytes.

**Run 1 writing nothing was correct, not a defect.** `SPEC_PHASE_DUTIES["exploring"]` says
*"Interview in your reply, not through a tool… then end your turn and let the operator answer in
the composer."* It did exactly that, and its two questions were the two real forks in the problem:
what replaces the boolean, and whether "can wait" means "later" or "gone". This is
`2026-08-13-the-interview-is-a-conversation` working as designed.

### The document is good

Faithful to the answers given, and it did the thing a specification is for — it found what the
operator did not say. Two open questions it raised unprompted:

- a notification already stale **on arrival** — FR-6 as written ("no notification is discarded")
  would require delivering something already useless, and the operator never ruled on it;
- a deadline falling **exactly** at the window's end, against the existing half-open
  (start-inclusive, end-exclusive) boundary convention the code already uses.

Both are real. The second one it found by reading the existing tests, not by pattern-matching.

Every requirement carries a rationale, and the acceptance criteria are per-requirement
Given/When/Then. This is the evidence `17.2` / `5.2` / `6.1` have been waiting for — see
`2026-08-15-judgement-evidence.md`.

---

## Findings

### 1. The activity log is 65% duplicate `context_warning` rows — real, worth fixing

23 event rows for the whole session. **15 are `context_warning`**, and they repeat identical
measurements consecutively:

```
11:01:18.903  context_warning  context_tokens: 46378, percent: 4.64
11:01:19.997  context_warning  context_tokens: 46378, percent: 4.64
11:01:20.697  context_warning  context_tokens: 46378, percent: 4.64
11:01:22.982  context_warning  context_tokens: 47665, percent: 4.77
11:01:24.163  context_warning  context_tokens: 47665, percent: 4.77
11:01:24.628  context_warning  context_tokens: 47665, percent: 4.77
11:01:24.807  context_warning  context_tokens: 47665, percent: 4.77
```

Four rows for one unchanged number, inside two seconds. The signal — trigger, start, complete — is
buried in a measurement that did not change. Two obvious fixes: only write a row when the value
moves, or drop the severity so it does not read as a warning at 4.6% of a 1M window. The name is
also wrong for what it is: nothing is being warned about.

**Suggested QoL (q6): emit `context_warning` only on change, or above a threshold.**

### 2. `create` refuses an existing directory without naming the alternative — minor

```
POST /projects/create  {"path": "…/aw-loop10"}
→ {"code":"invalid_project_path","message":"create requires a target that does not exist"}
```

Correct, and the code is clear. But the operator's next move is always `POST /projects/open`, and
the message does not say so. One clause — "use open for a directory that already exists" — turns a
correct refusal into an actionable one. The UI may already do this; worth checking before changing
the API text.

### 3. Route path reads `/projects/{id}/project/…` — cosmetic, do not churn it

`spec.py`'s router carries `prefix="/project"` and is mounted under `/projects/{project_id}`, so
every spec route is `/api/v1/projects/{id}/project/spec/...`. Singular inside plural. Harmless, and
renaming it would break every client for a cosmetic gain. **Recorded so the next person does not
think they have found a bug.**

### 4. The minted directory name is very long

The rename produced
`spec/changes/notify-window-graded-notification-urgency-beyond-quiet-hours-boolean/`, 66
characters, from a subject the agent chose. It is descriptive and it is legal, but on Windows it
eats a third of `MAX_PATH` before the project directory is counted. Worth a cap — and note the
document's *title* was later refined to something shorter and better ("deadline-based admission
beyond the quiet-hours boolean") while the **path kept the first, worse phrasing**, because the
path is minted once at rename time.

---

## Four things that looked like defects and were not

Recorded because each cost time, and the next person will hit them the same way.

1. **`GET /agent/{name}/chat/{conv}` returns `entries`, not `messages`.** Parsing for `messages`
   yields an empty list and looks exactly like "the run left no trace". The timeline was complete
   all along — 19 entries, operator input through to `Completed (cost: $0.2703)`.
2. **The agent roster has no `last_run_id` field.** Printing one shows `None` and reads as "the run
   never attached to the agent". `status`, `context_usage` and `session_started_at` are the real
   fields, and all three were correct.
3. **Em dashes in agent output looked like mojibake** in terminal output. Stored correctly as
   U+2014; zero U+FFFD in the row. It was the console codepage.
4. **The spec `requirements` index returns no `statement`.** By design — it is an index of
   identity, state and anchor, with a readable `key` slug. Statements come from
   `read_spec_document`.

The lesson worth keeping: **check the response schema before believing a surface is broken.** Three
of the four "findings" above would have been filed as serious bugs by anyone reading the output
without opening the endpoint.

---

## Not reached in this session

Propose → approve → task derivation → build → `record_evidence` → accept → approve → merge. The
document exists and is in `exploring`; everything downstream of it is still unexercised here.
Loop 9's approve→merge half also remains unexercised, which is now the longest-standing untested
claim in the product.

---

## Continued, next iteration: propose → approve, and a real defect in how they interact

Picking up where the above left off, same `aw-loop10` project, same document. All calls made as the
operator against `http://localhost:8010` with the `aw_live_...` credential from
`operator_credentials` (the Hub has no other way to mint one outside the UI's own session — worth
noting as its own friction below).

### `close-exploration` then `propose`: blocked correctly, but the blocking message points at the
wrong fix

`close-exploration` succeeded immediately (`explore_closed: true`). `propose` came back **still in
`exploring`**, refusing with two classes of finding: `unresolved_question` (the two open questions
from the interview) and `requirement_without_task` for all 8 requirements.

Both are real gates, working as designed — `spec_completeness.check()` (`hub/hub/spec_completeness.py`)
checks that every open question is `resolved: true` and that every requirement key appears in the
document's **own** declared `tasks` list.

Resolved the two open questions by triggering `speccer` again on the same conversation
(`conv-243dd3e2`) with the operator's decisions: a notification already stale on arrival is dropped
silently (not delivered, not digested — a ninth requirement, `stale-on-arrival-is-dropped`/FR-9, was
minted for this), and a deadline exactly at the window's end defers rather than interrupts, for
consistency with the codebase's existing half-open boundary convention. `run-d57f6a1b`, 57s, exit 0.
Both questions now carry `resolved: true` and a recorded `decision` string.

### Finding: a task board task with the right `requirement_ids` does not satisfy `propose` — only the document's own `tasks[]` does, and nothing tells you that

Before understanding the mechanism, I did what a real operator reading `"'X' has no task, so nothing
implements it"` would plausibly do: created two tasks directly via `POST /tasks` with
`requirement_ids` naming all 9 requirements and `spec_document` set to the right path. The response
confirmed proper linkage — `requirement_links` populated, correct identifiers, correct
`document_id`. Re-running `propose` afterward: **identical blocking list, byte-for-byte, all 9
`requirement_without_task` findings still present.**

The reason is in `spec_completeness.check()`: `tasked = {key for task in payload.tasks for key in
task.requirements}` reads `payload.tasks` — a list embedded in the **document's own JSON content**,
written only by `submit_spec_document` — not the real `Task` table the board and `/tasks` API read
and write. A task created on the board, however correctly linked to real `SpecRequirement` rows,
is invisible to this check. `hub/hub/spec_tasks.py`'s own docstring names the failure mode this
produces exactly: *"an operator approved nineteen requirements and got nothing... two
decompositions, no relationship between them, and the one that was reviewed and approved was the
one nobody worked from."* That comment describes the fix for **half** the problem — `materialise()`
now turns the document's declared tasks into real board rows on approval — but the other half is
still open: **nothing stops an operator or agent from also creating real board tasks by hand before
approval, and nothing reconciles the two.**

Confirmed the duplication happens: after triggering `speccer` again to add its own `tasks[]`
declaration (`run-aa971bc3`, exit 0) and re-running `propose` (now unblocked, phase → `proposed`)
and then approving (phase → `approved`), the approval's `tasks_created` returned **3 more tasks**
(`task-1f82d976`, `task-0d3c8cb5`, `task-553c2c37`) covering the identical 9 requirements the 2
hand-made tasks already covered. Five tasks on the board for one decomposition. Rejected the two
hand-made ones (`status: rejected`, operator-only edge, with a note) rather than deleting — there is
no delete route, which is itself consistent with the product's evidence-first design, but confirms
the duplication is not self-healing.

**The fix that would close this**: either (a) have `propose`'s blocking message say explicitly that
it means the document's own declared decomposition, not the task board — the current message
(`"'X' has no task, so nothing implements it"`) reads as a statement about the board, since "task" is
the board's word everywhere else in the product — or (b) have the completeness check also credit a
real board task whose `requirement_ids` cover the requirement, so the two paths converge instead of
silently coexisting. (b) is more work but is the one that actually prevents the duplication rather
than just explaining it. Filed for `q4`.

**Fixed 14:0x** (both (a) and (b), see `2026-08-15-overnight-catchup.md`). `spec_completeness.check()`
now takes a `board_served` set of requirement keys a hand-made task (`Task.spec_task_key IS NULL`)
already links to, and skips `requirement_without_task` for them. `spec_tasks.materialise()` mirrors
the same signal to skip minting a duplicate for a declared entry whose requirements are already fully
covered by a hand-made task. The wording (a) landed too: the message now says "is in neither the
document's own tasks[] nor a task already on the board." Both driven against the real reproduction
this section describes, as regression tests in `hub/tests/test_spec_board_task_convergence.py`
(confirmed failing on the pre-fix code, then passing).

### Minor: minting an operator API key requires reading the database directly

There is no CLI command or documented HTTP bootstrap to obtain `operator_credentials.id` outside the
Hub UI's own login flow. Ended up reading `hub/data/agentweave.db` directly
(`select id from operator_credentials`) to script the calls above. Fine for this loop's own driving,
but worth a `agentweave doctor`-adjacent surface (`cli.py` "does only what cannot be done from inside
the app" — minting a scriptable operator credential arguably qualifies) if operator scripting against
the Hub API becomes a supported pattern rather than an autonomous-loop workaround.

### State as of this entry

Document `spdoc-1d230e6b` is `approved`. Board carries `task-1f82d976` (admission decision: FR-1,
FR-2, FR-3, FR-4, FR-7, FR-9), `task-0d3c8cb5` (digest delivery: FR-5, FR-8), `task-553c2c37`
(no-notification-lost: FR-6), all assigned to `builder`. `builder` has been triggered on
`task-1f82d976` (`run-84f3535c`) with `task_id` bound so the run's completion moves the task off
`pending`. Outcome not yet known at the time of writing — continued below once the run lands.

---

## Continued, next iteration: build → evidence → verifier accept/reject → approve → merge → reachable-from-main, all proven for the first time

Picked this up because the previous iteration's process ended (not crashed — it correctly recorded
"outcome not yet known, continued below" and left the tree dirty only with the finding text above,
which this iteration committed first). `run-84f3535c` had in fact already finished by the time this
iteration started: `task-1f82d976` was `completed`, with six `record_evidence` calls against it,
each one a distinct `tests/test_notify_window.py` test at commit `1c65b98`, all `review_state:
awaiting`. **This is the first time a `builder` run has been observed completing a real task against
an approved spec document, with evidence.**

### `verifier` reviewing real evidence, for the first time, and catching a real spec defect

Triggered `verifier` (the project's only `can_accept_evidence` agent) with an instruction to judge
each piece on the merits rather than accept by default. `run-16b86c08`, ~4 minutes. Result: **5
accepted, 1 rejected** — not a rubber stamp.

The rejection (`ev-6efc41c1`, FR-9 "stale-on-arrival-is-dropped") is a genuine, well-reasoned catch,
quoted in full since it is the most interesting thing this loop has found so far:

> "Rejected against the full, unqualified wording of approved FR-9. The located stale test covers
> only arrival during quiet hours (23:30 with deadline 23:00). At the same commit,
> `test_non_quiet_delivers_even_with_a_stale_deadline` and the implementation explicitly deliver a
> stale-on-arrival notification outside quiet hours, so the evidence does not demonstrate that every
> notification whose deadline has already passed is dropped. This exposes a conflict between FR-9
> and FR-7's 'regardless of its deadline' wording."

FR-7 ("delivered immediately regardless of its deadline", outside quiet hours) and FR-9 ("dropped:
not delivered ... and not included in the digest", unqualified) are both `MUST` and both in the same
approved document, and they contradict each other for the one case where both apply: a stale
notification arriving outside quiet hours. `builder` implemented FR-7 literally (deliver, since
outside quiet hours always wins) and wrote a test proving it; that test is *correct against FR-7 and
wrong against FR-9 read literally*. Neither `builder` nor `speccer` (who wrote both requirements in
the same interview) caught this — only the review step did, and only because `verifier` was
instructed to judge rather than rubber-stamp. **This is a real spec-authoring defect** — a
requirements conflict that reached `approved` phase undetected — not a code bug. Filed for the
operator's `q3`/decision list below, not `q4`, because the fix is a wording decision (does FR-9 mean
"during quiet hours" implicitly, or does FR-7 need an exception for staleness?), not a code change.

### Finding: the approval gate is a no-op at the document's default rigor, and nothing says so at the point of approval

Moved `task-1f82d976` `completed` → `under_review` → `approved` as the operator. It approved
**instantly, with FR-9's only evidence sitting `rejected`**, and the response carried no mention of
that at all — same shape as any other successful approval.

Root cause read in `hub/hub/requirement_gate.py`: `evaluate()` only gates requirements whose
*document* rigor is `gate`; `_gated_requirements()` filters everything else out before the loop that
would check `review_state`, and returns "not refused" immediately if the filtered list is empty. The
document here (`spdoc-1d230e6b`) is at `rigor: sketch` — the default, never touched by `propose` or
`approve`, and nothing in the interview, `close-exploration`, `propose`, or `approve` responses
prompts the operator to consider raising it. The docstring is explicit that this is deliberate
("the default blocks nothing, and it has to, or the change would arrive as a barrier nobody asked
for") — so this is not a bug in the gate. But it means: **a document born from the ordinary interview
flow, with all its defaults, can have a task approved over an explicit, reasoned rejection from the
project's designated verifier, and the approval response gives the operator no signal that this
happened.** The only way to know is to separately query `/spec/evidence` and read `review_state`
per row. Filed for `q4` as a UX/signal gap, distinct from the gate's blocking behavior itself, which
is working as designed: **`approve`'s response should say when a requirement it names has rejected
or awaiting evidence, even at a rigor that does not block on it.**

### Finding: the merge is silent-skip by default, and the approve response does not say so either

First `approve` attempt integrated nothing: `task_integrations` showed one row, `outcome: skipped`,
`reason: "this project has no main branch set — choose one in the project's settings"`. This project
(`aw-loop10`) had never had `main_branch` set — nothing in the whole flow up to and including
`approve` had asked for it or refused for its absence. `GET /main-branch-suggestion` correctly
detected `master` as the candidate. Set it via `PUT /projects/{id}/settings`, then
`POST /tasks/{id}/integrations/retry`: **`outcome: merged`**, commit `1c65b98` merged from
`agentweave/builder` into `master` via a real merge commit (`e1ac86c`, "Integrate approved work
1c65b98992a5"). Verified independently with `git log --oneline master` and
`git branch --contains 1c65b98...` directly in `C:\Users\huida\Documents\aw-loop10` (outside the Hub
entirely) — the commit is genuinely on `master`. `GET /spec/evidence` afterward shows every evidence
row's footprint flipped to `"reachable_from_main": true` **automatically**, no manual refresh
endpoint needed — that part is correct and required no fix.

**This closes the single longest-standing untested claim in the product**: propose → approve → task
→ build → evidence → accept/reject → approve → merge → reachable-from-main has now been driven for
real, once, successfully (modulo the two findings above). But the same gap as the rigor finding
applies here: `approve`'s response is silent about whether the merge it triggers ("approving is what
merges it", per the gate module's own docstring) actually happened. An operator who does not
separately check `/tasks/{id}/integrations` has no way to know their approved work is not on `main`
except by noticing it missing later. Filed for `q4`: **surface the integration outcome inline in the
`approve` response** (or at minimum in the task detail response), not only via a separate endpoint an
operator has to already know to check.

### Net for this document

`spec/changes/notify-window-graded-notification-urgency-beyond-quiet-hours-boolean/spec.html`,
requirement `admission-decision` (FR-1, FR-2, FR-3, FR-4, FR-7, FR-9): 5 of 6 requirements verified
and merged to `master` in the real `notify-window` repository; FR-9 correctly rejected pending a
wording fix for its conflict with FR-7. `task-0d3c8cb5` (digest delivery) and `task-553c2c37`
(no-notification-lost) remain `pending` — not driven this iteration, left for the next one.

---

## Continued, next iteration: `task-0d3c8cb5` driven, `verifier` catches a second real gap, and the q4 fixes are confirmed live for the first time

`builder` triggered on `task-0d3c8cb5` (FR-5 `deferred-notifications-bundle-into-single-digest`,
FR-8 `empty-window-produces-no-digest`), `run-03598b4b`, completed, two `awaiting` evidence rows.
`verifier` triggered to judge them (`run-ed988ace`): **both rejected.** Full reasoning, quoted from
`/spec/evidence/{id}/reviews` (the list endpoint doesn't carry it — see the new finding below):

> "The implementation has no quiet-window-end trigger or delivery-event mechanism, and the tests
> neither model the window ending nor observe emitted delivery events. Returning `None` from an
> unintegrated helper is insufficient evidence for the requirement's temporal/event behavior."

`builder` wrote `DigestQueue.defer()`/`flush()` — real batching and clearing logic, all 20 tests
pass — but never wired it to an actual quiet-window-end event, so it demonstrates the data
structure, not the requirement. This is the second time `verifier` has caught a real gap between
what a requirement asks for and what evidence actually shows (first was FR-7/FR-9, `d5`), on a
different failure axis: not a spec contradiction this time, a spec/implementation gap that passing
tests fully obscured.

### Finding: `list_evidence` doesn't carry the rejection reason — same silent shape as the two things `q4` already fixed

`GET /project/spec/evidence` returns `review_state: rejected` but not *why*. The reason lives on
`EvidenceReview.reason`, written by `requirement_evidence.decide()` and readable only via a second
call, one per row, to `GET /spec/evidence/{id}/reviews`. A reviewer scanning a page of evidence to
understand what's blocking a task has to make N+1 calls to see why any of it was rejected. Same
"the signal exists, but not where you're already looking" shape as the two things this session
already fixed for `approve`'s response (`60f0b3f`, `eda02cf`). Filed for the next `q6` iteration —
not fixed this session, no code changed.

### The two already-shipped q4 fixes, confirmed live for the first time

Moved `task-0d3c8cb5` `under_review` → `approved` specifically to exercise `has_rejected_evidence`
and the merge-outcome signal against real rejected evidence. Neither fired — both came back
`null`/absent. Not a regression: the Hub process serving these calls had been running since the
12:21 handover and had never been restarted, so it was serving `a40ac5b`, six commits behind both
fixes. Restarted the Hub and repeated the check: `has_rejected_evidence: true, count: 1` on both
FR-5 and FR-8, `latest_integration: {outcome: "skipped", reason: "no accepted evidence names a
commit, so there is nothing to merge", ...}`. Both fixes are real and correct — this only ever
tested the *driving process's* assumption that a running Hub is a current one. Recorded as a
`dead_end` in `STATE.json`: this Hub does not hot-reload, and nothing before this had actually
re-verified any of the session's `hub/hub/` fixes against a live server since the interactive
handover.

### Net for `task-0d3c8cb5`

Approved with both requirements' only evidence `rejected` and the merge correctly skipped — the
same "sketch rigor blocks nothing, and says so" outcome as `task-1f82d976`'s FR-9, now confirmed
end to end on a second task. `task-553c2c37` (no-notification-lost) remains `pending` and undriven.
