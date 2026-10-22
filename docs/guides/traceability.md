---
description: How to answer "who made this, and why?" — task stories, requirement stories, evidence, traces, the ledger and usage.
---

# Traceability

*Nothing appears out of thin air.* For anything an agent produced, AgentWeave can tell you who
made it, on whose instruction, against which requirement, with what proof, at what cost, and who
approved it. This page shows where each of those answers lives.

## Start from the work: the task story

Open any task and its **Story** is the whole history, in time order, cause before effect:

- who created it, and from which specification;
- every status move, with **who** made it (you, an agent, or the Hub itself), from which run, and
  why;
- every run that worked on it, with model, duration, tokens and cost, and links to its
  **conversation** and its **trace**;
- every piece of evidence: the summary, the command and output (**Show the proof**), and the
  reviewer's verdict with its reasoning;
- checks, questions asked of you, divergences, and the **merge**: which commit landed on which
  branch.

A strip at the top sums it up: state, cost, runs, evidence, and the merged commit.

<figure class="aw-shot" markdown>
![A task story: created by planner, two builder runs, a resolved divergence, evidence accepted by reviewer with its reasoning, merged into main](../assets/screenshots/task-story-light.webp#only-light)
![A task story: created by planner, two builder runs, a resolved divergence, evidence accepted by reviewer with its reasoning, merged into main](../assets/screenshots/task-story-dark.webp#only-dark)
</figure>

## Start from the intent: the requirement story

On the **Spec** tab, every requirement opens to its story:

- **How it changed.** Each wording it has had, as word-level diffs, with who changed it and when.
- **Evidence.** What proved it, for which wording.
- **Tasks.** What served it.
- **Drift.** Whether the files its evidence was about have changed since.

The evidence is tied to the exact wording it proved. When a requirement is reworded, old evidence
becomes *stale*, and it never silently counts for the new statement.

## Start from the code: commits

Every merge AgentWeave makes is an ordinary git commit on your main branch (*Integrate approved work
747084df…*), made by `AgentWeave <agentweave@localhost>`. The commit it merges is the one the
accepted evidence names. From a commit you can find the task, and from the task, everything above.

## What one turn did: traces

Every agent turn is recorded as a **trace**: a waterfall of the run, its model calls, tool calls,
permission waits, questions to you, and message deliveries, each with its timing and attributes.
Open it from the **trace** button on a turn, a run in a task story, or **Trace of the last turn**
in a conversation's menu.

The Hub's own work, such as API requests and background jobs, is traced too, with content
redacted. Under **Project settings → General → Traces** you can download traces as OTLP JSON, or
send them to your own OpenTelemetry collector. Export is off by default.

## What the project did: the ledger

**Activity → Ledger** is the project's account book, built only from what the Hub recorded:

- **Spent**: dollars (an API-equivalent estimate, where the runner reports one) and tokens;
- **Merged into main**, and anything approved but skipped;
- **Divergences**: runs that ended without doing what they were bound to;
- **Tasks**, by where they came from;
- spend by day, by agent and by task, and the messages between agents.

<figure class="aw-shot" markdown>
![The ledger: spent, merged into main, divergences and tasks, with spend by day, agent and task](../assets/screenshots/ledger-light.webp#only-light)
![The ledger: spent, merged into main, divergences and tasks, with spend by day, agent and task](../assets/screenshots/ledger-dark.webp#only-dark)
</figure>

**Activity → Activity** turns the same record into one readable sentence per event, grouped by
day. **Activity → Logs** has the raw logs, filterable by severity and category.

## Usage, honestly

- Every run records its usage as **measured** (from what the provider reported) or
  **unavailable**. Unavailable is never shown as zero.
- Money is never computed from a price list. A cost the runner reports is labelled an
  *API-equivalent estimate*.
- Copilot **AI credits** and premium requests are kept in Copilot's own units, never converted to
  money.
- The Hub's own background model calls (titles, checkpoints, vault work) are counted, and shown
  as *by the Hub*.

## Identity is never self-declared

All of this holds only because attribution cannot be forged. Each run gets its own short-lived
credential, and the Hub decides who is acting from that credential alone. Nothing an agent writes
in a request can change who it is. An agent cannot approve its own work, decide its own evidence,
or move a specification's phase.
