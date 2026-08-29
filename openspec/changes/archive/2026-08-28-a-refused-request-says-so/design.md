# Design — A refused request says so

## D1. The edit is at the route, not in `turn_scheduler`

F108's own text proposes "making `turn_scheduler` propagate non-transient refusals". It already
does. `ScheduleResult.terminal_failure` has existed since F56 and is set from the error's own
classification at `turn_scheduler.py:229`; `scheduler.py:2446` and `:2585` both read it and mark the
job run `failed`. The operator's HTTP route is the only caller that ignores it.

Recording this because the finding is right and its mechanism is wrong, and following the mechanism
would have produced a change that edits a working component and leaves the broken one alone. Same
shape as F107, whose finding proposed carrying `params` onto `tool_input` when the code already did
and the data was elsewhere.

## D2. Presence of a refusal object, not reinterpretation of `terminal_failure`

The naive route-side test — `if scheduled.terminal_failure: raise` — is wrong, because
`terminal_failure` **defaults to `True`** (`turn_scheduler.py:33`) and **six early-return sites,
carrying five distinct reasons**, take the default without meaning it: `"queue is empty"` (`:70`),
`"hop budget exhausted"` (`:73` **and** `:108` — two sites, one sentence), `"queued entry has no
conversation"` (`:77`), `"conversation is unavailable"` (`:85`), `"token budget exhausted"`
(`:115`). Only `"agent is already running"` (`:66`) passes `terminal_failure=False` explicitly.

**Round 2 correction to round 1's evidence.** Round 1 argued this from `"queue is empty"` being
"genuinely reachable" after the route's own commit. Re-derived from the code, that is *reachable
but only as a race*, and narrower than round 1 implied: `schedule_agent` holds a per-agent
`asyncio.Lock` (`_lock_for`, `:59`), so a concurrent `redrain_queued_agents` cannot interleave with
this call — it must complete first. If it delivered this entry it also created a `Run`, and the
route's own call then hits the `Run.status == "running"` check at `:65` and returns *"agent is
already running"* with `terminal_failure=False`. For `"queue is empty"` to be what the route sees,
that run must also have **finished** inside the window. Real, but a race.

The argument does not need it. What makes D2 correct is **construction, not reachability**: the
refusal carrier is written in exactly one place, so no early return can produce one, whatever the
defaults happen to say. Round 1 reached the right design through an argument weaker than the design
itself — recorded here because this repository's stated failure mode is an argument that is wrong
about something that is right.

So `ScheduleResult` gains an optional `refusal` field, populated **only** in the
`except TriggerAgentError` branch and **only** when the error says its refusal is about the request
(D10 — round 1 wrote "non-transient" here, which is too wide). Its presence is the classification.
No early return can set it, so the defaulted-`True` trap cannot fire — by construction rather than
by a list of exclusions that the next early return would have to be added to.

`terminal_failure` is left exactly as it is. Rewriting the defaults would change what
`scheduler.py`'s two flow consumers do, and this change has driven none of that.

## D3. A refusal is attributed to entries, and the route refuses only for its own

`schedule_agent` picks the conversation of the **oldest eligible entry across the agent's whole
queue**. The route's own comment at `:1276` says so, and the success path already handles the
mismatch — when the scheduler started a run for a different conversation, the route does not return
that run, it says *"an older conversation's queued input is being delivered first"*.

The refusal path never got the same treatment, so today a refusal raised while building a turn for
**another** conversation is reported to this caller as its own `waiting_reason`. That is a second
defect, unfiled, found by this exploration.

The refusal object therefore carries the ids of the entries it applies to — `selected`, which the
refusal branch already iterates at `turn_scheduler.py:151` to stamp `entry.waiting_reason`. The
route refuses only when its own entry id is among them. One field answers both F108 and the
mis-attribution, because they are the same question asked twice: *is this refusal about my input?*

## D4. The status code comes from the error, not from the route

