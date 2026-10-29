# The measured re-run: one change built at Fast and at Gated (2026-10-28)

Slice H of the roadmap "Flows that do not stall after the October 25 retrospective"
(`spec/changes/the-measured-re-run/spec.json`). One candidate change was built twice on the
operator's Hub (:8000, project `proj-d85a82bf4216`), from the same base commit `4388621600ed`.
The candidate was "Every same-file overlap reaches the operator" (F1013, F1014, F1015: three
tasks, editing hub/hub and hub/ui). Fast ran first, then Gated. Both used the same builder,
`Developer` (claude-sonnet-5-5), the same mender model, the same project checks and a $30 cap with
an 8 h window. Only Gated had a reviewer, `QA` (claude-opus-5-5).

Real defects caught by either build: 0. Both builds produced the same seven files and passed
every project check when assembled by someone who took no part in them. Each let the same two
small defects through (see Escaped defects). Gated cost about 2.7 times what Fast did and needed
four operator actions to Fast's one, and its review found nothing Fast missed. On this candidate,
Gated bought an operator check the change asked for, and nothing else.

## The comparison

Sources: "stats" is slice G's project view (`GET /stats`, the build's row) and "build panel" is
the spec page's build figures (`GET /project/spec?path=...`, `builds[].figures`). A cell marked
"from a query" is a number no view shows: it was read with a read-only SQLite query of the Hub's
database, or counted by hand from the record, and each one is filed as a finding (F1079). The
baseline columns predate builds, so the views give them no wall-time split.

| Figure | 2026-10-25 flow (loop-df5f74816122) | 2026-10-26/27 night (slice B, loop-cee87801ae6a) | Fast (build-f7c5b7855dbc) | Gated (build-cee80c298887) |
|---|---|---|---|---|
| Tasks | 6 (recorded; 4 on the loop) | 4 (from a query: tasks on the loop) | 3 (stats) | 3 (stats) |
| Wall time in total | 7 h 26 min (recorded, src-17aeb9aea81f) | 6 h 45 min (from a query: first run to last run) | 1 h 29 min 4 s (stats wall.total) | 1 h 52 min 48 s (stats wall.total) |
| Wall time per task | 74 min (recorded total / 6) | 101 min (from a query) | 29 min 41 s (stats) | 37 min 36 s (stats) |
| Wall: building | not split (no view covers flows before builds) | not split (no view covers flows before builds) | 18 min 41 s (build panel) | 17 min 38 s (build panel) |
| Wall: waiting for review | about 3.3 h (recorded) | not split (no view covers flows before builds) | 4 s (build panel) | 35 min 3 s (build panel) |
| Wall: checks | not split (no view covers flows before builds) | not split (no view covers flows before builds) | 1 h 10 min 14 s (build panel) | 25 min 46 s (build panel) |
| Wall: waiting to be handed out | not split (recorded: every hand-off waited for the 5-minute tick) | not split (no view covers flows before builds) | 5 s (build panel) | 4 s (build panel) |
| Cost in total | $27.51 (stats; $52 recorded, including spec writing) | $41.80 (stats; $44 recorded) | $1.05 (stats) | $2.87 (stats) |
| Cost per task | $4.59 (stats / recorded tasks) | $10.45 (stats / tasks) | $0.35 (stats) | $0.96 (stats) |
| Cost: building | $10.93 (stats) | $14.66 (stats) | $0.87 (build panel) | $0.78 (build panel) |
| Cost: reviewing | $11.05 (stats) | $11.28 (stats) | $0.00 (build panel) | $1.69 (build panel) |
| Cost: mender | $5.53 (stats) | $15.86 (stats) | $0.18 (build panel) | $0.40 (build panel) |
| Send-backs | 6 (stats) | 4 (stats) | 0 (stats) | 0 (stats) |
| Real defects caught (check / reviewer / operator) | not classified here (6 send-backs, 2 failed check runs) | not classified here (4 send-backs, 4 failed check runs) | 0 (from a query: no send-back and no failed check run to classify) | 0 (from a query: no send-back and no failed check run; the operator check passed) |
| Escaped defects | not measured | not measured | 2 minor (from a query: independent assembly, see below) | 2 minor (from a query: independent assembly, see below) |
| Operator actions during the build | not recorded | not recorded | 1 (from a query: count by hand) | 4 (from a query: count by hand) |
| L: review turns begun beside a failed check | 3, $3.56, 52 min (stats) | 3, $4.38, 52 min (stats) | 0 (stats) | 0 (stats) |
| M: hours an approval waited on a failure not the task's | not measured (the record does not separate it) | not measured (the record does not separate it) | 0 h (from a query: the failures were approved over at once) | 0 h (from a query: no such failure) |
| N: mender turns | 19 (stats) | 42 (stats) | 1 (stats) | 3 (stats) |
| N: mender cost | $5.53 (stats) | $15.86 (stats) | $0.18 (stats) | $0.40 (stats) |
| N: mender model | claude-opus-5-5 (from a query) | claude-opus-5-5 (from a query) | claude-sonnet-5-5 (from a query) | claude-sonnet-5-5 (from a query) |
| N: mender wakes with no stalled work | not measured | not measured | 1 (from a query: 12:27, checks were running normally) | 0 (from a query: both wakes had a task truly waiting) |
| N: mender questions that expired unanswered | 1 (from a query) | 27 (from a query) | 0 (from a query; one left open, moot) | 0 (from a query; one left open, moot) |

