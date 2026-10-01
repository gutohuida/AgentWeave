---
name: night-briefing
description: Morning briefing on how the night window went — what was built, what problems it found, the state of the cycle branch and its CI, whether it is ready to fast-forward into master, and what still needs doing. Reads STATE-night.json, the night log, the driver log, the usage ledger, git, CI and the findings ledger; changes nothing unless the operator then asks for the merge. Use when the operator says "morning briefing", "how did the night go", "night report", "what did the loop do overnight", "is the branch ready to merge", "brief me", or opens a session in the morning after AgentWeaveNightLoop has run.
---

The operator reads this once, over coffee, to decide two things: **does the branch go into master
today, and what do I need to do.** Everything else in the briefing serves those two answers.

This skill is **read-only**. It does not fix, re-run, commit, archive or edit the ledger. If it
finds something wrong, it says so and names who acts on it. The one write it may make is the merge,
and only after the operator says yes in this conversation (Step 7).

Sources and their contracts: `.claude/loops/night-window.md` (what the window is supposed to do),
`.claude/loops/day-window.md` "The merge gate" (the four conditions), `spec-queue/README.md`.

## Step 1 — Which night, and is it over?

```bash
powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm'"   # Git Bash date is skewed here
git branch --show-current
powershell -NoProfile -Command "Get-ScheduledTask -TaskName AgentWeave* | Select TaskName,State | ft -auto"
tail -5 .claude/autonomous/driver-night.log
```

Then read `.claude/autonomous/STATE-night.json` whole (it is small): `branch`, `parent_sha`,
`stop_at`, `iteration`, `log_file`, `current`, `next_action`, `queue`, `decisions_for_user`.

Settle three facts before anything else, and state them in the briefing's first lines:

- **Which night.** The `Armed` line at the top of `log_file`. If it is not last night, say so first —
  the window may not have armed (check `driver-night.log` and `AgentWeaveArmNight`'s last result).
- **Is it still running?** `AgentWeaveNightLoop` still registered, or a driver line newer than
  `stop_at`, means a firing may still be committing. Brief anyway, but label every branch fact as
  provisional.
- **How it ended.** From the driver log's last lines: `Past <stop_at> - unregistering` (ran out the
  clock), a null `next_action` (queue empty or `NOTHING TONIGHT`), a usage-limit or API error
  (`is_error: true`, `api_error_status` in the ledger), or non-zero exits. **The window rarely writes
  the "Ending the window" close-out entry** — it is usually cut off mid-item at 07:00 — so never
  assume that entry exists; reconstruct from the sources below.

The briefing describes the cycle branch from `STATE-night.json`'s `branch`, not from whatever is
checked out. Use explicit refs (`<branch>`, `origin/<branch>`, `master`) throughout, so it works
from either checkout.

## Step 2 — What was built

```bash
git fetch origin --quiet
git log --oneline <parent_sha>..origin/<branch>
git log --format='%h %s' --stat <parent_sha>..origin/<branch> -- hub/hub src hub/ui/src   # product code only
git diff --shortstat <parent_sha>..origin/<branch>
```

`parent_sha` is where tonight began; a branch spanning several nights started earlier — use
`git merge-base master origin/<branch>` for "everything not in master" and say how many nights that is.

Classify each commit: **product code** (touches `hub/hub/`, `src/`, `hub/ui/src/`), **tests only**,
or **docs/state/ledger only**. The operator reviews the first closely and skims the rest.

For the narrative, read the night log **by section, never whole** (it runs past 1000 lines):

```bash
grep -n '^## ' <log_file>          # one heading per iteration
```

Read the last two or three iteration entries with `Read` offset/limit, plus any entry whose heading
says a group or change finished. For each change worked on, report tasks ticked tonight vs. total:

```bash
git diff <parent_sha>..origin/<branch> -- 'openspec/changes/*/tasks.md' | grep -E '^\+- \[x\]'
grep -cE '^- \[x\]' openspec/changes/<change>/tasks.md; grep -cE '^- \[ \]' openspec/changes/<change>/tasks.md
ls openspec/changes/archive | grep <today-or-yesterday>          # archived tonight?
```

Separate **driven** (a live Hub, a browser, real agent turns) from **only tested**. The playbook
requires every change to be driven before its queue item closes; a change implemented but not
driven is not done, whatever its tests say.

## Step 3 — Problems found

1. **Findings filed tonight:**
   `git diff <parent_sha>..origin/<branch> -- scripts/drive/FINDINGS.md | grep -E '^\+## F'`.
   For each, one line: id, severity, what breaks. Read the section only if the heading is unclear.
   Never `cat` FINDINGS.md (33k+ lines). Also note findings whose `**Status:**` changed to `fixed`.
2. **Decisions waiting for the operator:** every id in `decisions_for_user`, with its `OPEN` row from
   `spec-queue/DECISIONS.md` (grep the id, read that section). These go at the top of "What you
   need to do".
3. **Pace and cost:**
   `usage_report.py --windows` buckets a night by calendar date and splits one window across two
   groups, so count from the ledger directly, filtered by the `Armed` timestamp:
   ```bash
   py -3.11 -c "import json,collections as C; rs=[json.loads(l) for l in open('.claude/autonomous/usage-ledger.jsonl',encoding='utf-8')]; rs=[r for r in rs if r.get('window')=='night' and r.get('started','')>='<armed ISO, e.g. 2026-09-30T22:55>']; print(len(rs),'firings', round(sum(r.get('total_cost_usd') or 0 for r in rs),2),'USD list', dict(C.Counter(r.get('item') for r in rs)), 'errors', sum(1 for r in rs if r.get('is_error')))"
   py -3.11 .claude/loops/usage_report.py --windows --since <yesterday> | grep weekly   # weekly-limit movement
   ```
   Firings, list cost, and per-item firing counts. An item at 6+ firings whose recent commits change
   no product code is the stall `night-window.md` "Pace" exists to catch — call it out.