`TriggerAgentError` already carries the status the condition deserves — 403 for the author-as-own
-reviewer case, 409 for a task in the wrong state, 501 for an unimplemented runner. The refusal
object carries it out unchanged. The route inventing a single code would flatten distinctions the
Hub has already made correctly, and would diverge from what F76's pre-queue guards return for the
same conditions.

## D5. The entry does not stay in the queue after the operator has been told

A request-level refusal (D10) is one that no amount of waiting and no change to the environment
makes deliverable, because what is wrong is what was asked. Retrying it is pointless by
construction — F108's own observation, that the request "retries until the abandonment counter
gives up", is the waste being removed.

**Round 2 narrowed this.** Round 1 wrote `transient=False` here, which would have withdrawn the
entry for *environment-level* refusals too — and that is precisely the entry F96 proved must
survive (`test_runner_binding_redrain.py`: bind the runner, the queued entry is delivered). See
D10.

Once this request answers with an error, its entry is withdrawn with a reason naming the refusal, so
the synchronous answer and the queue agree. Without this the operator gets an error *and* the entry
works behind their back, and a `queue_entry_abandoned` event arrives minutes later for a request
that already reported failure.

Scoped to the entry this request created, and only on the path that returns the error. The general
question — whether a non-transient refusal should consume all three attempts for *any* caller —
belongs to the flow path too, which this change has not driven. Filed, not smuggled in.

`schedule_agent` has already incremented `delivery_attempts` and may itself have withdrawn the entry
at the limit, so this step is idempotent: it must tolerate an entry already `withdrawn`.

## D6. A foreign refusal stops being reported as this request's reason

When a refusal exists but names other entries, the route reports that this input is queued behind
another conversation's, mirroring the success path's existing treatment. It does not repeat the
foreign detail, which describes a conversation the caller did not ask about and cannot act on.

## D7. The operator must not end up worse informed, so the UI is in scope

Two of the three UI call sites discard the server's message on a non-2xx:
`AgentOutputPanel.tsx:672` throws `Trigger failed with status <n>`; `NewConversationSurface.tsx:108`
sets `Could not start the conversation`. `api/tasks.ts` is already fine — `fetchWithAuth` throws
`ApiError(status, text)`, which preserves the detail.

Shipping the server change alone would trade a *misleading but informative* message for an
*accurate but useless* one. The operator today at least reads why the turn did not start. Both
sites render the server's sentence.

## D8. What this change must not disturb

- **The flow path.** `scheduler.py:2446` and `:2585` keep reading `terminal_failure` unchanged.
- **F76's three route guards** at `:1214`. They run *before* the entry is queued (`:1257`), so they
  refuse with no queue residue at all — strictly better than propagating after the fact. They stay
  authoritative; this change is the backstop for conditions that cannot be hoisted ahead of the
  queue write.
- **`transient` classification.** Read, never redefined.

## D9. Blast radius on the suite

`waiting_reason` appears 35 times across 13 hub test files. The conditions F108 names each have a
test that asserts today's `200` — `test_archived_send_refusal.py`,
`test_a_decided_task_takes_no_new_work.py`, `test_project_workspace_unavailable.py` among them.
Those assertions change deliberately, and **R2 must enumerate them before implementation** rather
than discovering them as failures: a test that flips from `200` to `409` without anyone deciding it
should is how a behaviour change hides inside a green suite.

## D10. The gate is *request-level*, not *non-transient* — round 2's finding

Round 1 gated the refusal on `not transient`. Round 2 read every `TriggerAgentError` raise site
(25 of them, in `agent_trigger.py`) and every existing test that asserts today's `200`, and that
gate is **too wide**. `transient` answers one question — *does this clear on its own, so should a
delivery attempt be counted?* The route is asking a different one — *will this input ever be
delivered?* — and the non-transient population splits in two:

