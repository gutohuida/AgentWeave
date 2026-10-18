# The day window — DRIVE, 09:00 to 17:00

**You are a fresh process with no memory.** Everything you need is on disk. Read
`.claude/autonomous/STATE-day.json` for position and the newest entry at the **bottom** of
`.claude/autonomous/<date>-day-log.md` for context. Then do exactly the one thing `next_action`
names, rewrite the state, and commit and push. One unit per firing. Never end an iteration with a
dirty tree.

**This window drives AgentWeave end to end and files everything wrong with it** (operator,
2026-10-18: "the daily run will be about driving and testing e2e agentweave and finding everything
wrong with it and the night about fixing everything that was found. Unless I add something new").
The night window fixes what you file, so a finding is only useful to it if it is **ready**: a
repro, a severity, the seam, and a tier.

**You do not fix product code.** If you find yourself editing `hub/hub/`, `hub/ui/src/` or
`src/agentweave/`, stop and file it instead. There are two exceptions:

- the drive tooling, meaning `scripts/drive/` and `.claude/skills/e2e-loop/e2e.py`;
- work that today's `spec-queue/DIRECTION.md` section asks for (see "Something new", below).

Map, tasks, state layout and the cycle-branch rule: `.claude/loops/README.md`. The driving method
is `.claude/skills/e2e-loop/SKILL.md`: read it in full on every sweep firing, because a fresh
process has not seen it.

## Budget discipline

The weekly limit is shared with the operator, and ~60% of a window's cost is cache reads (measured
2026-09-14). Context is the budget.

- **The driver picks your model and effort** from `.claude/loops/usage-policy.json` by the id in
  STATE's `current`. Sweeps (`-sweep`) fall to the default, Opus/high: finding bugs is judgement.
  Re-drives (`-drive`), the gate, compose and `ledger-` run on Sonnet/medium. **Keep `current`
  equal to the id `next_action` names**, or the next firing runs on the wrong model.
- **Read by section.** Grep for the heading or symbol, then Read with `offset`/`limit`. Whole-file
  Reads over 60 KB are refused (`.claude/hooks/large-read-guard.py`). Never `cat` a spec-queue
  file, `FINDINGS.md` or `BACKLOG.html`.
- **Keep STATE small.** Each queue item is `id`, `status`, `title`, optional `model`/`effort`, and a
  `detail` of at most ~600 characters. Results go in the log, not in `detail`. Compose only what
  the window can reach, which is about 6 to 9 items.
- **Subagents run in the foreground.** A sweep may split its area across up to three foreground
  subagents, each with its own scratch Hub port. A background subagent from a headless run is
  waited for at most 60 minutes, then killed.
- **Close-out:** the final log entry includes the output of
  `py -3.11 .claude/loops/usage_report.py --windows --since <today>` for this window.

---

## Iteration 1 — compose the queue

Only the first firing does this. It ends by writing a full `queue` into `STATE-day.json`.

0. **Orient.** Run `py -3.11 scripts/backlog_page.py --check`. If it exits non-zero, run it
   without `--check` and read the `SINCE LAST GENERATION` block it prints. That block shows what is
   open, what is ready, and what moved. Knowing it is what stops you filing a duplicate.
1. **The morning merge gate.** If last night left the cycle branch unmerged, run `## The merge
   gate` (below) now, against the pushed tip. Nothing has committed since the night, so CI's
   verdict for that sha already exists and you only read it, without waiting. Log the result
   either way, then carry on. The gate does not block the day's driving.
2. **Something new.** Read the newest dated section of `spec-queue/DIRECTION.md`, but only if it is
   dated **today**. Also read any rows added to `spec-queue/REQUESTS.md` since the last day log.
   What the operator added comes **first** in the queue:
   - **A feature, area or change to test** becomes a scoped `-sweep` item, using the skill's scoped
     mode.
   - **Something to specify or build** becomes the items it asks for, with the tier rules from
     `CLAUDE.md`. This is the one case where the day may touch product code.
   - **A read-only review of the operator's real use** becomes an `o1` item. It opens :8000's
     database through a `mode=ro` SQLite URI only. Its files and transcripts are read, never
     written, and nothing is ever called on :8000.

   No section for today means the default queue. An absent section is not an instruction to stop.
