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

Per-agent chat interface with session management:

- **Session Selector**: Choose between previous sessions or start a new chat
- **Chat History**: Full conversation history per session
- **New Chat**: Start a fresh conversation while preserving history

Each agent maintains separate conversation sessions. Use the session selector to:
- Continue a previous conversation
- Start a new chat for a different topic
- Review historical interactions

### Jobs

View and manage scheduled recurring tasks:

- **Jobs list** — all scheduled jobs with cron expressions and next run times
- **Job history** — recent execution results and status
- **Toggle controls** — enable or disable jobs directly in the UI
- **Manual trigger** — run a job immediately outside its schedule

### Agent Cards

Connected agents are auto-discovered from your session. Each card shows:

- Agent name and roles (as badges)
- Runner type (native, claude_proxy, or manual)
- Yolo mode status
- Quick actions: Chat, View Activity

## Tips

- Keep the dashboard open in a separate tab while agents are working
- Use the tasks board to track progress without reading every message
- Answer human questions promptly — agents may be waiting for your input before continuing
- Check agent output logs when debugging issues
- Use per-session chat to maintain separate conversation threads with each agent
