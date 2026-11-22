---
description: Ask any agent a question about your project's data and get a dashboard that stays, and change it by asking.
---

# Dashboards

The app shows what it was built to show. For anything else (what each spec cost, why work comes
back, which runs fail, how often a word turns up in agent output), ask any agent:

> Make me a dashboard of what each agent cost this month, and which specs cost the most.

The agent writes queries over the current project's data, runs them to check the results, and
saves a dashboard. It appears on the project's **Dashboards** tab, drawn in the app's own charts.

![A dashboard an agent built: cost this week, cost per day and cost per agent](../assets/screenshots/dashboard-light.webp#only-light)
![A dashboard an agent built: cost this week, cost per day and cost per agent](../assets/screenshots/dashboard-dark.webp#only-dark)

## What a dashboard is

A name, the question it answers, and panels. Each panel is a query and one of five chart kinds:

| Kind | For |
|---|---|
| **Number** | One figure: cost this week. |
| **Bar** | A ranking or comparison: cost per agent. |
| **Stacked bar** | Parts of a whole across labels: send-backs per model, by reason. |
| **Line** | Change over time: cost per day. |
| **Table** | Detail rows: the latest failed runs. |

Opening a dashboard runs its queries; **Refresh** runs them again, and the screen says when the
data was last fetched. A panel whose query fails shows the error on that panel, and the rest still
draws. Hovering a bar or a point shows its value.

## What a query can read

Everything the project records: tasks and their moves, runs and what they cost, agent output,
traces, messages, questions, specifications, evidence, the vault. Free text is searchable,
including with regular expressions.

A query is limited, whatever it says:

- **This project only.** No row from another project is ever returned.
- **Read-only.** Anything that would change data is refused.
- **No secrets or paths.** API keys, credentials, run tokens and this machine's paths are not
  queryable.
- **Bounded.** A query is stopped after 10 seconds, and a result is cut at 10,000 rows.

Agents read a reference of every table and column, generated from the running Hub, and a vault
note on what the data means and where a plain count gives the wrong answer. When an agent learns a
new trap, it adds it to that note.

## Changing a dashboard

Ask an agent to change it, by name, or use **Ask to change** on the open dashboard, which opens a
conversation with the request ready to edit:

> Add a panel for cost per agent to "Build health".

The agent changes that dashboard in place, and only what you asked for. If the name you give fits
no dashboard or several, it asks which rather than guess. **Undo** restores the version before the
last edit, and undoing again restores what was undone. The screen shows who last edited the
dashboard and when.

**Delete** removes a dashboard. Deleting a project removes its dashboards.

## The landing dashboard

Every project is given one dashboard of its own, **Landing time and flaky tests**. It answers how
long approved work waits and is checked before it [lands](tasks-and-review.md#slow-checks-run-once-per-landing),
and which tests flake. Its panels are:

- **Landing batches, newest first**: for each batch, how long it waited (from the earliest task being
  ready to land until its checks held a slot), how long its checks took, how many check runs it made
  and its outcome.
- **Median landing check time**, over the last 20 batches.
- **Landing check time over time**, as a line.
- **Ten flakiest tests**.

A batch that landed before these times were recorded shows *not recorded*, never 0. The dashboard is
an ordinary one, so you can change it by asking, or delete it.
