# Using the Dashboard

The AgentWeave Hub includes a web dashboard at **http://localhost:8000** that gives you real-time
visibility into every registered project and its agents.

## Projects and navigation

The left rail is a live collection of registered projects and their agents. Selecting a project
opens project-scoped content tabs: **Overview**, **Tasks**, **Spec**, **Jobs**, **Activity**, and
**Environment**. The browser URL records the selected project, view, agent, and AgentWeave
conversation, so reload and back/forward navigation restore the same destination.

Use the project controls in the rail to open an existing directory or explicitly create and
register a new one. A missing or moved project remains visible; use **Locate** in Environment
settings to rebind it without losing history. In Docker, submitted paths must be container-visible
below the configured mounted workspace root.

## Dashboard Sections

### Overview

The main landing page showing:

- Agent health grid with status and context usage
- Task summary with status counts
- Recent activity ticker
- Unanswered questions interrupt card
- Quick navigation to any section

### Tasks Board

All tasks with status, priority, assignee, requirements, acceptance criteria, and deliverables. Click any card to expand and see full details.

Tasks are organized in a Kanban-style board by status:
- **Pending** → **Assigned** → **In Progress** → **Under Review** → **Completed** → **Approved** → **Revision Needed**
- Rejected tasks are shown in a collapsible section

### Messages Feed

Inter-agent messages with expand-to-read for long content. The message type and linked task are shown inline.

### Human Questions

Questions agents have asked you. Answer directly in the dashboard without switching to your terminal.

### Activity

Live event stream and per-agent output log. See what each agent is doing in real time.

The Agent Activity panel includes:
- **Activity Tab**: Live event stream from all agents
- **Output Tab**: Real-time console output from agent sessions
- **Info Tab**: Agent configuration, roles, and runner type

### Agent Chat

Each agent owns durable **conversations**, and you switch between them in the left rail rather than
from a selector inside the chat — the rail lists every agent's conversations, and each one is a
place you can return to.

- **Conversation list** — grouped by agent, or flattened into a recency view for scanning across
  agents. A conversation waiting for you is marked on its row, so you can see it without opening it.
- **Timeline** — operator input, the agent's own output, and agent-to-agent traffic in both
  directions, each placed by its recorded association rather than inferred from timestamps.
- **Composer** — sets the model, the reasoning effort and the permission posture for the next
  message, and shows how full *this* conversation's context is.
- **Checkpoint** — writes a record of where the work stands so it can continue in a fresh
  conversation, rather than letting one thread grow until it degrades.

A conversation records where it came from: one you typed, one another agent started, or one a
scheduled job or loop firing created.

### The side panel

A conversation can open a panel beside it, hosting one tab at a time. The plus affordance offers
whatever is not already open:

- **Specs** — browse specification documents; opening one gives it its own tab, keyed by document
  id so it survives a rename.
- **Files** — the project's workspace tree. Opening a file replaces the tree tab: the tree is a
  launcher, and in a narrow column a tab spent on the thing that only got you here is a tab wasted.
- **Loops** — a project-wide glance at every loop. Opening one gives it a tab of its own, and the
  index stays open beside it.

Which tabs you have open is remembered per project; the panel's width is a single preference shared
across all of them. Closing the last tab closes the panel and returns the full width to the
conversation.

### Jobs and loops

View and manage scheduled recurring work:

- **Jobs list** — all scheduled jobs with cron expressions and next run times
- **Job history** — recent execution results and status
- **Toggle controls** — enable or disable jobs directly in the UI
- **Manual trigger** — run a job immediately outside its schedule

A job with a stated purpose and a stop condition is a **loop**, and it gets more than a job does.
Its drill-down tab shows the purpose, the stop condition, the queue by status, the item claimed
right now, open questions, and the firing history — plus a live indicator while a firing is in
progress.

Because every firing opens a *new* conversation, an active loop would otherwise fill an agent's
conversation list with threads you never started. Two things prevent that:

- A conversation created by a firing **names the loop it came from**, and clicking that name opens
  the loop's own tab. A plain scheduled job's conversation shows nothing — it has no loop.
- **Consecutive firings of one loop collapse into a single expandable row.** A firing waiting for
  you still says so on the collapsed row, and the row opens itself if it holds the conversation you
  are reading.

Editing a running loop is safe: the edit is **staged**, not applied. The loop tab shows each staged
value beside the one still in force, labelled "In force now" and "From the next firing", and a
firing already running keeps the definition it was briefed with.

Neither a job nor a loop can be deleted — both are archived, so the record of what ran survives. A
loop that is still running cannot be archived at all.

### Agent Cards

Connected agents are auto-discovered from your session. Each card shows:

- Agent name and status
- The bound runner and the model it resolves to
- How full its context is, as a compact bar
- Its most recent status message, when it has one

Roles are gone — an agent's behaviour comes from the **charter** bound to it, and its execution
capability from the **runner** bound to it. Permission posture is set per run from the composer,
not as a property of the agent.

## Tips

- Keep the dashboard open in a separate tab while agents are working
- Use the tasks board to track progress without reading every message
- Answer human questions promptly — agents may be waiting for your input before continuing
- Check agent output logs when debugging issues
- Use per-session chat to maintain separate conversation threads with each agent
