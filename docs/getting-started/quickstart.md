---
description: From an empty project to an approved, merged change, in one sitting.
---

# Your first project

This walkthrough takes a small project from nothing to one merged change. It uses three agents:
one plans, one builds and one reviews. The screenshots come from doing exactly this on a small
invoicing service. It takes about fifteen minutes, most of it the agents working.

You need AgentWeave [installed](installation.md) and at least one agent CLI signed in.

## 1. Open the project

```bash
cd ~/code/northwind-invoicing
agentweave
```

The app opens on the project's **Overview**. Your projects are listed in the left rail, and each
one expands to show its agents and their conversations. Across the top are the project's tabs:
**Overview, Tasks, Spec, Vault, Jobs, Activity**. The gear on the right opens the project settings.

!!! tip "Set the main branch"
    Open **Project settings → General → Integration** and check that **Main branch** names the
    branch approved work should merge into. AgentWeave adopts the repository's current branch when
    it opens a project. You can also add **Checks** there, such as `pytest -q`. Approval is then
    refused until the checks pass on the merged result.

## 2. Add three agents

Click **+** next to the project in the rail (**Add agent**). An agent needs a name, a provider, a
model, and optionally a charter:

| Name | Provider and model | Charter |
|---|---|---|
| `planner` | Claude Code · Sonnet | Spec Author |
| `builder` | Claude Code · Sonnet | Developer |
| `reviewer` | Claude Code · Sonnet | Code Reviewer |

<figure class="aw-shot" markdown>
![The Create agent dialog with name, provider, model and charter](../assets/screenshots/create-agent-light.webp#only-light)
![The Create agent dialog with name, provider, model and charter](../assets/screenshots/create-agent-dark.webp#only-dark)
</figure>

A provider whose CLI cannot launch is greyed out, with the reason. The Hub creates the matching
runner for you. Everything else, such as default permissions, timeouts and grants, lives in the
agent's settings, and the defaults are sensible.

## 3. Ask for a change

Open `planner` and describe what you want. Be concrete about the outcome, not the implementation:

> Two things for Northwind Invoicing. 1) The CSV export should end with a totals row: subtotal,
> tax and total for the invoice region. 2) Tax must round half-up to the cent, per region. Please
> author a short change specification with requirements and scenarios, then the tasks for the
> builder, ordered by dependency.

The planner reads the code and writes a **change specification** into `spec/changes/…/spec.json`.
The Hub gives each requirement a stable identifier (`FR-1` … `FR-4`). Open it beside the
conversation from the side panel's **Specs** tab, or on the **Spec** tab:

<figure class="aw-shot" markdown>
![A conversation with the planner, with the change specification it wrote open in the side panel](../assets/screenshots/conversation-spec-light.webp#only-light)
![A conversation with the planner, with the change specification it wrote open in the side panel](../assets/screenshots/conversation-spec-dark.webp#only-dark)
</figure>

If the agent needs a decision from you, it asks with a question card above the composer, and its
turn waits for your answer. Agents never guess at what you meant.

## 4. Check, approve and build

On the **Spec** tab, **Check** lists anything still missing, exactly as the agent sees it, and
moves nothing: the agent keeps writing while you read. **Approve** approves the version you read
(if the agent changed it since, the Hub says so and you reload) and lays the tasks out as a plan;
nothing starts. **Build…** then starts building it the way the document recommends, now or later,
and **Approve and build…** does both at once. If the Hub found gaps, for example a scenario with
nobody named to check it, approving lists them first. You can fix them, or press
**Approve anyway**. The gaps you overrode are recorded on the document.

<figure class="aw-shot" markdown>
![The approval panel listing gaps, with an Approve anyway button](../assets/screenshots/approve-anyway-light.webp#only-light)
![The approval panel listing gaps, with an Approve anyway button](../assets/screenshots/approve-anyway-dark.webp#only-dark)
</figure>

Agents can draft and edit a specification, but only you can approve it. An agent asked to build
from an unapproved specification says so and stops.

## 5. Build

Open **Tasks**. Approval put the document's tasks on the board, in dependency order. Hover over a
card and choose **Start builder on this**, or tell `builder` in its conversation to take the task.

The builder works in the task's own worktree (`.agentweave/tasks/<task-id>`, on branch
`agentweave/task/<task-id>`). It implements the change, runs the tests, commits, and **records
evidence** against the requirement: the command, its output, and the commit. Then it moves the
task to *completed*.

<figure class="aw-shot" markdown>
![The task board with tasks in Pending, Completed and Approved](../assets/screenshots/tasks-board-light.webp#only-light)
![The task board with tasks in Pending, Completed and Approved](../assets/screenshots/tasks-board-dark.webp#only-dark)
</figure>

A task that depends on another cannot start until its prerequisite is **approved**. Completed is
not enough.

## 6. Review and merge

Ask `reviewer` to review the task. A review turn gets a clean checkout of exactly the commit the
evidence names. It runs the tests, decides the evidence, and
either approves the task or sends it back with the reason. The builder cannot approve its own work.

**Approving merges.** The task's evidenced commit is merged into your main branch, locally, in the
same step, and nothing is pushed. If the merge would conflict, approval is refused and names the
files. Open the task to see its whole **story**:

<figure class="aw-shot" markdown>
![A task's story: state, cost, runs, evidence and the merge, in time order](../assets/screenshots/task-story-light.webp#only-light)
![A task's story: state, cost, runs, evidence and the merge, in time order](../assets/screenshots/task-story-dark.webp#only-dark)
</figure>

```console
$ git log --oneline main
ab4099c Integrate approved work 747084df7cea
747084d Round tax half-up to the cent (FR-2)
888d46d Initial invoicing service
```

## Where to go next

- [The app](../guides/the-app.md): every screen, and what it is for.
- [Specifications](../guides/specifications.md): the authoring journey, rigor, and folding a
  shipped change into current behaviour.
- [Jobs, loops and flows](../guides/jobs-loops-flows.md): let a flow work through an approved
  specification on its own, with every task reviewed.
- [Permission postures](../reference/permission-postures.md): what an agent may do before it has
  to ask you.
