---
description: A tour of the AgentWeave app — the rail, the project tabs, settings, search and shortcuts.
---

# The app

Everything you do in AgentWeave, you do in the app the Hub serves at `http://localhost:8000`. This
page is the map: what each part of the screen is for, and where things live.

<figure class="aw-shot" markdown>
![The app: the sidebar on the left with projects, builds and threads; project tabs across the top](../assets/screenshots/overview-light.webp#only-light)
![The app: the sidebar on the left with projects, builds and threads; project tabs across the top](../assets/screenshots/overview-dark.webp#only-dark)
</figure>

## The sidebar

The sidebar on the left holds your **projects**, and under each project two lists: the **builds**
that are running or need you, and your own **threads**, each labelled with its profile. It holds
nothing else: there is no list of profiles, and the runs that served a task, a job or another
profile are reached through their build, flow or profile, not here. See
[Threads](conversations.md#the-sidebar).

- A project row offers **+** (a new profile) and **Project settings** (gear). If its folder has
  gone missing, it says *Directory unavailable*.
- **Builds** lists the builds needing you first (*Stopped*, *Stalled*, *Given up*, *Question*),
  then the running ones. Choosing one opens its build view. One that is not running can be
  dismissed with its **×**: it leaves the list, and a new stall, question or stop brings it back.
- **Threads** lists the threads you started or wrote in, those waiting for you first, then by
  most recent activity. **New thread** in its header asks which profile to talk to. Archived threads
  are behind **Show archived**.
- **Add project** at the bottom opens any folder. If the folder is already an AgentWeave project it
  opens. If not, it becomes one.

The sidebar can be resized or collapsed, and it remembers both. Collapsed, it shows the projects
only, and a project with a build that needs you carries a mark.

## Project tabs

Across the top, for the selected project:

| Tab | What it is for |
|---|---|
| **Overview** | The project at a glance, on two tabs: **Dashboard** and **Briefing**. A new project's setup list is here too, including the offer to add a builder and a checker. |
| **Tasks** | The task board, by status, and a dependency view. The tab's badge counts tasks waiting for review. See [Tasks and review](tasks-and-review.md). |
| **Profiles** | The project's profiles, each with its status and settings. |
| **Spec** | Specification documents, their coverage, evidence and history. See [Specifications](specifications.md). |
| **Vault** | The project's knowledge vault. See [Knowledge vault](knowledge-vault.md). |
| **Dashboards** | Charts a profile built from the project's data. See [Dashboards](dashboards.md). |

There is no Jobs, Activity, Checkpoints or Chapters tab. What they held lives where you already
work: **Jobs**, **Logs**, **Traces** and **Budgets** (which holds the ledger) are sections of
[Project settings](#project-settings); a thread's traces and checkpoints open in its side panel;
and **Chapters** is a link on the Overview. An old link to one of those tabs opens its new home.

At the right of the top bar, the **manager indicator** appears with a spinner and a count while
the Hub's background manager jobs are running. See [Manager work you can see](#manager-work-you-can-see).

### Overview

The Overview has two tabs, **Dashboard** and **Briefing**, that show the same picture from the same
data. Drag a tab to put it first: the first tab is the one the Overview opens on. The order and the
tab you last opened are remembered per project. Everything on either tab opens what it is about:
the thread, task, build, request, check or setting.

The **Dashboard** opens with a **health band**: one level, *Healthy*, *Needs you* or *Trouble*, and
one sentence naming every cause. *Trouble* is a failing or held main, or spend at 90% or more of
the token budget. Below it:

- **Needs you.** Everything waiting on you: open questions, tasks waiting for your review, pending
  permission requests, approved work that did not land, stalls, main trouble, checks that could
  not run, next-slice offers and reopening warnings. Each item says where it came from and how
  long it has waited.
- **Tiles.** **Main** (*Failing*, *Held*, *Unknown* or *Green*), **spend** (today and the last 7
  days, in dollars where turns are priced and in tokens or credits where they are not; a day that
  could not be priced shows as unknown, never zero), **running now** and **finished today**.
- **Running now** and **builds in progress**: which profile is working on what, how long it has been
  running, and each build's tasks done out of the total.
- **Finished today**, as a timeline with each item's outcome (landed, sent back, failed or
  stopped), time and cost.

The **Briefing** says the same in sentences: a headline matching the health band, what finished
since you last looked, who is working on what, what needs you and the builds in progress. The Hub
records when you last opened the Overview, so *since you last looked* counts from your previous
visit. The Briefing also carries a short **note** written by the **Overview note** manager job:
what changed since your last visit and anything that looks wrong, such as a build that has stopped
moving. It is written when a new visit starts more than 30 minutes after the last and something has
changed, and whenever you press **Refresh note**; never on a timer. If it cannot be written, the
Briefing says why and keeps the previous note. The job is off until you turn it on under
**Project settings → Manager**.

Links on the Overview reach the project's **Chapters**, the **Known failing tests** and
**Quarantined tests** lists, and each profile's status.

## Threads

Opening a thread shows the timeline, the composer, and an optional side panel with specs, files,
the run's changes, a terminal, another thread live, and everything running in the project. That
is where most of the work happens. See [Threads](conversations.md).

The side panel has its own toggle button in the thread's bar, and ++ctrl+alt+b++ (++cmd+option+b++
on macOS) shows or hides it, even with the cursor in the composer. **Trace of this thread**, **Trace
of the latest run** and **Checkpoints (N)** open as tabs in the panel, so you stay in the thread.
Close them like a spec or loop tab.

## Dashboards

The **Dashboards** tab holds charts any profile built from the project's own data when you asked it
a question. See [Dashboards](dashboards.md).

## Project settings

The gear in the top bar opens the project's settings:

| Section | What it holds |
|---|---|
| **Project** | The project's name and folder. |
| **Collaboration** | Hop budget, deliveries per turn, whether agents may start jobs, flows and loops, and **Profiles run in parallel**. |
| **Permissions** | Default permissions and granted reach. |
| **Checks** and **Landing** | **Main branch** and **Checks** (the quality gate on approval), and how approved work lands. |
| **Checkpoints**, **Spec steps** | Checkpointing and custom spec steps. |
| **Manager** | Background jobs the Hub runs with a model: conversation titles, vault distillation, vault reports, the spec vault check, thread chapters, the build retrospective, the pre-mortem, the Overview note and the mender. Each is off until you turn it on and pick a runner. Its **run log** lists what they did. |
| **Jobs** | The project's scheduled jobs, loops and flows. See [Jobs, loops and flows](jobs-loops-flows.md). |
| **Traces** and **Logs** | **Traces** is the project-wide trace view and the trace export settings. **Logs** is the raw event stream, with filtering and pausing. See [Traceability](traceability.md). |
| **Runners** | The CLIs runs use: Claude Code, Codex, GitHub Copilot. A profile's pool is drawn from them. |
| **Charters** | What each profile is accountable for. |
| **Instructions** | Rules every profile in this project reads at the start of a session, before its charter. |
| **Budgets** | Spend and tokens so far, an optional token limit that pauses autonomous work, the agent budget, and the project's **ledger** (what it did and spent). The Overview's spend tile opens it. |
| **Worktrees** | Every profile, thread and task checkout, and any conflicts between them. |
| **Diagnostics** | Counts and raw status, with a **Copy status** button for bug reports. |

<figure class="aw-shot" markdown>
![Project settings, General section: collaboration, reach, integration and checkpointing](../assets/screenshots/project-settings-light.webp#only-light)
![Project settings, General section: collaboration, reach, integration and checkpointing](../assets/screenshots/project-settings-dark.webp#only-dark)
</figure>

## Manager work you can see

Every manager job, and the mender, announces when a run starts and when it ends, and every open
view of the project learns of it within a few seconds, with no reload.

- **On the item.** A small manager icon appears on what a run works on, spinning while it runs: a
  spec's vault warnings, the Vault page, a spec's build retrospective. When the run ends, the item
  shows its product. If a run fails, the icon shows the failure and keeps showing it, across
  reloads, until you have opened the item's warning list or hovered the top-bar indicator while the
  failure is listed there, or the same job runs again.
- **In the top bar.** The manager indicator shows how many runs are in progress, titles and the
  mender included. Hover or click it for a popover of each run in progress (job, subject, elapsed
  time) and the latest that ended. Each row leads to that run in **Project settings → Manager**.
- **The run log.** **Project settings → Manager** lists the latest runs of every job, newest first:
  job, subject, trigger, automatic or manual, start, duration, outcome, the reason for a failure,
  and cost (or why there is none). Narrow it to one job; each job shows its runs, failures and
  total cost. A mender run is listed with its stall and links to its thread.

A thread a flow, build or the mender starts is titled when it is created, for example *Builder ·
work turn 2: Add tax rounding*, with no model call. Threads you start keep the **Conversation
titles** job.

## App settings

The gear at the foot of the sidebar opens **App settings**, which belong to you on this Hub and not
to one project: sound and notifications, appearance (light or dark), and **Hub connection**. That page holds the
Hub's address and key, its version, **Updates** and what closing the window does. **Updates**, in the
app window only, shows when a newer release is available, with an **Update to *version*** button
and **Update automatically when I open AgentWeave**, which is on by default. The update saves a
copy of your database, upgrades, checks the new version is healthy, and puts the old version and
database back if it is not. A Hub run from a git checkout updates from its local master instead. See
[Installation](../getting-started/installation.md#the-app-updates-itself).

## Search and shortcuts

++ctrl+k++ (++cmd+k++ on macOS) opens search across the current project's profiles, tasks,
specification documents and threads.

| Keys | Where | Does |
|---|---|---|
| ++ctrl+k++ | anywhere | Search |
| ++ctrl+shift+k++ | conversation, Spec tab | Open a specification document |
| ++enter++ / ++shift+enter++ | composer | Send / new line |
| `@` | composer | Mention a file |
| `/` at the start of a line | composer | Commands, such as `/model` |
| ++1++ – ++9++ | a question card | Pick that option |
| ++ctrl+left++ / ++ctrl+right++ | a focused task card | Move it to the neighbouring column, if that move is allowed |
| ++ctrl+f++ | Vault | Search the vault |

## Links you can share

Every place in the app has a URL: a project tab, a document, a requirement, a thread, a
profile's settings section, a build. Reload, back and forward all land where you were. A link to a
thread or a requirement is a good way to point a colleague at exactly what you mean.

## Light and dark

The sun and moon button switches the theme. The app starts in light.
