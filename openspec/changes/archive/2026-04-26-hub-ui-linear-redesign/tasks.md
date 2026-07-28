## 1. Fonts and Base CSS Tokens

- [x] 1.1 Add Inter (400, 500, 600) and JetBrains Mono (400, 500) `<link>` tags to `hub/ui/index.html` using Google Fonts with `rel="preconnect"` and `display=swap`
- [x] 1.2 Remove all M3 token definitions from `hub/ui/src/index.css`: delete `--p-cont`, `--on-p-cont`, `--s-cont`, `--on-s-cont`, `--t-cont`, `--on-t-cont`, `--sur-var`, `--on-sv`, `--surface-lowest`, `--surface-low`, `--surface-high`, `--surface-highest`, `--elev-1`, `--elev-2`, `--elev-3`, `--m-divider`, `--hover-overlay`, `--card-hover-shadow`
- [x] 1.3 Add new dark-mode token set to `index.css` under `:root` and `[data-mode="dark"]`: `--bg`, `--surface`, `--surface-2`, `--surface-3`, `--border`, `--border-hi`, `--text`, `--text-2`, `--text-3`, `--green`, `--amber`, `--red`, `--blue`, `--purple`, `--radius`, `--radius-sm`, `--radius-lg`
- [x] 1.4 Add light-mode token overrides to `index.css` under `[data-mode="light"]` for all tokens that change between modes (backgrounds, border, text colors — semantic colors unchanged)
- [x] 1.5 Set `body` font-family to `'Inter', -apple-system, BlinkMacSystemFont, sans-serif` in `index.css`
- [x] 1.6 Remove all `m3-*` CSS class definitions from `index.css` (`m3-nav-rail`, `m3-top-bar`, `m3-card-elevated`, `m3-chip`, `m3-chip-filter`, `m3-icon-btn`, `m3-title-large`, `m3-title-small`, `m3-label-large`, `m3-label-medium`, `m3-label-small`, `m3-body-medium`, `m3-body-small`, and any others found by running `grep -n 'm3-' hub/ui/src/index.css`)
- [x] 1.7 Verify: run `grep -r 'var(--p-cont\|--on-p-cont\|--s-cont\|--on-s-cont\|--t-cont\|--on-t-cont\|--sur-var\|--on-sv\|--surface-low\|--surface-high\|--elev-\|--m-divider)' hub/ui/src/` and confirm zero matches
- [x] 1.8 Verify: run `grep -r 'm3-' hub/ui/src/` and confirm zero matches

## 2. StatusBar Rewrite

- [x] 2.1 Rewrite `hub/ui/src/components/layout/StatusBar.tsx`: set height to 44px, background `var(--bg)`, border-bottom `1px solid var(--border)`
- [x] 2.2 Replace M3 chip markup with flat chip components: `background: var(--surface-2)`, `border: 1px solid var(--border)`, `border-radius: 4px`, `font-size: 12px`
- [x] 2.3 Style the "questions" chip with amber treatment when `unanswered > 0`: `border-color: rgba(245,158,11,0.3)`, `background: rgba(245,158,11,0.06)`, amber text
- [x] 2.4 Style the logo/title as plain text `font-size: 13px; font-weight: 600; color: var(--text)` — no M3 top bar treatment
- [x] 2.5 Keep the dark/light mode toggle button functional; replace `m3-icon-btn` class with plain Tailwind/inline styles

## 3. Sidebar Rewrite

- [x] 3.1 Rewrite `hub/ui/src/components/layout/Sidebar.tsx`: set width to 220px, background `var(--surface)`, border-right `1px solid var(--border)`, padding `12px 8px`
- [x] 3.2 Add a logo mark at the top: small "AW" text or icon, `font-size: 12px; font-weight: 700; color: var(--text)`, no click handler needed
- [x] 3.3 Implement grouped nav structure with section labels: add section label elements ("WORK", "COMMUNICATION", "OBSERVE") styled as `font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-3); padding: 8px 8px 4px; margin-top: 8px`
- [x] 3.4 Reorder nav items per spec: Overview · Agents · [WORK] Tasks · Jobs · [COMMUNICATION] Messages · Questions · [OBSERVE] Logs · Activity · Quality · [bottom] Settings
- [x] 3.5 Implement active state: `background: rgba(255,255,255,0.06); color: var(--text)` with a `2px solid var(--text)` left border (use `position: relative` + `::before` pseudo-element or a positioned `<span>`)
- [x] 3.6 Implement inactive hover state: `background: rgba(255,255,255,0.04); color: var(--text)` on hover
- [x] 3.7 Implement nav badges: pill element with `font-size: 10px; border-radius: 9999px; padding: 1px 5px`. Neutral style (`background: var(--surface-3); color: var(--text-2)`) for counts; urgent style (`background: var(--red); color: white`) for Questions when unanswered > 0
- [x] 3.8 Pin Settings to the bottom with `margin-top: auto` and a `border-top: 1px solid var(--border)` separator
- [x] 3.9 Add `'overview'` to the `Page` type union in `App.tsx` and add "Overview" as the first `NAV_ITEMS` entry