| | Examples | What the product does today, deliberately |
|---|---|---|
| **Environment-level** | no runner bound (`:461`), the bound runner's CLI is not on PATH (`:507`), the bound runner row is gone (`:480`), the worktree could not be prepared (`:756`), the canonical context could not be written (`:817`) | Queues the entry and states the remedy, **so that performing the remedy delivers it** |
| **Request-level** | the agent is not in this project (`:452`), the agent is archived (`:474`), the runner has no adapter (`:499`), the review target is in the wrong status (`:626`) / already under review (`:643`) / authored by the reviewer (`:657`) / has nothing to review (`:670`), an invalid `work_dir` (`:684`), a turn batching two reviews (`:337`) or mixing kinds (`:351`) | Nothing about the environment changing makes the answer different |

Both columns are `transient=False`. Round 1's gate would have refused the first column and, via D5,
**withdrawn its entry** — reversing two shipped decisions that have tests naming them:

- `test_agent_trigger.py::test_unbound_agent_accumulates_queue_with_visible_reason`, whose docstring
  states the behaviour as a decision: *"it queues with a stated reason **rather than failing the
  request outright**"*.
- **F96** (`test_runner_binding_redrain.py`) exists solely so that binding a runner delivers the
  entry queued while none was bound. Withdrawing that entry deletes the finding's own fix.
- `test_runtime_diagnostics.py::test_agent_trigger_reports_missing_cli_directly` asserts
  `200 … "not found in PATH"` for the same reason.

And F108's own four examples — an archived agent, a task that does not exist, an unimplemented
runner, a `work_dir` the project does not contain — are **all** in the second column. The finding
never asked for the first.

**So the classification is asked directly, the way `transient` already is.** `TriggerAgentError`
gains a second, independent flag meaning *this refusal is about the request, not the environment*,
defaulting to `False`. The two flags answer two different questions and are not opposites: a
refusal may be neither, and none may be both.

Defaulting to `False` is what makes D9's blast radius small and deliberate rather than large and
discovered: **no existing test changes unless a raise site is explicitly marked.** The behaviour
change is then exactly the set of sites this change decides to mark — the list in `tasks.md`
group 2 — and nothing else.

## D11. The route's entry object is stale by the time the refusal comes back

`async_session_factory` is built with **`expire_on_commit=False`** (`hub/hub/db/engine.py:40`), and
`schedule_agent` opens a session of its own (`turn_scheduler.py:59`) rather than reusing the
route's. So when the refusal branch stamps `waiting_reason`, increments `delivery_attempts`, and
possibly sets `state = "withdrawn"` at the attempt limit, **none of it is visible on the route's
in-memory `entry`** — which still reads `state="queued"`, `delivery_attempts=0`.

This is load-bearing for D5's idempotence (`tasks.md` 4.2). A route that tolerates an
already-withdrawn entry by reading `entry.state` will read `"queued"` in production every time,
while passing any test whose fake scheduler shares the route's session. That is this repository's
named failure mode — a check that is tested, correct, and cannot fire — so the implementation
refreshes the row (`await session.refresh(entry)`) before deciding, and a test asserts the refresh
by having the scheduler withdraw through a genuinely separate session.

## D12. Round 3: the withdrawal has to be announced, or the operator sees both answers

Round 3 followed D5 out to the UI. The route commits its entry at `:1260` and **broadcasts
`queue_entry_queued`** at `:1268-1269` before it ever calls `schedule_agent`. So by the time the
refusal comes back, every connected client has already been told the input is queued and has
invalidated its queue query on the strength of it (`useSSE.ts:489-493`).

Withdraw the row without saying so and the operator gets an error dialog *and* a queue card reading
`waiting_count: 1` for an entry that no longer exists — the two halves of the product disagreeing,
which is the same complaint F108 makes, moved one surface over.

The event to send already exists and the UI already handles it: **`queue_entry_withdrawn`**, emitted
today only by the operator's explicit `DELETE` on a queue entry (`api/v1/inbound_queue.py:271-272`)
and switched on in `useSSE.ts:491`. The refusal path emits the same kind with the same payload
shape. Nothing new is invented, and no client changes.

