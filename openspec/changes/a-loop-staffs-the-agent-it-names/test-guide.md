# Test guide — a loop staffs the agent it names

Covers groups 0–4, 6 and 7 (built and driven, `831ac16`/`adca56b`, `D-4, 2026-09-20`). Group 5
(what the operator is told — the wording of the 409/board sentences) was **moved out of this change
on 2026-09-21 by operator decision, to F400** (`scripts/drive/FINDINGS.md`); its checks belong to
F400's own change, not here.

## Agent-verifiable (run by IMPL and DRIVE)

| # | check | how |
|---|---|---|
| 1 | A documentless loop naming a busy agent, with siblings free, is refused (409) rather than silently substituted | `hub/tests/test_a_loop_staffs_the_agent_it_names.py` (groups 1–3); live: `scripts/drive/d7_0920_alsn_drive.py`, `D-4` |
| 2 | The same shape on a flow (spec-linked loop) still starts, on whichever roster agent is free | Task 3.x flow-width tests; live: `D-4`'s flow-control half, 200, both tasks moved |
| 3 | Staffing a loop's own named agent is not confused with resuming a sibling's in-flight work | Group 2 tests (D6, R2-2) |
| 4 | The busy guard's pool check and `decide_firing`'s fresh-work draw both read the same scope function, not two independently-maintained lists | Task 0.1 grep assertion (`_agents_a_loop_may_staff`, two call sites) |
| 5 | The F70 exception (`test_a_loops_wedged_review_still_recovers`) and the `run_divergence` silent-reviewer path are untouched by the scope filter | Group 4 tests (D5) |
| 6 | Full regression set unaffected: `test_a_loop_does_not_staff_its_own_review.py`, `test_loop_busy_guard.py`, `test_flow_width.py`, `test_actor_aware_claimability.py` | Group 6, 54 → 64 passed |
| 7 | `openspec validate a-loop-staffs-the-agent-it-names --strict` passes | Run directly |

## Human-only (for the operator, on their own Hub, once F400 ships)

These depend on wording that does not exist yet — do not judge them against today's text:

1. **Does the 409 tell you what actually happened?** Press Run on a documentless loop pinned to a
   busy agent with siblings idle. Today's sentence still reads F127's text (*"no other agent is
   free to take this loop's work"*), which is **false** in that shape — siblings *are* free, just
   not eligible; that is F400. *Judge, once F400 ships:* does the new wording say "this loop only runs its own agent" rather than implying
   nobody is around?
2. **Does the board's stall reason match?** Same shape, on the *Loops* board. *Judge:* does the
   amber line read as "waiting for its own agent," not "no claimable task" (moved task 5.4's, now F400's
   distinction)?

## Not covered by this change

- **The wording itself** (group 5) — moved out to **F400** on 2026-09-21; F128
  is closed on the substitution being fixed (see `scripts/drive/FINDINGS.md`), independent of when
  the wording lands.
- **Which agents count as free for a flow's roster** — untouched by this change; that is
  `an-unstaffed-review-names-its-holders`'s and F352's territory.
