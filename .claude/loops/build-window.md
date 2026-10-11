# The build window — BUILD, 09:00 to 21:30

**You are a fresh process with no memory.** Everything you need is on disk. Read
`.claude/autonomous/STATE-build.json` for position and the newest entry at the **bottom** of its
`log_file` (find it with `grep -n '^## '`, then Read by offset), do exactly the one thing
`next_action` names, rewrite the state, commit and push. One unit per firing. Never end an
iteration with a dirty tree.

**Why this window exists.** Operator, 2026-10-11 (`spec-queue/DECISIONS.md`, `away-1011`): away
until Wednesday 2026-10-14; the day builds the knowledge-vault roadmap end to end, and the window
may fast-forward master itself through the gate below. The night window keeps fixing the backlog
(`night-window.md`), unchanged. Both windows work on the **same cycle branch**
(`autonomous/<date>-daily`, settled by `arm-cycle.ps1`), so they never diverge.

The roadmap: `spec/changes/the-knowledge-vault-and-its-manager-roadmap/spec.json`
(`spdoc-7c75066d6403`), its `slices` array. Slices 1–5 are built (manager-framework,
vault-text-sources, distillation, contradictions, agent-reports). Remaining, in this order:
**specs-against-the-vault**, **images-and-pdfs**, **access-tuning**. The 2026-10-10 vault loop is
the worked example of one slice going spec → drive-first → build → drive → close:
`.claude/autonomous/2026-10-10-vault-playbook.md` and `2026-10-10-vault-log.md` (read by section).

## Iteration 1 — compose the queue

1. Check branch and tree: `git branch --show-current` equals STATE's `branch`, `git status --short`
   shows no tracked changes. Read the CI verdict the driver put at the top of your prompt.
2. Read where things stand: the newest entries of the previous `*-build-log.md` and of last night's
   `*-night-log.md` (by section), and the roadmap's `slices`. A slice is **built** when its change
   document's tasks have commits and its acceptance drive passed; it is **closed** when its change is
   folded (archived) on `:8010`. Check `spec/changes/` and `spec/changes/archive/` (or the Hub's
   documents list) rather than trusting a log line.
3. Compose the queue into STATE, in this order, each item with a standard suffix so
   `usage-policy.json` routes it (an improvised id falls to Opus/high):
   - `merge-gate` — always first. See "The merge gate".
   - `<slice>-close` for every slice that is built, not closed, and whose commits are on master
     (after the gate). Today, 2026-10-11, that is `contradictions-close` (`fcontra`) and
     `reports-close` (`freports`): both are on master since `8145541`; the exact commands are in
     `2026-10-10-vault-log.md`, iterations 4 and 8.
   - For the next unbuilt slice: `<slice>-spec` (`"model": "opus"`), `<slice>-drive-first`,
     `<slice>-backend-impl` (`"model": "opus"` when it is the hard half), `<slice>-tab-impl`,
     `<slice>-drive`. Then the following slice's items, if the day can plausibly reach them.
   - `ledger-close` — last: the window's final log entry with
     `py -3.11 .claude/loops/usage_report.py --windows --since <today>`.
   Keep STATE small: `detail` ≤ ~600 characters, results go in the log. Do no other work this
   iteration.
4. If every remaining slice is built and closed, the roadmap is finished: queue `merge-gate`, then
   Tier-0 fixes from the backlog (`night-window.md` "Implementing", severity first; check the night
   log so you do not take what it is working on), then `ledger-close`. Update the roadmap's memory
   line in the log so the operator sees it ended.

## The merge gate

Fast-forward master to the cycle branch **only when all four hold**, measured now:

1. `git rev-list --count <branch>..master` is 0 (a genuine fast-forward).
2. `git status --short --untracked-files=no` is empty and `git rev-parse HEAD @{u}` match.
3. CI for **this exact sha** concluded `success`. Find the run with
   `gh run list --branch <branch> --limit 5 --json databaseId,headSha,conclusion,status`; if it is
   still running, wait for it, polling every ~90 s, up to 25 minutes. A `failure` whose failed lines
   (`gh run view <id> --log-failed | grep -E '^(FAILED|ERROR) '`) are only `database is locked` or
   `bound to a different event loop` gets **one** `gh run rerun <id> --failed`, and its conclusion
   is the verdict. Any other failure: the gate stays shut and fixing it is the next item you queue.
4. No line beginning `HOLD MERGE` in the newest dated section of `spec-queue/DIRECTION.md`.

