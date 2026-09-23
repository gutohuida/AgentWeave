# Test guide — an unstaffed review names its holders

**Re-derived 2026-09-23 (task 6.5), against the shipped `_rung_3_reason`** (`hub/hub/scheduler.py`).
The OPERATOR QUESTION is closed — option (f), reachability, `spec-queue/DECISIONS.md`'s `F352-free`
row — and this guide describes what actually shipped against it, not option (e).

## Agent-verifiable (run by IMPL and DRIVE)

| # | check | how |
|---|---|---|
| A1 | The rung-3 reason takes one of five clauses per roster agent, in precedence order — excluded, no runner, held (waiting for a usage-limit reset), booked (reachable holdings only), running — and names every agent that fits the 500-character bound before falling back to a tail count | `test_rung_3_reason_is_this_exact_string_for_a_completed_task`/`..._under_review_task`, tasks 2.6–2.9b's fixtures, the drive's `review_unstaffed` event |
| A2 | A booked clause names only *reachable* holdings (a live loop or a queued turn) — an agent whose only tasks are unreachable takes the **running** clause, not booked, and is staffed by rung 2 on the next firing rather than named in a rung-3 reason | Task 2.6's fixture (`test_a_loopengine_shaped_firing_names_every_reachable_holder`); drive 6.3(a) |
| A3 | The reason never suggests archiving a loop to free an agent — that remedy was removed (R6-3); it appends "Rejecting booked tasks that are no longer wanted can free their agents" only when at least one named clause is `booked` | `test_the_rung_3_reason_never_claims_archiving_a_loop_frees_an_agent`, `test_the_rung_3_reason_does_not_reject_when_nobody_booked_is_named`; drive 6.3(b) |
| A4 | Over the 500-character bound, the reason retries a booked clause at 3, then 2, then 1 named task before dropping that agent (and everyone after it, in name order) to the tail; a held agent left to the tail still gets its own tail wording | `test_twelve_booked_agents_still_fit_the_500_character_bound`, `test_a_thirty_two_character_name_still_fits_sixty_four_character_ids` |
| A5 | The history route survives a long reason produced by rung-3's own clause construction | `GET /api/v1/projects/<p>/jobs/<job>/history` → 200 on the drive Hub (6.3) |
| A6 | The board's stall `<p>` carries the full, unstripped reason in its `title` attribute, even once the visible text is truncated on screen | `loopsIndexTab.test.tsx`'s title-attribute test; drive 6.3 (Chromium, `get_attribute('title')`) |
| A7 | Who is free did not change **by this directory's own tasks** — it changed by (f), shipped separately (`4b59ee0`) | The existing ladder, width and busy-guard suites, unchanged and green; `test_a_task_nothing_will_move_holds_nobody.py`'s R5 guard |

## Human-only (for the operator, on their own Hub after a restart)

These need judgement, not an assertion. **Note:** the UI bundle carrying A6's title attribute was
built and driven (group 5, iteration 15) but not shipped to `:8000` — it ships once that process
restarts past `c18a87b`, the operator's call. Items 1 and 3 need that restart to observe on the
operator's own Hub; item 2 does not depend on it.

1. **Does the stall line tell you what to do?** Open *Loops*. On a flow with a finished task and
   every other agent holding work, read the amber line, then hover it. *Expect:* the first words
   name agents and what they hold. The hover (or, until the bundle ships, the `title` attribute)
   shows the whole sentence, ending with an action you can take. *Judge:* could you unblock a stuck
   flow from this sentence alone, without asking an agent?
2. **Is Land it the right thing to be told?** Open a completed task still held by its author, and
   choose `under_review` in the status menu. *Expect:* a refusal naming **Land it**, which sits in
   the same drawer. *Judge:* is "Land it" what you would want to be pointed at, knowing it approves
   without an agent review, or refuses and names the evidence still unjudged? Or should the product
   also offer a way to hand the review to a specific agent (F336)?
3. **Is the sentence too long?** With four or more agents it can still run to several hundred
   characters even after the 500-character budget walk shortens or drops booked clauses.
   *Judge:* is naming every free-checkable agent worth the length, now that unreachable holdings no
   longer pad it, or should the tail summarize more aggressively?

## Not covered by this change

- **An agent reassigning a task over HTTP** (F366). Noted, not changed. The agent's refusal is
  worded so it does not depend on the answer.
- **The drawer's status-menu refusal text and a real agent's `under_review` refusal turn**
  (originally drafted as A3–A5 here) — these drive D5's refusals, which moved with the split to
  `a-refusal-names-a-remedy-that-works/test-guide.md` (archived 2026-09-16) and are not this
  change's to re-verify.