Two notes on the view's numbers. The view's wall total is the sum of its parts, not the clock
time. By the clock, Fast ran 10:58:28 to 12:29:03 (1 h 30 min 35 s) and Gated ran 12:32:52 to
14:27:48 (1 h 54 min 56 s). Gated's view also gives 34 min 17 s of "reviewing", time QA's turns
ran. That falls within "waiting for review" and is not a row of its own here.

Cost the views leave out: Fast's checks opened a follow-up task, `task-c9d09a9fd379`, to fix two
timing tests that failed under load. Its turn cost $0.18 and belongs to no build. Fast all in:
$1.24. Each build record's `spent_usd` is $0.87 for Fast and $2.47 for Gated, because it leaves
out the mender turns that the build panel counts (F1077).

## Where the time went

- **Fast.** The builder's three turns ended by 11:19. The rest was checks. Each task's full Hub
  suite took 40 to 45 minutes, against about 12 minutes alone, because the suites ran side by
  side. The third task's checks waited about 30 minutes for a free slot (F1075). The parallel
  load made two timing tests fail. The Hub approved over them as "not the task's" and opened the
  follow-up task.
- **Gated.** The builder's turns ended by 12:53. QA reviewed the tasks one after another from
  13:12 to 13:52 (18, 12 and 4 minutes). F1015 then stopped at the evidence gate. Its criterion
  `operator-sees-both-pairs` is checked by the operator, and at Gated an operator-checked
  criterion with only partial evidence blocks approval. The operator cannot approve over it. The
  mender asked the operator and offered "Approve without the check", which neither the mender nor
  the operator can do (F1073, F1074). About 33 minutes went on that: the answer, a refused
  approval, then a real in-app check on a scratch Hub served from Gated's branches (Playwright, 
  `h/opcheck/gaplist-full.png`), recorded as operator evidence `ev-f59cdc2a15c5`, and the
  approval.

## Every send-back and failed check run, classified

Neither build had a send-back, and the app records no failed check run for either. One check
run did have failures, which the app records as "passed" (F1078). It is listed here so nothing
is hidden:

- Fast, `task-e50d0d42e298`, check run `chk-2cbb324baa52`: `test_a_busy_project_opens_inside_a_second`
  (1.009 s against a 1.0 s bound) and `test_more_operator_streams_than_the_pool_holds_all_open`
  failed in the run and passed when rerun alone. **Not the task's**: three suites were running
  at once. The Hub approved over them and opened the follow-up `task-c9d09a9fd379`.
