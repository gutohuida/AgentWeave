## Why

The AgentWeave Hub currently uses Material Design 3 (M3) as its visual foundation. While functional, M3 is immediately recognizable as a Google design system — it reads as a consumer app template rather than a focused developer tool. The tonal surface layering, pill-shaped nav indicators, and large border radii add visual complexity that competes with the actual content (live agent output, task status, log lines). The 2026 standard for developer tooling is a precise, monochromatic aesthetic — used by Linear, Vercel, Raycast, and Resend — that lets data and status be the visual signal, not the chrome around it.

## What Changes

- **Design tokens**: Replace all M3 CSS custom properties (`--primary`, `--p-cont`, `--on-p-cont`, `--s-cont`, `--surface-low/high/highest`, `--m-divider`, etc.) with a new Linear/shadcn token set built on near-black backgrounds and zinc/neutral grays. Dark mode becomes the primary mode; light mode remains available.
- **Navigation restructure**: Reduce from 9 flat nav items to 5 grouped sections in a 220px labeled sidebar (replacing the 80px icon-only rail). Groups: Overview · Agents · Work (Tasks + Jobs) · Communication (Messages + Questions) · Observe (Logs + Activity).
- **Agent page merge**: Collapse the separate "Agents" page and "Mission Control" page into a single unified Agents view. Left panel = agent list with status dots, tags, and inline task preview. Right panel = tabbed detail (Output / Tasks / Messages / Info).
- **Blocked-question interrupt**: When `questions.unanswered > 0`, render a persistent amber interrupt card inline at the top of the agent list (and as a dedicated card on the Overview page), not just a badge on a nav item.
- **Full kanban**: Expand the Tasks board from 4 columns to 7, covering the complete task lifecycle: Pending → Assigned → In Progress → Under Review → Completed → Approved / Revision Needed / Rejected.
- **Typography & spacing**: Switch to Inter (body) + JetBrains Mono (code/timestamps) with tighter spacing, 6–8px border-radius, and border-based depth (1px lines) replacing box-shadow elevation.
- **Status bar**: Slim the top status bar to flat chips on a dark background; remove the M3 "top app bar" treatment.
- **Semantic color**: All color usage becomes strictly semantic — green (running/ok), amber (waiting/warning), red (error/blocked), blue (primary action), purple (roles/tags). No decorative color.
- **Component rewrites**: Badge, AgentCard, TaskCard, Sidebar, StatusBar, AgentsPage, MissionControlPage (removed), MessagesFeed, QuestionsPanel, LogsView, ActivityLog.
- **New Overview page**: A new default landing page showing agent health grid, blocked-question interrupt, in-progress task count, and a live activity ticker at the bottom.

## Capabilities

### New Capabilities

- `hub-ui-design-tokens`: New CSS custom property token system replacing M3. Defines all colors, spacing, typography, radius, and semantic color aliases for the Linear/shadcn aesthetic.
- `hub-ui-navigation`: New 220px labeled sidebar with grouped sections, active left-border indicator, unread badges, and section labels.
- `hub-ui-agents-page`: Unified agent-centric page merging Mission Control + Agents. Agent list panel + tabbed detail panel with live output, per-agent tasks, messages, and info.
- `hub-ui-question-interrupt`: Persistent blocked-question interrupt card that surfaces unanswered questions at the top of the agent list and on the Overview page, replacing badge-only treatment.
- `hub-ui-overview-page`: New default landing page (replaces Messages as home) showing system health at a glance: agent status grid, blocked questions, task summary, activity ticker.
- `hub-ui-full-kanban`: Expanded task board covering all 7 task statuses with agent filter chips and correct status columns.

### Modified Capabilities

*(none — no existing spec-level behavior changes; all changes are UI presentation only)*

## Impact

- **Files modified**: `hub/ui/src/index.css` (full token replacement), `hub/ui/src/App.tsx` (routing, new Overview page, MissionControlPage removed), `hub/ui/src/components/layout/Sidebar.tsx` (full rewrite), `hub/ui/src/components/layout/StatusBar.tsx`, all files under `hub/ui/src/components/agents/`, `hub/ui/src/components/tasks/TasksBoard.tsx`, `hub/ui/src/components/tasks/TaskCard.tsx`, `hub/ui/src/components/messages/`, `hub/ui/src/components/questions/`, `hub/ui/src/components/logs/`, `hub/ui/src/components/activity/`, `hub/ui/src/components/common/Badge.tsx`.
- **Files deleted**: `hub/ui/src/components/agents/MissionControlPage.tsx` (absorbed into AgentsPage).
- **Files added**: `hub/ui/src/components/agents/AgentDetailPanel.tsx`, `hub/ui/src/components/overview/OverviewPage.tsx`, `hub/ui/src/components/questions/QuestionInterruptCard.tsx`.
- **No API changes**: All existing React Query hooks, SSE subscription, and Zustand stores remain unchanged.
- **No backend changes**: Hub FastAPI backend is untouched.
- **Dependency note**: `lucide-react` is already installed; no new npm packages required. Font loading may require adding Inter + JetBrains Mono to the HTML `<head>`.