Deliberately **not** `queue_entry_abandoned`: that one means *the Hub gave up after trying*, it
carries an attempt count and a run id, and `useSSE` gives it its own operator-visible treatment
(`:440`). This entry was never delivered and nobody gave up on it — the request it belonged to was
answered.

## D13. Round 3: two of round 2's marked sites cannot be reached, and one changes F96-shaped behaviour

Round 2's marking list (`tasks.md` 2.0) was itself unreviewed. Round 3 re-derived it.

**`:474` (the agent is archived) is unreachable through the queue, and should be marked anyway.**
`agent_lifecycle.archivable` refuses to archive an agent that has queued entries
(`agent_lifecycle.py:46-59`), and the route refuses an archived agent pre-queue at `:1108`. Between
them, no entry can be sitting in the queue for an agent that is archived by the time
`schedule_agent` runs. Marking it costs nothing and is honest about intent — but **no test may
claim to exercise it through the route**, because such a test would have to construct a state the
product forbids, and would then be green for a reason unrelated to what it claims. `:499` and `:874`
(unimplemented runner) are the same: `Runner.cli` is schema-constrained to `claude`/`codex`, so
neither is reachable through the API at all.

**`:452` (the agent is not in this project) genuinely changes behaviour of the F96 shape, and that
is the decision.** There is no redrain when an agent is *created*; there is one when a runner is
*bound* (`agents.py:2026`). So today, an operator who triggers a mistyped name, then creates that
agent and binds it a runner, has their original input delivered. Refusing at the route ends that.

It is still right, and the distinction from F96 is not "how hard the repair is" but **whether the
input has an addressee**:

- *No runner is bound* — the agent exists, the operator's intent is unambiguous, the input is for
  **that** agent, and the Hub is holding it for a component the operator is about to attach.
- *No such agent* — the input is addressed to a string. The Hub cannot tell a typo from an agent the
  operator is about to create, and the failure mode of guessing is the worse one: an agent created
  later that happens to reuse the name receives input meant for something else entirely, exactly
  the name-reuse hazard `:474`'s own comment already cites from D15.

The raise site's wording leads with the same reading — *"Create it in the Hub UI, **or correct the
name**"* — and its measured example is a scheduled job repeating the mistake every five minutes.
Recorded here as a deliberate reversal rather than left to be discovered.

## D14. Round 3: the delta must say the withdrawn input names no run

`agent-conversation-workspace` already requires (*Repeated delivery failure does not wedge an
agent*) that "an input the system has given up on SHALL still name the run that was carrying it, so
the operator can find what happened to their message."

Nothing carried this input. `schedule_agent`'s refusal branch already says so in its own comment —
*"No `Run` was ever created for this attempt"* (`turn_scheduler.py:182`) — and already broadcasts
`run_id: None` for the abandonment it does at the attempt limit (`:208`). So the shipped code
already sits outside that sentence for every refusal raised before a spawn; this change does not
create the gap, it walks into it.

**No contradiction, and the delta says so explicitly** rather than leaving a reader to reconcile
them. The existing requirement governs *returned* input — input a run carried and gave back — and
its attempt limit is a **ceiling on retries, not a floor**: "stop retrying it before it can block an
agent indefinitely". Withdrawing at the first request-level refusal is inside that ceiling, not
against it. The one clause that reads as a floor — "Returning an input to the queue SHALL cause the
system to attempt its delivery again without requiring any further operator action" — is scoped to
input that was returned, and this input was never delivered to return.

## Filed, not fixed here

1. **`terminal_failure`'s defaults are dishonest.** Five early returns claim `True` without meaning
   it, and `scheduler.py`'s two consumers gate on it — so a job run may be being marked `failed`
   today because a re-drain won a race against `"queue is empty"`. Candidate defect, own change.
2. **A non-transient refusal consumes three delivery attempts on every path.** D5 fixes it only for
   the entry whose request is answering with an error.