3. **Last night's fixes.** Read the newest `.claude/autonomous/*-night-log.md` closing entry. Every
   finding it marked `fixed` that touches a route, a run, a gate or the UI goes into **one**
   `night-recheck-drive` item. That item re-drives each fix live, end to end, through the path the
   finding named. A fix that passes its test and cannot fire is this repository's commonest defect
   (`CLAUDE.md`), and the morning after is the cheapest time to catch it. A fix that does not fire
   reopens its finding: change its `**Status:**` back to `open`, with the evidence.
4. **Do not choose sweep areas here.** The `plan-review` item chooses them, after it has checked
   the plan against the code.
5. **Write the queue**, in this order:
   1. `plan-review`, always first (operator, 2026-10-18; see the next section);
   2. the items from step 2;
   3. `night-recheck-drive`, if step 3 found anything;
   4. `ledger-tidy`: regenerate the backlog page, and check that every finding filed today has
      `**Ready:**` and `**Tier:**` lines;
   5. `D-7`, the merge gate, always last.

   `plan-review` inserts the sweep items in front of `ledger-tidy`.

---

## The pretask — `plan-review`

The operator asked on 2026-10-18 that the drive loop **start by reviewing the plan against the
code**: does the plan reach everything, and is there something new? The plan is the skill's
checklist (`## The checklist — what "everything" means`). It drifts, because the product moves
faster than the file.

1. **Run the skill's Step 0 in full**, including its *plan against the code* inventory: the routes,
   the MCP tools, the CLI commands, the UI components, and what landed since the checklist date.
   Write the result into the checklist itself: unreached paths added to a row, new paths marked
   `(new <date>)`, gone paths removed. Commit `.claude/skills/e2e-loop/SKILL.md` alone, with a
   message that counts each of the three.
2. **Log `PLAN: rows <n> · unreached added <n> · new <n> · gone <n>`**, and list the new and
   unreached paths by name.
3. **Choose today's sweep areas**, three or four of them, in this order:
   - (a) rows with new or unreached paths from step 1;
   - (b) rows last night's commits touched heavily (`git log --stat` since the arm);
   - (c) rows swept least recently (grep the last seven day logs for `SWEPT:` lines). A row that
     has never been swept counts as least recent.

   Pair rows whose seam is the point, such as the spec flow with tasks and runs, or the vault with
   specs. Insert one `sweep-<area>-sweep` item each, with the new paths named in its `detail` so
   the sweep drives them first.

This item drives nothing. It reads code and edits only the checklist. Keep it to one firing.

---

## A sweep firing — `sweep-<area>-sweep`

The method is the skill's Steps 3–8 and its harness, `e2e.py`. Its Step 1 and Step 2 questions
are already answered here. The scope is the item's area. Nothing stops for an operator: a decision
that is truly theirs becomes an `OPEN` row in `DECISIONS.md`, and the sweep carries on.

- **A scratch Hub from source on a free port, 8110 or above.** Check the port is free with
  `netstat -ano | grep LISTENING` first. Use a fresh database under `testbed/` and test projects
  under `testbed/`. Before trusting it, confirm the Hub runs this branch's code (skill Step 3).
  Stop it at the end of the firing. **Never :8000, and never :8010.**
- **Every real agent turn binds `claude-haiku-4-5`.** Never leave a job or a loop enabled.
- **Drive as the operator would**, through the routes the UI calls, and check what the operator
  would *see*: the event, the panel, the status. Checking the database row alone is not enough.
  Provoke each refusal and judge whether it is legible. Ask what each route returns when the thing
  it calls raises. A UI area is driven in a browser against the served bundle. If no browser was
  available, say "not browsed"; never claim it was.
- **Record every defect as a new `F<n>`** in `scripts/drive/FINDINGS.md`. Grep the ledger and
  `openspec/changes/` first, so you do not file a duplicate. Follow the format of the newest
  entries, and add:
  - `**Ready:** yes`, once the repro is pinned down;
  - `**Tier:** 0|1|2`, from `CLAUDE.md`'s table;
  - the seam, the exact repro (the route, the body and what came back), and where a failing test
    would sit.

  The night builds from exactly this, with nobody to ask. A finding that reads "might" and has no
  repro is not filed.