## 4. QuestionInterruptCard Component

- [x] 4.1 Create file `hub/ui/src/components/questions/QuestionInterruptCard.tsx`
- [x] 4.2 Define props interface: `{ questions: Question[]; compact?: boolean; onNavigateToQuestions: () => void }`
- [x] 4.3 Implement dismiss logic: track dismissed question IDs in `useState<Set<string>>`. Filter `questions` array to exclude dismissed IDs. If filtered array is empty, return `null`
- [x] 4.4 Render the first non-dismissed question: amber border card, eyebrow "⚠ {agent} is waiting", elapsed time (use `formatDistanceToNow` from `date-fns`), question text (2-line clamp in compact, no clamp in full)
- [x] 4.5 Implement "Answer" button: calls `onNavigateToQuestions()`
- [x] 4.6 Implement "Dismiss" button: adds current question's ID to the dismissed set; button not shown in `compact` mode
- [x] 4.7 Apply amber styling: `border: 1px solid rgba(245,158,11,0.25)`, `background: rgba(245,158,11,0.06)`, eyebrow `color: var(--amber)`, `border-radius: var(--radius)`

## 5. OverviewPage Component

- [x] 5.1 Create directory `hub/ui/src/components/overview/` and file `OverviewPage.tsx`
- [x] 5.2 Import and call: `useAgents()`, `useQuestions()`, `useTasks()`, and access SSE event history (from `useSSE` or a derived store)
- [x] 5.3 Render page header: title "Overview" (`font-size: 14px; font-weight: 600`), subtitle showing agent count + task count + project name from `useStatus()`
- [x] 5.4 Render agent health grid: `display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px`. Each card: status dot, agent name, role tags, task count, message count, last-seen, context bar, latest_status_msg preview. Cards are clickable and call a `onSelectAgent` callback that navigates to Agents page
- [x] 5.5 Render `QuestionInterruptCard` (full variant) between agent grid and task summary — only when unanswered questions > 0; pass `onNavigateToQuestions` prop
- [x] 5.6 Render task summary section: show count chips per status (only statuses with count > 0). Each chip is clickable and navigates to Tasks page
- [x] 5.7 Render activity ticker: 28px-tall flex row at the bottom of the scrollable content area. Show up to 10 recent SSE events as `flex-shrink: 0` chips. Each chip: colored dot (green by default, amber for warnings), agent name, event summary, relative time. Ticker auto-updates when SSE events arrive
- [x] 5.8 Export `OverviewPage` and import it in `App.tsx`; render it when `page === 'overview'`

## 6. AgentsPage Rewrite and MissionControlPage Removal

