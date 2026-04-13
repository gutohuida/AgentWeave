# Using the Dashboard

The AgentWeave Hub includes a web dashboard at **http://localhost:8000** that gives you real-time visibility into everything your agents are doing.

## Dashboard Sections

### Mission Control

The main overview page showing:

- Session status and connected agents
- Recent activity summary
- Quick access to active tasks and unread messages
- Health indicators for all components

### Tasks Board

All tasks with status, priority, assignee, requirements, acceptance criteria, and deliverables. Click any card to expand and see full details.

Tasks are organized in a Kanban-style board by status:
- **Pending** → **Assigned** → **In Progress** → **Completed** → **Under Review** → **Approved**

### Messages Feed

Inter-agent messages with expand-to-read for long content. The message type and linked task are shown inline.

### Human Questions

Questions agents have asked you. Answer directly in the dashboard without switching to your terminal.

### Agent Activity

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

### AI Jobs

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
- Pilot mode indicator
- Quick actions: Chat, View Activity

## Tips

- Keep the dashboard open in a separate tab while agents are working
- Use the tasks board to track progress without reading every message
- Answer human questions promptly — agents may be waiting for your input before continuing
- Check agent output logs when debugging issues
- Use per-session chat to maintain separate conversation threads with each agent