- **Disproving a finding counts.** If a drive shows that an open finding no longer reproduces, set
  its status, with the evidence.
- **Log `SWEPT: <area> — passed: … · failed: F… · not reached: …`.** The next day's step 4 rotates
  on these lines. "Not reached" is a real result: record it, never omit it.
- Keep a drive script under `scripts/drive/s<MMDD>_<area>.py` when it is reusable. Commit it with
  the findings.

## Re-driving last night's fixes — `night-recheck-drive`

This is the skill's scoped mode, with one scope per fixed finding. Drive the path the finding's
repro names, on this branch's code, and read the effect back. Do not trust the echo. For each
finding, log `CONFIRMED F<n>` or `REOPENED F<n>` with what you saw.

---

## The merge gate — `D-7`, the window's last firing

Fast-forward master to the cycle branch **only when all four conditions hold**, measured now.
Decided 2026-09-19 (`merge-gate-cadence`) and reaffirmed by the operator on 2026-10-18.

1. `git rev-list --count <branch>..master` is 0, so this is a genuine fast-forward.
2. `git status --short --untracked-files=no` is empty, and `git rev-parse HEAD @{u}` match.
3. CI for **this exact sha** concluded `success`. Find the run with
   `gh run list --branch <branch> --limit 5 --json databaseId,headSha,conclusion,status,createdAt`.
   At D-7, if it is still running, wait for it, polling every ~90 s, for up to 25 minutes. Nothing
   commits behind you, so the wait ends.

   A `failure` whose failed lines
   (`gh run view <id> --log-failed | grep -E '^(FAILED|ERROR) '`) are only `database is locked` or
   `bound to a different event loop` gets **one** `gh run rerun <id> --failed`, and that rerun's
   conclusion is the verdict. A run still `in_progress` after 60 minutes is **HUNG**: treat it as
   red. Any other failure keeps the gate shut, and fixing it becomes the night's first item.
4. No line beginning `HOLD MERGE` in the newest dated section of `spec-queue/DIRECTION.md`.

**The migration hold.** If `git diff --name-only master..<branch>` adds a file under
`hub/hub/migrations/versions/`, the gate stays shut. Log `HOLD: migration <file>` and add an `OPEN`
row to `DECISIONS.md` for it. The operator's :8000 runs this checkout, and its next restart would
run that migration on real data, so a person lands it awake. This hold is the loop's own safety
rule, added 2026-10-18 alongside the operator's go-ahead for Tier 2 work at night. It is not one of
the operator's decisions.

When the gate opens, stay on the branch and run
`git fetch . <branch>:master && git push origin master`. `git fetch .` refuses a non-fast-forward,
which is the point. Never `checkout master`, never make a merge commit, and never resolve a
conflict. Log the four measured values and the sha that landed. When the gate stays shut, log which
condition failed.

Then write the closing entry: the findings filed by severity and tier, the areas swept, what was
confirmed and reopened, and the decisions waiting for the operator. Set `next_action: null`.

---

## Limits

- **Stay on the cycle branch.** Only the merge gate touches `master`, and only as written above. No
  rebases, ever. Push every iteration.
- **Nothing outward-facing:** no publish, release, PR, issue, force-push or history rewrite.
- **Nothing destructive:** no deleting projects, databases or kept reproductions. Do not delete
  `.agentweave/` or `spec/` at the root.
- **Do not browse the open web.** Research is `AgentWeaveResearch`'s job (`README.md` says why).
- **Every claim is measured, or labelled unverified.**
- **Decisions that are truly the operator's** get an `OPEN` row in `spec-queue/DECISIONS.md`, and
  only that row's id goes in `decisions_for_user`. At compose, drop and log any inherited id whose
  row is no longer `OPEN` (F305).
- Stage explicit paths, never `git add -A`. Never commit `kimichanges.md` or `kimiwork.md`.
- Tests run under `py -3.11`, never bare `python`. `black` needs `--target-version py311`.
- **Port 8000 is the operator's real use.** Never start, stop, probe, call, migrate or write to it.
  Never drive against `proj-5e960453` or `proj-18e5d4e0`.