4. **Loose ends:** `git status --short` and `git rev-parse HEAD @{u}` on the checkout if it is on
   the cycle branch; uncommitted work, an unpushed commit, or a background test run the last firing
   started and never read back (the last driver lines often say "waiting for the background run").
   Name the log file it was writing to, if the log entry gives one.
5. **Contamination:** the log's own "what to distrust" notes, any firing that tested its own work
   only, and any step the log says it skipped.

## Step 4 — CI

```bash
gh run list --branch <branch> --limit 30 --json databaseId,headSha,conclusion,status,workflowName,createdAt
```

Report the CI conclusion **for the branch tip sha**, in `gh`'s own word (`success`, `failure`,
`in_progress`, or "no run"). Then:

- **Red streak:** count consecutive non-`success` conclusions back from the tip. More than three:
  say "CI has been red for N consecutive pushes since <time>" in plain words.
- **Did the window notice?** `night-window.md` requires every firing to write CI's verdict word in
  its log entry, and makes fixing a `failure` that firing's job. `grep -niE 'CI verdict|success|failure' <log_file>`:
  if the branch went red and the log never says so, or kept building on red, that is a playbook
  failure in its own right — report it, with the first red sha and how many commits went on top.
- **Hung:** `in_progress` with `createdAt` more than 60 minutes ago is `HUNG` (F394), not pending.
- **Signature:** for a red tip, `gh run view <id> --log-failed | grep -E '^(FAILED|ERROR) '` —
  classify from those lines only, never `grep -i failed` (matches passing tests' names). Say whether
  the failures are ones the log already predicted (e.g. a finding's named cases), the known
  intermittents F292 (`database is locked`) / F314 (`bound to a different event loop`) — which are
  *fixed*, so either is now a regression — or new.
- If the branch's local suites were run tonight, quote their counts from the log next to CI's.

## Step 5 — Is it ready to merge?

Evaluate the merge gate from `day-window.md` against the **pushed tip**, plus two judgement checks.
Report each as PASS / FAIL with the measured value:

1. `git rev-list --count origin/<branch>..master` is **0** (a genuine fast-forward). If master has
   moved — interactive work commits to master — the merge is a real merge, not `--ff-only`; say so.
2. Tree clean and pushed: no uncommitted work on the cycle branch, `HEAD == @{u}`.
3. CI `success` for the tip sha exactly (not an earlier green). A known-intermittent red allows one
   `gh run rerun --failed` — recommend it, do not run it.
4. No line-initial `HOLD MERGE` in `spec-queue/DIRECTION.md`'s newest dated section.
5. *(judgement)* No change left half-implemented in a way that breaks behaviour on master. A change
   mid-way through its tasks is normal and mergeable when CI is green; a change whose tests are red
   *by design* until a later task is not.
6. *(judgement)* Nothing in "Problems found" is severity A against code this branch adds.

**Verdict** — one of: **READY** (all pass; give the exact commands), **READY AFTER <one thing>**
(e.g. a re-run of an intermittent, a pending CI run), or **NOT READY** (name the failed conditions
and what would fix each). Also say how many commits master is behind.

## Step 6 — Write the briefing

In the terminal, in this order and no longer than it needs to be. Lead with the answer.

```
# Night of <date> — <one-line verdict: e.g. "20 firings, 1 change advanced, CI red, NOT READY">

**Window:** armed <time> on <branch> · ended <how> at <time> · <N> firings · $<cost> list
**Merge:** READY | READY AFTER … | NOT READY — <reason in one sentence>

## What you need to do
1. <decisions waiting, by DECISIONS.md id, with the question>
2. <merge or not, and the command>
3. <anything only the operator can unblock>

## What was built
<per change: name, tasks ticked tonight (x→y of z), driven or only tested, archived?>
<commit list grouped: product code / tests / docs-state>

## Problems found
<new findings, one line each; CI signature; stalls; loose ends>

## Branch & CI
<tip sha, pushed?, clean?, CI word for tip, red streak, master behind by N, merge-gate table>

## What's next
<next_action in one or two sentences; open queue items remaining (count + next three);
what the day window or tonight's window will pick up; anything that will block it>

## Distrust
<what was only self-tested, not verified, or contaminated>
```

Keep facts measured: every number comes from a command run in this session. Anything inferred is
labelled so. Explain any finding id or decision id in words the first time it appears — the operator
does not carry ids in their head.

Offer, in one line at the end, to publish the briefing as an Artifact page.

## Step 7 — Only if the operator says merge

Merging is the operator's decision, made awake; never merge on your own reading of the verdict.
On an explicit yes:

```bash
git status --short                      # must be empty
git checkout master && git pull --ff-only
git merge --ff-only origin/<branch>     # if master moved, stop and ask: this needs a real merge
git push origin master
```

Remember `:8000` runs this checkout: **a merged UI bundle reaches the operator's live app on their
next reload**, and its next restart runs the merged migrations on real data. Say this before merging
if the branch touches `hub/hub/static/ui` or `hub/hub/migrations`.

After merging, interactive work continues on `master` (the night window checks out its own branch at
22:55).