- Gated, `task-a2437846eb7f`: the approval was refused with `gate_unsatisfied` because FR-3 had
  only partial evidence. **Not a defect**: the gate worked as Gated defines it. The operator
  check then passed.

## Escaped defects

Someone who took no part in either build assembled each one: base `4388621`, the three task
branches merged no-ff, Fast at `ad1eb55a3c7a` and Gated at `27576b454625`. They then ran ruff,
black, mypy, eslint, tsc, vitest (2392/2392), the CLI suite and the Hub suite (Fast 9330 passed;
Gated 9329 passed; 0 failed), the candidate's acceptance tests, and the repro tests written red
on master before the build. Everything passed on both. Two defects escaped both builds alike:

1. **The UI bundle was not rebuilt.** `hub/ui/src/components/spec/SpecPhaseParts.tsx` changed
   and `hub/hub/static/ui` did not. This repository requires the two to be committed together,
   and without the rebuild the fix never reaches the running app. Fast's builder listed it as
   not done in the task notes. Gated's reviewer did not send the task back for it.
2. **A `<ul>` nested inside a `<span>`** in `SpecPhaseParts.tsx`, in Fast's `GapLine` and in
   Gated's `GapLines` (invalid HTML, which renders anyway). Minor.

## Re-recording held evidence

Across the project's 403 evidence pieces since slice K shipped, the Gated build's included, no
held piece was ever judged again: 0 re-judged, 0 failed, $0.00 of review cost. The rule needs
at least 5 pieces judged again before deciding, so the recommendation is: keep re-recording;
the evidence is too thin to change it.

## Deviations from the plan

- **Another Hub was running.** The old trial Hub on :8010 (running since 10-24) stayed up through
  both builds, against `one-build-at-a-time`. It ran no turns in either window. Process lists
  were saved at each start (`h/processes-fast-start.txt`, `h/processes-gated-start.txt`).
- **Landing `nowhere`, assembled afterwards.** Each build used landing `nowhere` instead of its
  own landing branch, because landing anywhere but the checked-out branch needs switching the
  live checkout (F1056). The builds' branches were assembled afterwards by someone who took no
  part. Nothing reached master.
- **A twin document for Gated.** The Gated build ran on a twin of the candidate document,
  `spec/changes/every-same-file-overlap-reaches-the-operator-at-gated/spec.json`. A second build
  of one document has no open tasks to build (F1058).
- **The base commit is not on the build view.** Both builds started from `4388621` (recorded at
  the start); the build record does not say so (F1079).
- **Master moved for 25 seconds.** While doing the operator check, a helper agent merged Gated's
  three branches into the master checkout by mistake, at 14:19:02, and reset it to `4388621` at
  14:19:27. :8000 recorded "main moved" notice `mnot-79d178be9942`. Neither build was affected:
  both had ended or were waiting on the operator.
- **Questions left open.** The mender's questions `q-3985f03c03f5` (Fast, 12:27) and
  `q-527c404bf04f` (Gated, 14:27) were not answered while their builds ran, and both were moot
  by the time they were seen (F1076).

## What to take from it

- On a small, well-specified change with good tests, Gated's reviewer caught nothing the checks
  had not. It cost $1.69 of $2.87, and it missed the one rule the checks cannot see (the bundle
  rebuild). Fast's cheapness came with no visible loss of quality here. One candidate is not
  enough to generalise from.
- The checks, not the agents, set the pace. Fast spent 70 of its 89 view minutes in checks,
  most of it queueing behind other suites. Running checks side by side made timing tests fail
  and cost a follow-up task. The cheapest speed-up is running the checks one after another with
  a smaller suite per task, not a cheaper agent.
- The mender on Sonnet cost $0.18 to $0.40 per build, against $5.53 and $15.86 on Opus in the
  baselines, and let no question expire. But it twice offered actions nobody could take, and
  once recommended killing a healthy check run.
