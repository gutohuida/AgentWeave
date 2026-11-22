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
| **Overview** | What needs you, what is running, what recently merged, and each profile's state and spend. A new project's setup list is here too, including the offer to add a builder and a checker. |
| **Tasks** | The task board, by status, and a dependency view. The tab's badge counts tasks waiting for review. See [Tasks and review](tasks-and-review.md). |
| **Spec** | Specification documents, their coverage, evidence and history. See [Specifications](specifications.md). |
| **Vault** | The project's knowledge vault. See [Knowledge vault](knowledge-vault.md). |
| **Jobs** | Scheduled jobs, loops and flows. See [Jobs, loops and flows](jobs-loops-flows.md). |
| **Activity** | The project **ledger** (spend, merges, divergences), a readable activity digest, and raw logs. See [Traceability](traceability.md). |

### Overview

The Overview answers four questions at a glance:

- **Needs you.** Questions runs have asked you, which you can answer inline, and tasks that were
  approved but not merged.
- **Running now.** Which profile is working on what.
- **Recently finished.** Merges into your main branch, and who approved each one.
- **Profiles.** Each profile's status, for example *Working on "…"*, *Waiting for your answer* or
  *No runner yet*, with its spend so far and the grants it holds. Its card opens its settings.

## Threads

Opening a thread shows the timeline, the composer, and an optional side panel with specs, files,
the run's changes, a terminal, another thread live, and everything running in the project. That
is where most of the work happens. See [Threads](conversations.md).

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
| **Checkpoints**, **Spec steps**, **Traces** | Checkpointing, custom spec steps, trace export. |
| **Manager** | Background jobs the Hub runs with a model: conversation titles, vault distillation, vault reports, the spec vault check. Each is off until you turn it on and pick a runner. |
| **Runners** | The CLIs runs use: Claude Code, Codex, GitHub Copilot. A profile's pool is drawn from them. |
| **Charters** | What each profile is accountable for. |
| **Instructions** | Rules every profile in this project reads at the start of a session, before its charter. |
| **Budgets** | Spend and tokens so far, an optional token limit that pauses autonomous work, and the agent budget. |
| **Worktrees** | Every profile, thread and task checkout, and any conflicts between them. |
| **Diagnostics** | Counts and raw status, with a **Copy status** button for bug reports. |

<figure class="aw-shot" markdown>
![Project settings, General section: collaboration, reach, integration and checkpointing](../assets/screenshots/project-settings-light.webp#only-light)
![Project settings, General section: collaboration, reach, integration and checkpointing](../assets/screenshots/project-settings-dark.webp#only-dark)
</figure>

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