Then, without leaving the branch: `git fetch . <branch>:master && git push origin master`.
`git fetch .` refuses a non-fast-forward, which is the point; never `checkout master`, never a
merge commit, never resolve a conflict. Log the four measured values and the sha landed. Gate shut:
log which condition failed and carry on with the queue — the slice work does not depend on it, only
`-close` items do (mark those `blocked`).

## A slice, step by step

- **`-spec`** (Opus). Author the slice's change document on `:8010` with
  `scripts/drive/author_change.py <name> <payload.json>` (payload needs `"schema_version": 1`;
  usage in its docstring; payload drafts in `.claude/autonomous/scratch/`). Pick the tier
  (CLAUDE.md "Spec weight follows risk"; a migration or new storage is Tier 2). Requirements with
  scenarios, the **acceptance drive** named, short design decisions. The roadmap slice's `done`
  sentence is the acceptance drive's spine. Approve it through the Hub (`approve_anyway` is a
  **body** field). Queue its Hub task ids into the following items' titles.
- **Design questions** the operator would normally answer: take the recommended option, build it,
  and add an `OPEN` row to `spec-queue/DECISIONS.md` with id `build-<MMDD>-<n>`, worded "Taken by
  the loop: … Rejected: … Confirm or reverse." (the `vault-1010-*` rows are the model). Put the id in
  `decisions_for_user`. Questions the roadmap says are decided **in** the slice (F573), e.g.
  images-and-pdfs' "can each runner read PDFs and images itself", are settled by a measurement you
  run, not by guessing; record what you measured.
- **`-drive-first`**. Write `scripts/drive/d<MMDD>_<slice>.py` from the acceptance drive and record
  it **failing** on the tree before the build (`d1017_contradictions.py`, `d1024_reports.py` are
  the pattern).
- **`-impl`**. Tests first at the seam, failing before. `py -3.11` only; ruff over CI's paths and
  `py -3.11 -m black --target-version py311`. UI: vitest first, component, `npm run build` in
  `hub/ui`, `py -3.11 scripts/refresh_ui_bundle.py`, commit `hub/ui/src` and `hub/hub/static/ui`
  together. Editing `hub/hub/mcp_server.py` or a migration loads its `.claude/rules/` file: read it.
  Split an item `-a`/`-b` rather than leave work uncommitted at the end of a firing.
- **`-drive`**. The acceptance drive green on the **committed** tree, on a scratch Hub from source
  on a free port (8110+) with a fresh database under `testbed/`; every real agent turn binds
  `claude-haiku-4-5`; never leave a job enabled. Full Hub suite in chunks (`-n 4`) and full vitest
  once per slice. Record evidence on `:8010` (`close_change.py`'s per-change entry, pattern
  `freports`) but **do not land** until the commits are on master; append the METRICS row.
- **`-close`** (after the gate put the commits on master). `close_change.py <entry>` (duplicate
  evidence answers 409, harmless; the tasks land as "already integrated"), then
  `close_change.py --fold-change <entry>`, then
  `POST /projects/proj-d85a82bf4216/project/spec/reindex {}`, and mark the slice done in the roadmap
  document through the Hub. Commit what that writes under `spec/`.

## Hubs

- `:8010`, the trial Hub, `proj-d85a82bf4216`, key `~/.agentweave/hub/profiles/trial/bootstrap-key.txt`
  (`Authorization: Bearer`). If it is down, start it from `hub/` from source per
  `.claude/reference/hubs.md`; restarting `:8010` is allowed. It writes into this checkout, which is
  on the cycle branch — intended.
- `:8000` is the operator's. Never start, stop, call, migrate or write to it. A committed UI bundle
  reaches it on the operator's next reload and a migration on their next restart: name both in the
  log entry that commits them, so the close-out briefing carries them.

## Pace and time

- **Don't start what you cannot commit by `stop_at`.** If that is every remaining item, log why and
  set `next_action` to null; the driver then writes the close-out briefing. Tomorrow's 08:55 arm
  writes a fresh STATE, and its compose reads your log to continue.
- **Stall check:** an item at its third firing with no product commit gets split or marked
  `blocked` with the reason, and the queue moves on.
- **Findings** found on the way go to `scripts/drive/FINDINGS.md` (next free F-number) with a
  repro, not into the change. Spec-flow friction is a finding too (e.g. `approve_anyway` as a query
  parameter is silently ignored — file it if still unfiled).

## Limits

Everything in STATE's `limits`. Stage explicit paths; never `git add -A`. Do not browse the web.
Every claim measured or labelled unverified. No PRs, releases or publishing.
