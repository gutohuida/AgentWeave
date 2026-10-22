---
description: The handful of things AgentWeave is made of, and how one piece of work moves through them.
---

# How it fits together

AgentWeave has a small vocabulary. This page defines each term once and shows how one piece of
work moves through them. Every other page assumes it.

## The pieces

**The Hub**
:   The one local process that runs everything. It owns the database, launches agent runs, enforces
    the rules, and serves the app. One Hub serves many projects. `agentweave` starts it, or reopens
    it if it is already running.

**Project**
:   A directory on your disk, usually a git repository. A project keeps its own agents,
    conversations, tasks, specifications and settings. The folder is bound to its project by a small
    marker file, `.agentweave/project.json`, so renaming or moving the folder never merges two
    projects by accident.

**Runner**
:   How an agent is executed: one of the CLIs **Claude Code**, **Codex** or **GitHub Copilot**,
    optionally with a model. Every project starts with one default runner per CLI. The Hub uses the
    sign-in the CLI already has.

**Agent**
:   A named worker in one project, such as `planner`, `builder` or `reviewer`. An agent has one
    runner, a model, and optionally a **charter**. Its name is the attribution on everything it
    produces, so agents are archived, never deleted.

**Charter**
:   A short Markdown text that states what an agent is answerable for and where its authority ends.
    It is injected into every turn the agent takes. New projects are seeded with starter charters:
    Tech Lead, Developer, Code Reviewer, Verifier and others.

**Conversation** and **run**
:   You talk to an agent in a conversation. Each message you send starts a **run** (a turn): the Hub
    launches the CLI, streams what it does into the conversation, records its usage, and records how
    it ended. A conversation can also be started by another agent, a scheduled job, or a loop.

**Specification document**
:   A structured document in `spec/` that says what to build: requirements with scenarios, the
    tasks that will deliver them, and how the work will be delivered. Agents can draft one, but only
    you **approve** it. Approving a change creates its tasks.

**Requirement**
:   One statement in a specification, such as *"tax rounds half-up to the cent"*. The Hub gives
    each requirement a stable identifier (`FR-2`) and tracks its **coverage**: whether any evidence
    shows it is satisfied, and whether that work has merged.

**Task**
:   One unit of work, usually serving one or more requirements. A task moves through a fixed
    [lifecycle](../reference/task-lifecycle.md). In a git project it gets its own **worktree** and
    branch.

**Evidence**
:   A record an agent makes to show that a requirement holds: the command it ran, the output, and
    the commit it ran against. Evidence is reviewed, and accepted evidence is what approval merges.

**Review and approval**
:   A finished task is reviewed, by you or by an agent that did not write it. Approving a task
    **merges its work into your main branch**, locally, in the same step. Nothing is pushed.

**Job**, **loop** and **flow**
:   A job sends an agent a message on a schedule. A loop is a job with a purpose and a stop
    condition, working through a queue of tasks. A flow is a loop bound to an approved specification:
    it picks the tasks and the agents, and has each finished task reviewed by a different agent.

**Knowledge vault**
:   A per-project library of meeting transcripts, rules, decisions and reference documents. Agents
    see it on every turn and read what their work needs.

## One piece of work, end to end

A change starts as a conversation and ends as a merge, and the same thread runs through every step:

--8<-- "red-thread.html"

1. **You ask for a change.** You describe it to an agent, here `planner`, and it drafts a
   specification document. Requirements get identifiers (`FR-1`, `FR-2`, …) and scenarios say how
   each one will be checked.
2. **You approve the specification.** The Hub lists any gaps first, such as a scenario with nobody
   named to check it. You fix them or approve anyway, and either way the decision is recorded.
   Approval creates the document's tasks, with their dependencies.
3. **An agent takes a task.** The run is bound to that task, in the task's own worktree and branch.
   The agent implements it, runs the tests, commits, and records **evidence** against the
   requirement.
4. **Someone else reviews it.** The author cannot approve its own work. A reviewer, an agent or you,
   reads the requirement and the evidence and runs the checks. It then approves the task or sends it
   back with the reason.
5. **Approval merges.** Approving the task merges its evidenced commits into your main branch. The
   requirement now reads *verified* and *integrated*.

Every step is attributed. The task's **story** shows who moved it and when, every run with its
transcript and trace, the evidence with its command and output, and the merge commit. The
requirement's own story shows how its wording changed and what proved each version. See
[Traceability](../guides/traceability.md).

## Who decides what

AgentWeave keeps a clear line between what agents may do and what only you may do:

| Only you | Agents, through their tools |
|---|---|
| Approve, archive or retire a specification | Draft and edit change specifications |
| Set a document's rigor | Record evidence for a requirement |
| Configure checks, the main branch and budgets | Create tasks, move their own tasks, send messages |
| Overturn a decided piece of evidence | Accept or reject someone else's evidence, if granted |
| Create agents and edit charters | Request a new agent modelled on an existing one, within a budget |
| Answer questions and permission requests | Ask you questions and wait for the answer |

An agent's identity comes from its run's credential, never from anything it writes in a request.
An agent cannot claim to be someone else, and it cannot approve its own work.
