---
description: Threads and runs — the sidebar's threads and builds, starting a thread with a profile, the composer, questions and permission requests, the side panel, context and checkpoints.
---

# Threads

You work with a [profile](agents.md) in a **thread** (the app's conversation). Each message you
send starts a **run** of that profile in the thread: the Hub launches the profile's CLI on one
entry of its pool, streams everything it does into the timeline, and records how the run ended and
what it cost.

Threads are not only yours. Every run has one: a task build, a review, a mender turn, a job firing,
a message from one profile to another. The sidebar lists only yours; the others are found through
the build, flow, task or profile they belong to.

<figure class="aw-shot" markdown>
![A thread with the builder: its report, the context meter, the composer with model, effort and permissions, and the spec open in the side panel](../assets/screenshots/conversation-build-light.webp#only-light)
![A thread with the builder: its report, the context meter, the composer with model, effort and permissions, and the spec open in the side panel](../assets/screenshots/conversation-build-dark.webp#only-dark)
</figure>

## The sidebar

Under each project the sidebar holds two lists, **Builds** and **Threads**, and nothing else.
There is no list of profiles: profiles are reached from their threads, the project's **Overview**
and its settings. Each list's header shows how many it holds and can be folded away; the app
remembers which you folded. The arrow keys move between rows, and ++enter++ opens one.

### Builds

**Builds** lists every build that is **running**, and every build that **needs you**. A build
needs you when:

- it was **stopped** before it finished;
- one of its open tasks has **stalled**;
- the mender **gave up** on one of its tasks;
- one of its tasks has a **question** for you.

Builds that need you come first. Each row shows the document's title and one word for its state:
*Stopped*, *Stalled*, *Given up* or *Question*, or, while it runs, how many of its tasks are done
(*3/7*). Choosing a row opens that build's view. The sidebar's "needs you" and the build view's
**Needs you** count read the same rule, so the two never disagree.

A build that is not running can be dismissed with its **×**: it leaves the list and stays gone
after a reload. It comes back if it needs you again for a new reason (a new stall or question, or
a restart followed by another stop). A running build cannot be dismissed. A finished build that
needs nothing is not listed; every build, finished ones included, is on the side panel's
**Running** tab ([below](#the-side-panel)).

### Threads

**Threads** lists your threads, as one list:

- a thread you started;
- a thread you have written in, such as a job firing you replied to;
- a thread cut over from one of yours at a [checkpoint](#context-and-checkpoints).

Threads **waiting for you** (an amber mark and a hand) come first; the rest follow by most recent
activity. Each row is labelled with its profile's name, and a green mark means a run is going. A
thread that a loop fired, or that another profile started, says so on hover.

Past 15 threads, the rest go behind **Show N more**, and a **Filter threads** box appears that
matches a thread's title or its profile. Archived threads are hidden until you choose **Show
archived**. A list that could not be read says so, with **Try again**, rather than showing as empty.

What the list leaves out is deliberate. A task build, a review or a mender run, a job firing, a
message between profiles: none of them is yours until you write in it, so none is listed. They are
reached elsewhere:

| Run | Where to open it |
|---|---|
| A run that served a task of a build | The build's view: every task, every run on it, its trace and its thread, while the build runs and after it finishes or stops. |
| A run a flow started | The flow's page on the **Jobs** tab, under **Runs**. See [Jobs, loops and flows](jobs-loops-flows.md#a-flows-runs). |
| Any run of a profile | The profile's settings, under **Runs**. See [Profiles](agents.md#a-profiles-runs). |

Nothing leaves the record: every run stays reachable through its build, flow, task or profile.

### The collapsed sidebar

Collapsed to icons, the sidebar shows your **projects only**. A project with a build that needs you
carries a mark, a hand as well as a colour, and its name, read aloud or on hover, says how many
builds need you and which. Choosing a project opens it.

The sidebar can be resized or collapsed, and it remembers both.

## Starting a thread

Choose **New thread** (**+** in the **Threads** header) and pick the profile to talk to. Nothing is
created until you send the first message. The new-thread screen offers starters: *Pick up the next
task*, *Catch up on today*, *Review the latest work*.

A new thread starts on the profile's **default pool entry**. Before the first message you can
change either:

- the **profile**, to any open profile of the project;
- the **entry**, in the composer, to any entry of the chosen profile's pool.

After the first run, the thread's profile is fixed. Its entry can still change, but only to another
entry of that profile's pool on the CLI the thread started on: one CLI cannot resume another's
session, and the Hub refuses the change with that reason.

A thread can also be started by another profile sending a message, by a scheduled job, or by a loop
firing. Those threads join your list once you write in them.

## The composer

The composer sends your message to this thread's profile. There is no recipient picker. Under the
text box, each run can be set to:

- **Model.** An entry of the profile's pool: a runner, a model and an effort, searchable, with
  favourites. A runner that fixes its model shows it read-only.
- **Effort.** The reasoning effort the provider supports, such as low, medium or high.
- **Permissions.** The [posture](../reference/permission-postures.md) for this run: **Workspace
  only**, **Edit files**, **Ask me** or **Full access**. At rest it shows the profile's default.
- **Spec.** **Explore** starts a new specification document with your first message. The folder
  button attaches an existing one. See [Specifications](specifications.md).

Type `@` to mention a file and `/` for commands. While a run is going in this thread, your message
queues and is delivered when that run ends. With [parallel runs](agents.md#parallel-runs) off, a
message also waits for the profile's runs in other threads. You can withdraw a queued message
before it is delivered.

## The timeline

Each run shows the profile's prose, its reasoning, and a card for every tool call it made: reads,
edits (as diffs), shell commands, searches. A run that did not end normally says so: *Turn
failed*, *Turn stopped* or *Turn interrupted*. That label comes from what the Hub recorded, not
from what the run wrote. Each run has a **trace** button that opens a waterfall of it: model calls,
tools, permission waits and questions. See [Traceability](traceability.md).

**Stop** in the conversation bar ends a running run.

## Questions from agents

A run that needs a decision calls `ask_user`. A question card appears above the composer, with
options to pick (++1++–++9++) or room to write your own answer. The run waits for you, up to its
profile's question timeout. Questions also appear on the project's **Overview** under *Needs you*,
and a question on a build's task makes that build need you in the sidebar.

If you answer after the run has already ended, your answer is delivered as a new message, and the
card tells you so.

!!! note "No guessing on either side"
    A run that does not call `ask_user` has simply finished. AgentWeave does not read a run's
    closing prose to decide whether it "sounded like" a question. If you want a profile to stop and
    ask, say so in its charter or your instructions.

## Permission requests

Under **Ask me**, or when a call falls outside what **Workspace only** or **Edit files** allows, the
run's request comes to you as a card: a command, a file read, a file change, a tool call, or a
change to a runner's own configuration. Choose **Allow** or **Deny**. A card that times out is a
refusal, and the run moves on.

## The side panel

A thread can open a panel beside it, from **More conversation actions** in the conversation bar.
The panel holds tabs; **+** adds one:

- **Specs.** Browse specification documents. Opening one gives it a tab.
- **Files.** The run's own checkout, or the project root: a switch says which one you are looking
  at. In the checkout, every file changed since main is marked, and **Changed only** narrows the
  tree to them. A file tab has **Insert into composer**, which adds an `@path` mention.
- **Changes.** What changed in the checkout, file by file, with added and removed line counts.
  Switch between **Last turn** and **Since main**; select a file to see its diff. While a run is
  going, a line names the files it has changed but not yet committed.
- **Terminal.** Shells on the Hub's computer, started in the thread's checkout or the project root:
  PowerShell, Command Prompt, Git Bash or a WSL distribution on Windows, your login shell
  elsewhere. Up to four per thread, and they keep running while you are in another thread. You can
  send a selection of a shell's output into the composer. The terminal opens only on the computer
  the Hub runs on, never from another machine and not in Docker mode. The thread's runs can read
  its shells' recent output, but cannot type into them.
- **Watch.** Another thread, live and read-only. Pick the profile and, if it has several threads,
  the thread; the tab follows the profile into its next thread until you pick one by hand. A
  coloured mark says whether it is **working** (green, pulsing), **waiting for your answer**
  (amber) or **idle**. **Talk to** makes that thread the main view, keeping your unsent draft.
- **Running.** Every build, loop and job in the project, finished ones included, grouped by what
  needs you, what is working, what is scheduled and what has finished. **Answer** takes you to a
  waiting question; selecting a row opens the build, loop or job.

![A thread with the Watch tab open, following another profile while it works](../assets/screenshots/side-panel-watch-light.webp#only-light)
![A thread with the Watch tab open, following another profile while it works](../assets/screenshots/side-panel-watch-dark.webp#only-dark)

Open tabs, and the profile you are watching, are remembered per project. An open specification
document stays open as you move between threads.

## Context and checkpoints

The bar above the timeline shows how full this thread's context window is, for example
`57,230 / 1,000,000 · 5.72%`. It turns amber at 70% and red at 90%. The numbers come from what the
provider reports. If the provider reports nothing, the meter says *unavailable* rather than
guessing.

A long thread degrades. Rather than let one grow until it does, take a **checkpoint**:

1. **Checkpoint** in the conversation bar writes a record of where the work stands. The Hub fills
   in the facts it holds itself: files changed, tasks, open questions, decisions. A worker model
   writes the judgement part: objective, state, next actions, risks.
2. When it is ready, **Cut over** opens a successor thread titled *Continued: …*, hands it the
   checkpoint, and archives this one. A thread can be handed over only once. The successor of one
   of your threads is yours too, and stays in the sidebar before you write in it.

Projects can set checkpointing to **Offer me one** (the default, a banner at the threshold),
**Automatic**, or **Off**, under **Project settings → Checkpoints**. A profile can override that
in its own settings.

## Binding a thread to a task

Starting a profile on a task (from the task card's **Start … on this**) binds the run to that task.
The thread shows *Every turn here counts towards task …*, the task moves to *in progress*, and the
run works in the task's own worktree. **Work on something else** releases the binding.

## Archiving

**Archive conversation** in the **More** menu (with **Undo**) moves a thread out of the sidebar. It
stays readable under **Show archived**. Nothing in AgentWeave's history is deleted by archiving.
