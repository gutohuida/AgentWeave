---
name: autonomous-session
description: Run a long unattended work session on an isolated branch, surviving the session deaths that kill naive loops. Asks what to work on up front (including "you choose"), commits and pushes every iteration, and keeps durable state on disk so any later session resumes exactly where the last one stopped. Use when the user says "work on this overnight", "keep working while I'm away", "work autonomously", "run until 10am", "do something crazy while I sleep", or asks to set up a recurring self-directed work loop. Pairs with /handoff, /resume and /e2e-loop.
---

Work unattended for a long stretch, on a branch nobody else is standing on, in a way that survives
being killed at an arbitrary moment.

## Read this first: what killed the last one

On 2026-08-15 this was attempted with `/loop`'s dynamic `ScheduleWakeup` mode. It was asked to run
from 00:40 to 10:00. **It stopped at 01:18 — four iterations, about forty minutes.**

The post-mortem matters because it dictates the whole design:

- The machine **did not sleep and did not reboot** (`Kernel-Power` shows only session transitions;
  last boot was two days earlier).
- The Hub **survived**, because it had been started detached via `Win32_Process.Create`.
- Nothing ran after the last iteration. **`ScheduleWakeup` is bound to the interactive session**, and
  when that went away, so did every future wakeup. Same for `CronCreate` — `/loop` says as much in
  its own confirmation line: *"Runs until you close this session."*
- **Nothing was lost**, because every iteration had already committed and pushed.

So there are two rules, and everything below follows from them:

> **Assume the loop dies at an unpredictable moment.** Never let that cost more than one iteration.
>
> **Durability comes from disk and git, not from the scheduler.**

### Choosing a driver

| Driver | Survives session death | Reaches the local machine | Use when |
|---|---|---|---|
| `ScheduleWakeup` (`/loop` dynamic) | **No** | Yes | You are present, or a short run |
| `CronCreate` (`/loop N m`) | **No** | Yes | Same |
| Cloud schedule (`/schedule`) | Yes | **No** | Work needing no local Hub, CLI or repo |
| **OS scheduled task running `claude -p`** | **Yes** | **Yes** | **Genuine unattended overnight work** |

For anything that drives a **local** Hub, local `codex`/`claude` runtimes, or the local checkout,
the cloud is not an option — it cannot reach them. The only durable local driver is an OS task
invoking headless `claude -p`, where each invocation is a **fresh process** that reads the state
file and performs exactly one iteration. See `scripts/` in this skill directory.

**Say which driver you are using and what it costs, before starting.** If the user is going to bed
and you arm a session-bound loop, tell them plainly that it will probably not survive the night —
do not let them find out in the morning.

## Step 1 — Ask what to work on

**Ask before proposing.** Use `AskUserQuestion` with the work options *and* an explicit
"you choose" option, because the user may genuinely not want to decide — but that has to be their
choice, not your assumption.

Offer, in a single multi-select where it fits:

1. **A specific queue** they name — open findings, a change in flight, a failing suite.
2. **Verification** — drive what was recently built and prove it works, rather than building more.
3. **You choose** — you pick from the repository's own record: unarchived openspec changes, open
   findings in `openspec/explorations/`, unchecked human-only tasks, the last handoff's next steps.
4. **Exploration** — write up a known gap properly rather than fixing anything.

Also ask two things that change the shape of the run:

- **A stop time**, and whether to stop early if the queue empties.
- **What is off limits.** Default to the limits in Step 2 and confirm rather than assume.

If the user has already said all of this, do not re-ask. Honour standing directives over anything
here.

## Step 2 — Set the limits, and write them down

State these in the log before any work, so a later session inherits them even if this one dies
mid-thought. Default set, adjust to what the user said:

1. **Stay on the autonomous branch.** No commits, merges or rebases onto the parent branch or
   `master`. Merging back is the user's decision, made awake.
2. **Nothing outward-facing.** No publish, no release, no PR or issue creation, no force-push, no
   history rewriting. Pushing the autonomous branch itself is required, not optional — it is what
   makes the work durable and reviewable.
3. **Nothing destructive.** No deleting projects, databases, or kept reproductions.
4. **Never mark work complete on the strength of a plan existing.** This matters more when nobody is
   checking, not less.
5. **Every claim is measured or labelled unverified.** If something could not be run, the log says so.
6. **Decisions that are genuinely the user's get written down, not guessed.** They collect in one
   section the user reads first.

## Step 3 — Cut the branch and open the log

```bash
git checkout -b autonomous_work        # or <topic>-autonomous if that name is taken
```

Never work on the parent branch. The point is that the user wakes up able to read a diff and throw
it away without consequence.

Then create the two files this skill runs on.

**The log** — `.claude/autonomous/<date>-<subject>-log.md`. Prose, newest entry at the **bottom**, so
it reads in the order the work happened. It is written for a human who was asleep. Each entry says
what was attempted, what actually happened, and what a reviewer should distrust.

**The state file** — `.claude/autonomous/STATE.json`. This is what makes death cheap. Machine-readable,
rewritten at the end of every iteration:

```json
{
  "branch": "autonomous_work",
  "started_at": "2026-08-15T00:40:00+01:00",
  "stop_at": "2026-08-15T10:00:00+01:00",
  "iteration": 4,
  "last_heartbeat": "2026-08-15T01:14:33+01:00",
  "queue": [
    {"id": "L9-2", "title": "Artefact cannot be cloned and run", "status": "open"},
    {"id": "loop9-revision", "title": "Rejected task back through builder", "status": "in_progress"}
  ],
  "current": "loop9-revision",
  "next_action": "Trigger builder on task-6de550a5 with the verifier's three rejections",
  "decisions_for_user": ["Merge autonomous_work into hub-native-experience?"],
  "limits": ["stay on branch", "nothing outward-facing", "nothing destructive"]
}
```

`next_action` is the important field. Write it as an instruction to a stranger, because that is
what the next session is.

Commit both before doing any work.

## Step 4 — Run iterations

Each iteration is a **complete, committed unit**. Never leave the tree dirty across a boundary.

1. **Re-read `STATE.json` and the log's last entry first.** Do not trust memory; the process may be
   new. Check `git log` and `git status` against what the state file claims, and reconcile out loud
   if they disagree.
2. **Check the stop time.** Past it, write a final entry and stop.
3. **Do one unit of work**, sized so it fits comfortably in one turn. Prefer a small finished thing
   over a large half-thing — half a thing is what dies badly.
4. **Verify it.** Run the tests. Drive the real surface where one exists. A green suite is not
   evidence that behaviour is right (see "What this skill learned", below).
5. **Append a log entry, rewrite `STATE.json`, commit and push.** Every iteration. This is the single
   most important habit here: it is why the failed overnight run lost nothing.
6. **Schedule the next iteration**, or exit if the driver is an OS task.

### Sizing an iteration

If an iteration ends without a commit, it was too big. Split it. The overnight run's iterations were
7–20 minutes each and every one ended pushed; that is the target.

## Step 5 — When context fills

Run `/handoff`, commit it, and let the next iteration `/resume` from it. The state file and the
handoff do different jobs: the handoff carries *understanding*, the state file carries *position*.
Keep both.

## Step 6 — Stop, and make the morning easy

At the stop time, or when the queue empties, write a final log entry with:

- **What changed** — commits, with which contain product code and which are only documentation.
  The user needs to know what to review closely versus skim.
- **What was proven** — with evidence. Distinguish what you drove from what you inferred.
- **What is open** — findings, with enough detail to act on.
- **Decisions waiting for the user** — the section they should read first.
- **What to distrust** — where the run was contaminated, where you tested your own work, what you
  could not verify.

Then say plainly, in the final message, **how far it actually got**. If it was meant to run nine
hours and ran forty minutes, that is the first sentence, not a footnote.

## What this skill learned, the hard way

These are not decoration. Each cost real time on the run that produced this skill.

**A green suite agrees with broken behaviour more often than you expect.** Three times in one
session: two tests stubbed a function that the route under test *also* used, so no run ever
happened and the assertions held over nothing; one patched `module.function` when the caller had
imported it under an alias, so the patch bound nothing. And a fix that 75 unit tests passed both
before *and* after was wrong in production — a payload shipped a raw exit code while the message
rendered it. **Mutation-check anything you claim: delete the line the test exists for, and watch a
named test fail.**

**The best evidence is the failure you did not stage.** A staged kill proves the handler runs. An
app-server dying on its own mid-interview, and the queue entry retrying twice and completing on a
fresh session, proves the feature. Watch for unprovoked failures and write them up when they happen.

**Verify the artefact, not the claim.** An agent reported "59 tests pass" and it was true; a fresh
clone still could not run them, because the claim was conditional on an install step. Clone it. Run
it the way a user would.

**Agents share more than you think.** They are isolated by worktree, not by environment. One agent
running `pip install -e .` changed what its own reviewer imported. If you install anything, uninstall
it and say so.

**Say when you contaminated your own test.** Testing code you wrote yourself inherits your blind
spots. That does not make the run worthless, but it makes a finding you *didn't* make weaker
evidence, and the user needs to know which is which.

## Reference — this repository

- Work belongs on an autonomous branch; the parent branch is the user's to merge into.
- Project instructions in `CLAUDE.md` still apply in full — in particular: never create
  `.agentweave/`, `agentweave.yml` or `spec/` at the repository root; use `openspec/`, never the
  `aw-*` skills; stage paths explicitly.
- Test projects live **outside** the repository.
- Start the Hub detached so it outlives the session:
  ```
  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}
  ```
  This worked: the Hub was the one thing that survived the night.
- `pytest hub/tests/` takes about seven minutes and exceeds the 600s command cap — run it in file
  chunks, or in the background.
- Interpreter: `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **Keep `.ps1` files ASCII-only.** Windows PowerShell 5.1 reads a BOM-less UTF-8 file as ANSI, so an
  em dash inside a double-quoted string corrupts the quoting and the file fails to parse — with an
  error pointing at a word several tokens later, which is not obvious. Both driver scripts hit this.
  Syntax-check after writing one:
  ```powershell
  $e=$null; [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $f).Path,[ref]$null,[ref]$e); $e
  ```
