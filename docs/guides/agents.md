---
description: Profiles — a role with a charter, grants, posture and a pool of runners and models, from which many runs start at once. Runners, charters, folding and project instructions.
---

# Profiles

A **profile** is a role in one project: *Developer*, *QA*, *Architect*. It is not a person who
takes one turn and then the next. It is a description of how work of that kind is done, and the
Hub starts a **run** from it whenever there is work for it: a message from you, a task in a build,
a review, a job firing. With parallel runs on, several runs of one profile go at the same time,
each on its own work, in its own thread and its own checkout.

A profile is made of:

- a **charter**: what it answers for and where its authority ends (optional);
- **grants**: what it may read and decide beyond its own work, all off by default;
- a **posture**: the [permissions](../reference/permission-postures.md) its runs get when nothing
  else chooses one;
- a **pool**: the runners and models it may run on, one of them the default.

The project's **instructions** apply to every profile. In the tools agents are given, and in the
API, a profile is still addressed by its name in parameters such as `to_agent`, `assignee` and
`agent`: those names did not change.

## Runners

A runner is how a run is executed. AgentWeave supports three agent CLIs:

| CLI | Notes |
|---|---|
| **Claude Code** (`claude`) | Runs with a pinned, project-local configuration. Your user-level plugins, hooks and skills do not load into agent runs. |
| **Codex** (`codex`) | Runs over Codex's app-server protocol. |
| **GitHub Copilot CLI** (`copilot`) | Version 1.0.81 or later. It also offers Gemini, Grok and other models through Copilot. It can send runs to an Anthropic-compatible endpoint with your own key ([below](#bring-your-own-key-copilot)). |

Every new project gets one default runner per CLI. AgentWeave uses the sign-in each CLI already
has. It does not store provider keys for Claude Code or Codex, and it never reads them. Check which
CLIs are usable with `agentweave doctor`. A provider that cannot launch is also greyed out, with
the reason, wherever you choose a runner.

Manage runners under **Project settings → Runners**. A runner has a name, a CLI (fixed once
created) and an optional model. Flags that would override the model or the permission posture,
such as `--model`, `--permission-mode` or `--dangerously-skip-permissions`, are refused. Those are
set per profile, per thread and per run instead.

### Bring your own key (Copilot)

A Copilot runner can send its runs to an Anthropic-compatible provider: a base URL plus the
**name** of an environment variable in the Hub's environment that holds the key. The Hub stores
only the variable's name, never the key, and scrubs the value from everything it records. The
runner is launchable only while that variable is set.

## A new project's builder and checker

A build needs two profiles: one builds each task, and a different one checks it. One profile never
checks its own work. A new project's setup list, on its **Overview**, therefore offers **Add a
builder and a checker**. **Add both…** opens one dialog for the two profiles. For each you give:

- a **name** (the dialog suggests *Builder* and *Checker*; the two must differ);
- a **runner**, from the project's runners;
- a **charter**, optionally. None is chosen for you: *No charter* is the starting value, and a
  profile without one still runs.

Nothing is created until you choose **Create both**, and then both are created together or, if the
Hub refuses one (a name already taken, say), neither is. Once you have used the offer, or dismissed
it, it leaves the setup list. With the two profiles in place you can approve a specification and
start its build without opening profile creation at all. See [Tasks and review](tasks-and-review.md).

## Creating a profile

Click **+** beside the project in the sidebar. You choose:

- **Name.** 1–32 letters, numbers, `-` or `_`. `user` and `operator` are reserved.
- **Provider** and **model.** The Hub creates or reuses the matching runner, and it becomes the
  default entry of the profile's pool.
- **Charter**, optionally.

<figure class="aw-shot" markdown>
![Creating a profile: name, provider, model and charter](../assets/screenshots/create-agent-light.webp#only-light)
![Creating a profile: name, provider, model and charter](../assets/screenshots/create-agent-dark.webp#only-dark)
</figure>

Creating a profile starts nothing. Its first run happens when you start a thread with it, or when a
build, job, loop, flow or another profile gives it work.

## The pool: what a profile runs on

A profile's **Running** settings list the **models it may run on**: each entry is a runner, a model
and an effort, and one entry is the **default**. Add an entry from the project's runners, make
another entry the default, or remove one the profile no longer needs.

Each run uses one entry of the pool, chosen in this order:

1. the entry you chose for this build, or for this thread in the composer;
2. the entry the specification recommended for the task;
3. the profile's default.

A choice outside the pool is refused, naming why. A thread is bound to the CLI it started on,
because one CLI cannot resume another's session: after its first turn, a thread can move only to
another entry on that CLI. See [Threads](conversations.md#starting-a-thread).

## Parallel runs

**Project settings → Collaboration → Profiles run in parallel** decides whether one profile may
have several runs going at once.

- **On:** a profile with free work starts a run for each piece of it. A flow of three independent
  tasks with one builder profile builds all three at the same time, each task in its own checkout
  and branch, and each run in its own thread. A thread you start gets its own checkout too.
- **Off** (the default): runs of the same profile queue behind one another, and a message to a
  profile that is already running waits until its current run ends.

Either way, each run is recorded on its own: its thread, its trace, its usage and how it ended.

## Profile settings

Open a profile's settings from the **More** menu in one of its threads, from the profile's card on the
project's **Overview**, or from any link that names one of its settings. The sections are:

| Section | What it holds |
|---|---|
| **Agent** | Name (renaming keeps the history), a description for you (agents never read it), its **charter**, **Fold into…** and **Archive**. |
| **Running** | Its pool (the models it may run on, and the default). How long a run waits for your permission decision (default 120 s) and for your answer to a question (default 240 s); when a wait runs out, the action is refused and the run moves on. On a Copilot profile, its review agents and GitHub server. |
| **Permissions** | Its posture, the default used when nothing else chooses one, including scheduled runs and messages from other profiles. **Own granted reach**. Its grants (below). |
| **Checkpoints** | Checkpointing for its threads: follow the project's setting, off, offer, or automatic, with its threshold, and the checkpoints already taken. |
| **Workspace** | Its working directory and isolation, its task checkouts, and its provider sessions. Read only. |
| **Runs** | Every run of the profile, newest first ([below](#a-profiles-runs)). |

<figure class="aw-shot" markdown>
![Profile settings: runner, default permissions and granted reach](../assets/screenshots/agent-settings-light.webp#only-light)
![Profile settings: runner, default permissions and granted reach](../assets/screenshots/agent-settings-dark.webp#only-dark)
</figure>

### Grants

All grants are off by default:

- read other profiles' checkpoints;
- recall what a checkpoint cites;
- **accept or reject evidence** (never its own);
- tidy the specifications.

### A profile's runs

The **Runs** section lists everything the profile has run, newest first: its threads, task builds,
reviews, mender turns, job firings and messages, and the runs of any name folded into it. Each row
shows the run's **kind** (*Thread*, *Task build*, *Review*, *Mender*, *Job* or *Message*), the task
it served if it served one, when it started, and how it ended (*Running*, *Completed*, *Failed*,
*Stopped*), as a word and a shape as well as a colour. Choosing a run opens its trace, which links
to its conversation. **Show older runs** reads further back.

This is where a profile's past work is found. The sidebar lists only your own threads and the
builds that are running or need you ([Threads](conversations.md#the-sidebar)); a run that served a
task is also reached from its build's view, and a run a flow started from the flow's page in
**Project settings → Jobs** ([Jobs, loops and flows](jobs-loops-flows.md#a-flows-runs)).

## Folding one profile into another

Projects tend to grow near-duplicates: *Developer*, *DeveloperOpus*, *DeveloperSonnet*, each the
same role on a different model. Now that a profile has a pool, one profile can hold all of those
models. **Fold into…** in a profile's **Agent** section merges it into another profile:

1. Choose the profile to fold into. The dialog shows, before anything changes, which settings
   differ between the two and which open work (tasks, builds, jobs, loops, flows) names the folded
   profile and will move.
2. Confirm. The folded profile is archived for good. Its open work moves to the profile you chose,
   and its pool entries join that profile's pool.

Folding cannot be undone. The folded name stays in history: its threads, runs and checkpoints stay
readable under it, it accepts no new turn, and it is counted with the profile it joined, in that
profile's **Runs** and in dashboards that group by profile.

## Archiving

**Profiles are archived, never deleted.** A profile's name is the attribution on every task,
message, commit and piece of evidence its runs produced. Archiving takes it out of task assignment,
messaging and the choice of profiles for a new thread, and keeps all of that history readable.
Archiving is refused while the profile has a run in progress or input still waiting.

## Charters

A charter is a Markdown text that says what a profile is answerable for and where its authority
ends: *"You review a finished task against its requirement and its evidence. You approve only what
you could verify by running it."* It is injected verbatim into every run. A profile without a
charter still runs, and its context says it has none.

Each new project is seeded once with starter charters: **Tech Lead, Developer, Code Reviewer,
Verifier, Security Engineer, Guardian, Spec Author**. Edit them, delete them, or write your own
under **Project settings → Charters**. A charter a profile still holds cannot be deleted.

## Project instructions

**Project settings → Instructions** holds one text that every profile in the project reads at the
start of a session, before its charter. Use it for the rules of the house: how to run the tests,
the branch conventions, what never to touch. A change applies when a run starts its next session.

## What a run is told

Before every run, the Hub assembles its context from its own records, in this order:

1. **The project and the run.** The workspace and branch, the task and its specification (if the
   run is bound to one), the team (the other profiles, their CLI and model), the quality checks,
   and which capabilities this profile holds or lacks.
2. **The project instructions.**
3. **How to reach the Hub.** The [tools](../reference/agent-tools.md), as MCP tools or through the
   `aw-tool` command.
4. **Its charter.**

When the project has a [knowledge vault](knowledge-vault.md), every run is also told how many
entries it holds and how to read them.

## Profiles creating profiles

A run may ask for a new profile modelled on an existing one, with `request_agent`. The new profile
copies the template's runner, charter and configuration. It inherits no grants and no posture. The
project's **agent budget** (default 8) caps how many profiles can be created this way. Raise it
under **Project settings → Budgets**. Creating one yourself is never limited.