- [x] 6.1 Delete `hub/ui/src/components/agents/MissionControlPage.tsx`
- [x] 6.2 Remove `MissionControlPage` import and `page === 'mission-control'` branch from `App.tsx`; remove `'mission-control'` from the `Page` type union
- [x] 6.3 Remove the `mission-control` entry from `NAV_ITEMS` in `Sidebar.tsx`
- [x] 6.4 Rewrite `hub/ui/src/components/agents/AgentsPage.tsx`: two-panel layout — left `240px` panel with `background: var(--surface)` and `border-right: 1px solid var(--border)`; right `flex-1` panel
- [x] 6.5 Add page header above both panels: title "Agents", subtitle "{count} agents · {active} active", and a "Grid view" toggle button (`background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius)`)
- [x] 6.6 Add tab bar below header: tabs "All agents", "Active ({n})", "Idle ({n})". Active tab has 1px bottom border in `var(--text)`
- [x] 6.7 Render `QuestionInterruptCard` (compact variant) pinned at the top of the left panel, using `useQuestions()`. Pass `onNavigateToQuestions` prop that sets page to `'questions'`
- [x] 6.8 Render agent list items below interrupt card; each item: `background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px; cursor: pointer`. Selected item: `background: rgba(255,255,255,0.05); border-color: var(--border-hi)`
- [x] 6.9 Each agent list item contents: status dot (with `animate-ping` ring if running), agent name, status label, role tag pills, stats row (tasks / msgs / last-seen), context bar (2px height, green/amber/red fill), latest_status_msg preview (truncated)
- [x] 6.10 Create `hub/ui/src/components/agents/AgentDetailPanel.tsx`: accepts `agent: AgentSummary` prop; renders the detail header and tabbed body
- [x] 6.11 Detail panel header: status dot, agent name, role tags, then right-aligned: context percentage text + 48px context bar + "Compact" button + "Reset" button. Codex agents show "Auto-managed" text instead of Compact button
- [x] 6.12 Detail panel tabs: "Output", "Tasks ({count})", "Messages", "Info". Active tab: `color: var(--text); border-bottom: 1px solid var(--text)`
- [x] 6.13 Output tab: render existing `AgentOutputPanel` component (no changes to its internals needed)
- [x] 6.14 Tasks tab: render a list of tasks filtered by `task.assignee === agent.name` using `useTasks()`. Each task: title, status badge, priority badge, updated-at. Use `EmptyState` if no tasks
- [x] 6.15 Messages tab: render existing `AgentActivityTab` component (or equivalent per-agent message list)
- [x] 6.16 Info tab: render existing `AgentInfoTab` component
- [x] 6.17 Implement Grid view toggle: `useState<boolean>` for `gridView`. When true, render right panel as `display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 16px` with `MissionCard`-style compact health cards. When a card is clicked, set `gridView = false` and select that agent

## 7. AgentCard Rewrite

- [x] 7.1 Rewrite `hub/ui/src/components/agents/AgentCard.tsx` to use new tokens: `background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px`
- [x] 7.2 Selected state: `background: rgba(255,255,255,0.05); border-color: var(--border-hi)` — no M3 `--p-cont` tinting
- [x] 7.3 Ensure all badge/tag pill styles use the new semantic color system (drop M3 `color-mix(in srgb, var(--primary)...)` patterns)
- [x] 7.4 Status dot: green with `box-shadow: 0 0 0 2px rgba(34,197,94,0.3)` pulse on running agents (or CSS animation); amber dot for waiting; muted for idle
- [x] 7.5 Keep all existing data fields (runner badge, liveness badge, yolo indicator, pilot badge) — just re-style them with new tokens

## 8. Badge Component Update

- [x] 8.1 Rewrite `hub/ui/src/components/common/Badge.tsx`: replace M3 tonal container colors with semantic color tokens. Status variants: `pending` → neutral (`--surface-3`); `in_progress` → blue tint; `under_review` → amber tint; `completed` → neutral; `approved` → green tint; `revision_needed` → red tint; `rejected` → red tint. Priority variants: `high` → red tint; `medium` → amber tint; `low` / `normal` → neutral
- [x] 8.2 All badge backgrounds: `rgba(color, 0.1)`, border: `rgba(color, 0.2)`, text: full color — no filled/solid backgrounds
- [x] 8.3 Badge border-radius: `var(--radius-sm)` (4px) for rectangular badges; `9999px` for pill-shaped count badges

## 9. TasksBoard and TaskCard Rewrite

- [x] 9.1 Rewrite `hub/ui/src/components/tasks/TasksBoard.tsx`: expand `COLUMNS` array from 4 to 7 entries: `pending`, `assigned`, `in_progress`, `under_review`, `completed`, `approved`, `revision_needed`
- [x] 9.2 Add `rejected` tasks as a collapsible section below the Needs Revision column using `useState<boolean>` for expanded state; show count in header even when collapsed
- [x] 9.3 Apply column accent colors per spec: `in_progress` blue, `under_review` amber, `approved` green, `revision_needed` red; all others neutral
- [x] 9.4 Set kanban grid to `display: grid; grid-template-columns: repeat(7, minmax(160px, 1fr)); gap: 8px; overflow-x: auto`
- [x] 9.5 Add agent filter chip row above kanban: derive unique assignee names from `tasks` array; render "All" chip + one chip per agent. Store active filter in `useState<string | null>`
- [x] 9.6 Apply filter: when `activeFilter !== null`, filter each column's tasks to only those where `task.assignee === activeFilter`
- [x] 9.7 Style filter chips: `background: var(--surface-2); border: 1px solid var(--border); border-radius: 9999px; font-size: 11px; padding: 3px 10px`. Active: `background: var(--surface-3); color: var(--text); border-color: var(--border-hi)`
- [x] 9.8 Rewrite `hub/ui/src/components/tasks/TaskCard.tsx`: `background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px`. Hover: `border-color: var(--border-hi)`
- [x] 9.9 Task card collapsed state: title, status badge, priority badge, assignee badge, assigner badge (if different from assignee), updated-at relative time, expand hint
- [x] 9.10 Task card expanded state: full description in `background: var(--surface-3); border-radius: var(--radius-sm); padding: 10px`, requirements list, acceptance criteria list, deliverables list, notes, task ID footer

