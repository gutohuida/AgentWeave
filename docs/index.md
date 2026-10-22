---
title: AgentWeave
description: Run your AI factory in the open. A local app where AI coding agents build against specifications you approve, and every artifact traces back to who made it and why.
hide:
  - navigation
  - toc
---

<div class="aw-home" markdown>

# AgentWeave

<div class="aw-hero" markdown>
<div class="aw-hero__mark"><img src="assets/agentweave-loop-on-dark.svg" alt="The AgentWeave loop"></div>
<div markdown>
<h1>Nothing appears out of thin air.</h1>
<p class="aw-hero__tagline">Run your AI factory in the open.</p>
</div>
</div>

<p class="aw-lede">AgentWeave is a local app where AI coding agents work on your projects together,
against specifications you approve. Every requirement, task, run, piece of evidence and merge is
recorded and connected, so for anything in your repository you can say who made it, and why.</p>

<div class="aw-cta" markdown>
[Get started](getting-started/quickstart.md){ .md-button .md-button--primary }
[How it fits together](getting-started/concepts.md){ .md-button }
[GitHub](https://github.com/gutohuida/AgentWeave){ .md-button }
</div>

```bash
pip install agentweave-ai
agentweave
```

<figure class="aw-shot" markdown>
![The AgentWeave app: a project overview with what needs you, what is running, what merged, and each agent's state](assets/screenshots/overview-light.webp#only-light)
![The AgentWeave app: a project overview with what needs you, what is running, what merged, and each agent's state](assets/screenshots/overview-dark.webp#only-dark)
</figure>

## Why it exists

AgentWeave began as a way to get agents from different companies working together, each doing
what it does best. Then the real problem showed. Work appeared out of thin air, and nobody could say
who made it or why. A tool that lets agents loose on a codebase, and leaves you to work out
afterwards what happened, does not give you control.

So AgentWeave became the place where you run the work in the open. Agents build from specifications
you approve. Each task runs in its own git worktree. Evidence is recorded against the requirement it
proves. Approval is a reviewed merge, and every step names who took it.

## One thread through everything

In Goethe's *Elective Affinities*, every rope of the Royal Navy is spun with a red thread, so any
piece of it can be traced back to where it was made. AgentWeave does the same for your software.
Here is one thread from a real project, followed end to end:

--8<-- "red-thread.html"

Each of those is a record you can open: the requirement's history, the task's story, the run's
transcript and trace, the evidence's command and output, the reviewer's verdict, and the commit
that merged.

## What you get

<div class="grid cards" markdown>

-   :material-file-document-check-outline:{ .lg } __Specifications you approve__

    ---

    Agents draft a change with requirements and scenarios. You propose it and approve it, and
    approving creates the tasks.

    [:octicons-arrow-right-24: Specifications](guides/specifications.md)

-   :material-source-branch:{ .lg } __Isolated, reviewed work__

    ---

    Each task gets its own worktree and branch. A different agent reviews it, and approving it
    merges it into your main branch.

    [:octicons-arrow-right-24: Tasks and review](guides/tasks-and-review.md)

-   :material-transit-connection-variant:{ .lg } __Traceability by default__

    ---

    Task stories, requirement histories, evidence with its command and output, per-turn traces and
    a spend ledger.

    [:octicons-arrow-right-24: Traceability](guides/traceability.md)

-   :material-account-group-outline:{ .lg } __Agents with a charter__

    ---

    Claude Code, Codex and GitHub Copilot agents, each bound to a runner, a model and a charter
    that says what it answers for.

    [:octicons-arrow-right-24: Agents](guides/agents.md)

-   :material-sync:{ .lg } __Loops that finish__

    ---

    Scheduled jobs, plus loops and flows with a purpose and a stop condition. Each one works a
    queue of tasks until the queue is done.

    [:octicons-arrow-right-24: Jobs, loops and flows](guides/jobs-loops-flows.md)

-   :material-shield-check-outline:{ .lg } __You stay in the loop__

    ---

    Agents ask you questions and wait for the answer. Permission postures decide what an agent may
    do before it has to ask.

    [:octicons-arrow-right-24: Conversations](guides/conversations.md)

</div>

## How it runs

AgentWeave is **one local process**, the Hub. It owns execution, state and identity, and it serves
the app you work in. It runs on your machine, against directories on your disk, using the agent
CLIs you have already signed in to. Nothing is hosted, and nothing is pushed anywhere unless you
push it.

- **You** work in the app: projects, agents, conversations, specs, tasks, jobs.
- **Agents** are the CLIs the Hub launches. Each run gets a short-lived credential and a fixed set of
  [tools](reference/agent-tools.md) for messages, tasks, questions, specs and evidence.
- **The CLI** only starts, checks, stops and resets the local app. It also adds files to a project's
  knowledge vault.

Read [How it fits together](getting-started/concepts.md) next, or go straight to the
[quick start](getting-started/quickstart.md).

</div>
