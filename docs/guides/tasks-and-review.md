---
description: The task board, dependencies, per-task worktrees, evidence, checks, review, and how approval merges.
---

# Tasks and review

A task is one unit of work. Most tasks are created by approving a [specification](specifications.md),
and some are made by hand or by an agent. A task records who did the work, what proves it, and who
approved it. Approving it merges it.

<figure class="aw-shot" markdown>
![The task board: a completed task waiting for review and an approved one, with requirement tallies and assignees](../assets/screenshots/tasks-board-light.webp#only-light)
![The task board: a completed task waiting for review and an approved one, with requirement tallies and assignees](../assets/screenshots/tasks-board-dark.webp#only-dark)
</figure>

## The board

The **Tasks** tab has a **Board** and a **Dependencies** view, a filter by agent, and a search box.
The board's columns follow the [task lifecycle](../reference/task-lifecycle.md): Pending, Assigned,
In progress, Under review, Completed, Needs revision, Approved, Rejected. Empty columns fold away.

Each card shows how many of its requirements are verified (`1/1 FR`), its assignee, priority and
age, and a one-line status when something needs saying: *Waiting on you*, *Waits on …*, *Sent back
for changes*, *Merge failed*.

You move a task by dragging it (or with ++ctrl+left++ / ++ctrl+right++), or with **Change status**
in its dialog. Only moves the lifecycle allows are accepted. There are no separate approve and
reject buttons: *Move to approved* **is** the approval.

## Dependencies

A task can depend on others. Dependencies are declared in the specification that created the task,
or added by hand. **A task cannot start until every prerequisite is approved.** Completed is not
enough, because completed work has not been reviewed. Cycles are refused.

The **Dependencies** view groups tasks by document and shows each chain: *Starts the chain*,
*Waits on …*, *After …*.

## Starting work

Hover over a card and choose **Start *profile* on this**, or ask a profile in a thread to take a
task. The run is **bound** to the task:

- the task moves to *in progress*, and takes that profile as assignee if it had none;
- in a git project the run works in the task's **own worktree**,
  `.agentweave/tasks/<task-id>`, on branch `agentweave/task/<task-id>`, cut from your main branch
  with its approved prerequisites already merged in;
- a profile cannot claim another profile's assigned task, and a run can complete only the task it
  holds.

If a bound run ends without moving its task, that is recorded as a **divergence**. The task's
setting *If a run ends without moving this* decides what happens next: **Tell me**, **Try again
once**, or **Hand to another agent**.

## Builds

**Build** on an approved document starts its tasks for you: you choose the profile that builds
them and a different profile that checks them, and a flow hands each task out as its prerequisites
are approved. With [parallel runs](agents.md#parallel-runs) on, one builder profile builds several
independent tasks at the same time.

A build's view lists its tasks, and on each task every run with its profile, runner, model, cost,
duration and outcome, its send-backs and its evidence. Any run opens its trace and its thread, while
the build runs and after it has finished or stopped. Those runs are not in the sidebar's threads:
the build is how you reach them.

The view's totals show the build's tasks, cost, runs and send-backs, and how many **Need you**. Each
task opens a timeline of its runs and the send-backs between them, and the **Needs you** filter
narrows the list to the tasks that want your attention.

When a document's last task is approved, the manager can write a **build retrospective**, and you
can ask for one with **Review this build** on the document. Its *Where the time went* section lists,
for each task, the time spent building, waiting for review, in the check gate and waiting to start.
Those figures are computed from the build's own records, never by the model.

The sidebar lists a build while it is running, and while it **needs you**: stopped before it
finished, or with a task that stalled, that the mender gave up on, or that has a question for you.
The build view's **Needs you** count reads the same rule. See
[Threads](conversations.md#builds).

## Evidence

Before an agent asks for review, it records **evidence** against the requirement: what it ran, the
output, and the commit it ran against. The Hub also records which files the evidence is about, as of
that commit. That footprint is what approval later merges, and what [drift](specifications.md#drift)
watches.

Evidence starts *awaiting review*. It is decided by you, or by an agent you have granted *Accept or
reject evidence*, never by the agent that recorded it. The reviewer's verdict on the task decides
it: approving accepts the evidence, sending the task back rejects it. Only you can overturn a
decision, and you must give a reason.

The **Evidence** view on the Spec tab lists every piece in the project, filterable by state and
agent, and each one opens to its proof: command, output, commit and diff.

<figure class="aw-shot" markdown>
![The evidence browser: every piece of evidence, its state, and its proof](../assets/screenshots/evidence-light.webp#only-light)
![The evidence browser: every piece of evidence, its state, and its proof](../assets/screenshots/evidence-dark.webp#only-dark)
</figure>

## Checks

Under **Project settings → Checks** you can list commands, such as your
test suite or linters, with a time limit each. When configured, they run in the background, in a
scratch worktree holding **exactly what approval would produce**: your main branch plus the task's
work. They run when a task completes and again before approval if the last result is stale. A
task's **Checks** row shows the result, with **Re-run**.

With checks configured, **approval is refused until they pass**. You can override a failure with a
reason, which is recorded on the approval. Agents cannot override. A check that fails on main
too is marked as pre-existing, and comes to you rather than back to the author.

Each check can also say:

- **Paths**: it runs only when the work changes a file that matches one. Otherwise it is skipped and
  counts as passed.
- **Fast**: it runs when a profile completes its task, before anyone reviews it, so the profile can
  fix a failure in the same run. A fast check may have a time limit of at most 120 seconds.
- **Runs**: *before review and at landing*, *before review only*, or *at landing only*. Use
  *at landing only* for a slow suite, so that review and approval do not wait for it.
- **Report path** and **Re-run command**: see [Reports and known failures](#reports-and-known-failures).
- **Command for a change**: runs in a task's check before review in place of the full command, given
  a file listing what the task changed. Landings and main still run the whole command.

**Checks give way to me** runs the processes a check starts below normal priority, so your own work
on this machine comes first. Fast checks keep normal priority.

How many checks the Hub runs at once is a Hub-wide setting, not a project one. The default is 2. It
is read and changed with `GET` and `PUT /api/v1/hub-settings` (`check_concurrency`), which need
your operator credential. A landing batch's checks take a free slot before other checks do.

### A check that could not run

A check whose command cannot start, for example because a program it needs is not installed, is
recorded as **could not run**. It is a result of its own: not a pass, and not a failure of the work.
The task's Checks row says *Checks could not run* and names what was missing, nothing is sent back to
the author for it, and the Overview lists it under *Needs you* until the check runs again. A landing
batch in which any check could not run does not land and sends nobody back: its tasks stay approved
and are queued again for the next batch.

### Reports and known failures

A check can name the **JUnit XML report** its command writes. The Hub reads that file after every
run to see which tests failed, and never reads a test runner's console output. With a **re-run
command** that takes the failed test ids (where `{tests}` stands), a failure is confirmed by running
only those tests again before it is held against the task. A failure that passes the second time is
a flake: the run goes on, and the test goes on the project's known-failing list.

The Overview's **Known failing tests** lists tests that fail on main or flake, each with the fix task
that owns it. A failure already on the list is not the task's: approval and landing go past it, and
a landing names the entries it went past.

If a run fails at least the check's **disturbed threshold** of tests (3 unless set, and at least 2)
and every one passes when re-run, the run is recorded as **disturbed**. No test is listed and no fix
task is filed: the machine was disturbed, and the tests are not flaky.

### Flaky tests are quarantined

The Hub keeps a flake rate for each test from the runs it has been in. When a check run records a
flip for a test and its flake rate, counting that flip, is above the project's **Quarantine
threshold**, the test is **quarantined**. The threshold is a rate above 0 and at most 1, and the
default is 0.05. A test with too few runs to have a rate is not quarantined.

A quarantined test still runs, and its history is still recorded, but its failures count against no
gate: they are not re-run to confirm, they do not fail a task's checks or a landing batch, and they
are not added to the known-failing list. A result or landing names the quarantined tests it excused.
Entering quarantine files one fix task for the test, unless an open one already names it. If the
work changes the test file the report names, the failure still counts.

A test leaves quarantine after **Passes to leave quarantine** consecutive passes, 20 by default; a
failure starts the count again. Both numbers are under **Project settings → Checks**, apply from the
next decision, and admit or release no test by themselves.

The Overview's **Quarantined tests** lists each test with its flake rate on entry, when it entered,
how many of its passes it has, and its fix task. **Never quarantine**, on a row or by naming a
check and test in the *Never quarantined* form below, takes the test out of quarantine and keeps it
out: its failures always count.

### Slow checks run once per landing

When the project has checks, approved work does not land one task at a time. Landings are queued and
land in **batches**, one batch at a time per project. The oldest queued landing waits up to a minute
for others to join, up to 8 tasks are taken together, and each task's work is merged onto main's tip
in order. The checks that run at landing run **once**, on the whole batch. When they pass, main moves
to exactly the commit that was checked; if main moved meanwhile, the batch is built again on the new
tip. A task's card shows where its landing is: queued, checking, landed or sent back.

When a batch fails, the Hub checks it task by task to find the first task whose part breaks it, and
only that task goes back to its author. A landing failure is **blamed on a task only when it
reproduces there**:

- A run that fails a disturbed number of tests, in files no task of the batch changed, is run once
  more on a quiet Hub before it is judged.
- A failure that reproduces on no task's part is held against nobody. The batch's checks run once
  more, and if it then passes, the batch lands and says which failures it went past. Those tests are
  listed as flaky.

### Pull request landing

With **Project settings → Landing → Land builds as pull requests** on, a build can put its approved
work on one GitHub pull request instead of merging into main. It is off until you turn it on, because
pushing publishes the work, and it needs a GitHub remote and a logged-in GitHub CLI (`gh`): the Hub
uses no token of its own. The Build dialog then offers *A pull request* under *Lands on*.

The first push opens a draft pull request against your main branch. Each approved task is merged
onto the build branch and pushed once the landing checks pass. The pull request is marked ready when
every task is pushed, and returned to draft if one is sent back. The Hub never merges the pull
request, approves it or changes its base: you merge it on GitHub. Two more settings sit beside it:

- **One commit per build** puts the whole build in a single commit instead of one per task.
- **The PR's CI is the full check** pushes without running the landing checks here, and lets the
  checks that count on GitHub decide whether the pull request is ready or the latest task goes back.
  Those are the checks GitHub marks required on the base branch, else the names you list under
  *CI check names*.

## Review

A finished task is reviewed by someone who did not write it:

- **A reviewing profile.** Ask another profile to review the task. A review run gets a clean,
  detached checkout of exactly the commit the evidence names. It runs what it needs, decides the
  evidence, and moves the task to *approved* or *revision needed*, with its reasons.
- **You.** Open the task. Its **Story** shows the runs, the evidence and the checks. Move it to
  approved, or send it back. **Land it** takes a completed task through review and approval in one
  step.

**A profile cannot approve, reject or send back work it produced**, including work it recorded
evidence for. A task cannot enter review while it is still assigned to its author.

## Approval merges

**Moving a task to *approved* merges its work into your main branch, locally, in the same
operation.** What merges is the commits named by its accepted evidence (or, if no evidence governs
the task, the tip of its branch). Nothing is pushed, and no remote or credential is involved.

Before you approve, the task dialog tells you exactly what will happen: *"Approving writes to your
repository: it merges 747084d from agentweave/task/… into main"*, or why it will not.

Approval is **refused**, with the reason, when:

- the merge would conflict (the refusal names the files; nothing in your checkout is touched);
- a run on the task is still live;
- evidence that would merge is still awaiting review;
- an approved prerequisite's work is not in the task's branch;
- configured checks have not passed;
- at **gate** rigor, a requirement it serves is not verified.

Approval succeeds but **records the merge as skipped** when the project has no main branch, the
checkout has uncommitted changes to tracked files, or the checkout is on another branch. A skipped
merge shows *Not merged* on the card, with **Retry**, and the Overview lists it under *Needs you*.

<figure class="aw-shot" markdown>
![A task's story after approval: merged into main, cost, runs, accepted evidence with the reviewer's reasoning](../assets/screenshots/task-story-light.webp#only-light)
![A task's story after approval: merged into main, cost, runs, accepted evidence with the reviewer's reasoning](../assets/screenshots/task-story-dark.webp#only-dark)
</figure>

When a task is approved or rejected, its worktree is released and its branch is kept.

## Worktrees and conflicts

**Project settings → Worktrees** lists every profile, thread and task checkout, and any conflicts between
them and your main branch, without touching any of them. Agent checkouts live at
`.agentweave/worktrees/<agent>`, task checkouts at `.agentweave/tasks/<task-id>`, and review
checkouts at `.agentweave/reviews/<agent>`. The Hub keeps all of them out of `git status` through
`.git/info/exclude`, so it never edits your `.gitignore`.

In a project that is not a git repository, agents share the project directory, nothing is merged,
and every agent's context says so.