## 10. Remaining Component Token Updates

- [x] 10.1 Update `hub/ui/src/components/messages/MessagesFeed.tsx`: replace all `var(--p-cont)`, `var(--on-p-cont)`, `var(--sur-var)`, `var(--on-sv)` references with equivalent new tokens (`--surface-2`, `--surface-3`, `--text-2`, `--text-3`, etc.); remove any `m3-*` class names
- [x] 10.2 Update `hub/ui/src/components/messages/MessageCard.tsx` and `ConversationGroup.tsx`: same token replacement pass
- [x] 10.3 Update `hub/ui/src/components/questions/QuestionsPanel.tsx` and `AnswerForm.tsx`: same token replacement pass
- [x] 10.4 Update `hub/ui/src/components/logs/LogsView.tsx` and `LogLine.tsx`: same token replacement pass; ensure log output area uses `font-family: 'JetBrains Mono', monospace`
- [x] 10.5 Update `hub/ui/src/components/activity/ActivityLog.tsx` and `EventRow.tsx`: same token replacement pass
- [x] 10.6 Update `hub/ui/src/components/jobs/JobsPage.tsx`, `JobCard.tsx`, `JobForm.tsx`: same token replacement pass
- [x] 10.7 Update `hub/ui/src/components/quality/QualityHealthPanel.tsx`: same token replacement pass
- [x] 10.8 Update `hub/ui/src/components/layout/SetupModal.tsx`: same token replacement pass; ensure modal overlay and dialog use `var(--surface)` and `var(--border)`
- [x] 10.9 Update `hub/ui/src/components/common/EmptyState.tsx` and `Icon.tsx`: remove any M3 color references; use `var(--text-3)` for muted icon/text

## 11. App.tsx Wiring

- [x] 11.1 Add `'overview'` to the `Page` type union in `App.tsx`
- [x] 11.2 Change the default `useState<Page>` initial value from `'messages'` to `'overview'`
- [x] 11.3 Import `OverviewPage` from `@/components/overview/OverviewPage`
- [x] 11.4 Add render branch: `{page === 'overview' && <div className="h-full overflow-auto"><OverviewPage onNavigate={setPage} /></div>}`
- [x] 11.5 Remove `MissionControlPage` import and `page === 'mission-control'` render branch
- [x] 11.6 Pass `onNavigate={setPage}` prop to `OverviewPage` so it can trigger navigation (clicking agent cards → Agents page, task chips → Tasks page, Answer button → Questions page)
- [x] 11.7 Update `main` element class if needed: ensure `bg-[var(--bg)]` or equivalent replaces any M3 `bg-background` usage

## 12. Verification and Cleanup

- [x] 12.1 Run `grep -r 'm3-' hub/ui/src/` — must return zero matches
- [x] 12.2 Run `grep -r 'var(--p-cont\|--on-p-cont\|--s-cont\|--sur-var\|--on-sv\|--elev-\|--surface-low\|--surface-high\|--m-divider)' hub/ui/src/` — must return zero matches
- [x] 12.3 Run `cd hub/ui && npm run lint` — must pass with zero errors
- [x] 12.4 Run `cd hub/ui && npm run build` — must complete without TypeScript errors
- [ ] 12.5 Open the app in a browser: verify Overview page loads as default, sidebar shows 220px width with labels and sections, Agents page shows two-panel layout, MissionControl is no longer in sidebar
- [ ] 12.6 Toggle dark/light mode: verify all surfaces, text, and borders correctly switch between token sets
- [ ] 12.7 With an agent running and questions pending: verify QuestionInterruptCard appears in both the Agents left panel and on the Overview page
- [ ] 12.8 On Tasks page: verify all 7 status columns render, agent filter chips work, rejected tasks collapse correctly
- [ ] 12.9 Verify Compact and Reset buttons on agent detail header work end-to-end (requests fire, feedback message shown)
- [x] 12.10 Verify Grid view toggle on Agents page: switches between detail and 3-column grid; clicking a grid card selects that agent in detail view
