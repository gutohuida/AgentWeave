## Context

The AgentWeave Hub UI is a React 18 + Vite + TypeScript single-page app styled with Tailwind CSS v3 and a custom Material Design 3 token system defined entirely in `hub/ui/src/index.css`. Components use `var(--token-name)` inline styles throughout — there is no separate theme file or CSS-in-JS layer. The design system change is therefore a **token replacement + component rewrite** problem, not a library swap.

Current token vocabulary (M3):
- Surface containers: `--surface-lowest`, `--surface-low`, `--surface-high`, `--surface-highest`
- Tonal containers: `--p-cont`, `--on-p-cont`, `--s-cont`, `--on-s-cont`, `--t-cont`, `--on-t-cont`
- Surface variant: `--sur-var`, `--on-sv`
- Elevation: `--elev-1`, `--elev-2`, `--elev-3`
- M3-specific utilities: `m3-nav-rail`, `m3-top-bar`, `m3-card-elevated`, `m3-chip`, `m3-title-large`, etc.

The new system replaces all of the above with a zinc/neutral gray stack, keeps existing semantic color names (`--destructive`, `--border`, `--foreground`, `--background`) where compatible, and introduces the new token names documented in the design decisions below.

All data fetching (React Query hooks), real-time updates (SSE via `useSSE`), global state (Zustand `configStore`), and backend API contracts are **unchanged**.

---

## Goals / Non-Goals

**Goals:**
- Replace all M3 CSS tokens with Linear/shadcn-style tokens in `index.css`
- Rewrite `Sidebar` from 80px icon rail to 220px labeled sidebar with grouped sections
- Merge `MissionControlPage` into a redesigned `AgentsPage` (single agent-centric view)
- Add `OverviewPage` as new default landing page
- Add `QuestionInterruptCard` shown whenever unanswered questions exist
- Expand `TasksBoard` from 4 to 7 status columns
- Update all components to use new tokens and drop all `m3-*` class references
- Preserve all existing functional behavior (SSE, React Query, routing logic)
- Dark mode remains default; light mode toggle remains functional

**Non-Goals:**
- No backend or API changes
- No new npm packages (use existing Inter from Google Fonts, add JetBrains Mono)
- No routing library introduction (keep existing `useState<Page>` pattern in `App.tsx`)
- No Storybook or component documentation
- No accessibility audit (separate concern)
- No mobile/responsive layout (existing desktop-only constraint unchanged)

---

## Decisions

### D1 — Token replacement strategy: full swap in `index.css`, not incremental

**Decision:** Delete all M3 tokens in `index.css` and replace in one pass. Do not run old and new tokens in parallel.

**Rationale:** M3 tokens are deeply interwoven — `--p-cont`, `--on-p-cont`, and `--s-cont` appear across 15+ components. Running parallel token sets would double the CSS surface area and create confusion. A clean cut forces each component to be updated explicitly, leaving no silent M3 fallbacks.

**Alternative considered:** Alias new tokens to M3 names (e.g., `--p-cont: var(--surface-2)`). Rejected because it hides the migration debt and doesn't remove M3 class utilities like `m3-nav-rail`.

**New token set:**

```css
/* Backgrounds */
--bg:          #09090b;   /* page background */
--surface:     #111113;   /* sidebar, panels */
--surface-2:   #18181b;   /* cards, inputs */
--surface-3:   #27272a;   /* hover states, inactive tags */

/* Borders */
--border:      rgba(255,255,255,0.08);   /* default dividers */
--border-hi:   rgba(255,255,255,0.12);   /* emphasized borders, selected */

/* Text */
--text:        #fafafa;   /* primary content */
--text-2:      #a1a1aa;   /* secondary labels */
--text-3:      #71717a;   /* tertiary, timestamps, placeholders */

/* Semantic (unchanged names) */
--destructive: #ef4444;
--destructive-fg: #ffffff;

/* Semantic aliases (new) */
--green:       #22c55e;   /* running, success, ok */
--amber:       #f59e0b;   /* waiting, warning, blocked */
--red:         #ef4444;   /* error, rejected */
--blue:        #3b82f6;   /* primary actions, principal role */
--purple:      #a855f7;   /* dev roles, tags */

/* Radius */
--radius:      6px;        /* default card/button radius */
--radius-sm:   4px;        /* tags, badges */
--radius-lg:   8px;        /* larger cards */
```

Light mode overrides defined under `[data-mode="light"]` — same structure, inverted values.

---

### D2 — Remove `m3-*` utility classes, use Tailwind directly

**Decision:** Delete all `m3-*` CSS class definitions from `index.css`. Replace usages in components with Tailwind utility classes or plain `style={{}}` with new tokens.

**Rationale:** M3 utilities (`m3-title-large`, `m3-label-small`, `m3-card-elevated`, `m3-chip`, `m3-nav-rail`, `m3-top-bar`) encode M3 sizing and spacing rules. Keeping them while changing tokens would produce mismatched results (e.g., `m3-card-elevated` still applies M3 box-shadow via `--elev-1`). Removing them forces explicit, readable styling in each component.

**Typography scale replacement:**

| Old class         | New approach                                     |
|-------------------|--------------------------------------------------|
| `m3-title-large`  | `text-sm font-semibold tracking-tight`           |
| `m3-title-small`  | `text-[13px] font-medium`                        |
| `m3-label-large`  | `text-[13px] font-medium`                        |
| `m3-label-medium` | `text-xs font-medium`                            |
| `m3-label-small`  | `text-[11px]`                                    |
| `m3-body-medium`  | `text-sm`                                        |
| `m3-body-small`   | `text-xs`                                        |

---

### D3 — Sidebar: 220px labeled rail with section groups

**Decision:** Replace the 80px icon-only nav rail with a 220px sidebar with text labels, grouped into sections separated by section heading labels.

**Structure:**
```
[AW logo mark]

Overview          ← no section label, top item
─────────────────
Agents            [badge: active count]

WORK              ← section label (10px uppercase zinc-600)
Tasks             [badge: count]
Jobs

COMMUNICATION
Messages          [badge: unread]
Questions         [badge: unanswered — red]

OBSERVE
Logs
Activity
Quality

─────────────────
Settings          ← bottom pinned
```

**Active state:** 2px solid `--text` left border on the nav item, background `rgba(255,255,255,0.06)`, text `--text`. No pill/container indicator.

**Badge style:** Rounded pill, `--surface-3` background + `--text-2` text for counts; `--red` background + white text for urgent (unanswered questions only).

**Alternative considered:** Keep 80px rail, add tooltips. Rejected — 9 items in 80px is cognitively costly, and the icon-only treatment required users to memorize icon meanings.

---

### D4 — Merge MissionControlPage into AgentsPage

**Decision:** Delete `MissionControlPage.tsx`. Redesign `AgentsPage.tsx` to be the single agent-centric view with a two-panel layout.

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│ [Header: "Agents" title + agent count + "Grid view" btn] │
│ [Tab bar: All agents / Active (N) / Idle (N)]            │
├──────────────────┬───────────────────────────────────────┤
│  Agent list      │  Detail panel                         │
│  240px           │                                       │
│  ─────────────   │  [Agent name] [role tags] [ctx%] [...] │
│  ● claude        │  ──────────────────────────────────── │
│    Running       │  [Output] [Tasks] [Messages] [Info]   │
│    4 tasks       │                                       │
│    tech_lead     │  (live output / task list / msgs)     │
│                  │                                       │
│  ○ codex         │                                       │
│    Waiting       │                                       │
│                  │                                       │
│  ○ gemini        │                                       │
│    Idle          │                                       │
└──────────────────┴───────────────────────────────────────┘
```

The agent list panel shows `QuestionInterruptCard` pinned above the agent items whenever `questions.unanswered > 0`.

The detail panel right side preserves all existing tabs: Output (`AgentOutputPanel`), Activity (`AgentActivityTab`), Info (`AgentInfoTab`). A new "Tasks" tab is added showing tasks filtered by the selected agent name.

The "Grid view" toggle button in the header switches the right panel to a 3-column health grid (the Mission Control card layout), rendering `MissionCard` components inline. This preserves Mission Control's context-bar overview without a separate page.

**New component:** `AgentDetailPanel.tsx` — extracts the right-panel logic from `AgentsPage.tsx` for clarity.

---

### D5 — QuestionInterruptCard: inline interrupt, not just a badge

**Decision:** When `questions.unanswered > 0`, render a `QuestionInterruptCard` at the top of the agent list panel in `AgentsPage` and as a full-width card in `OverviewPage`. This is in addition to the existing nav badge.

**Component contract:**
```tsx
interface QuestionInterruptCardProps {
  questions: Question[]   // from useQuestions()
  compact?: boolean       // true = agent list version (narrower), false = overview version
}
```

**Visual:** Amber border (`rgba(245,158,11,0.25)`), amber-tinted background. Shows agent name, time elapsed, truncated question text. Primary CTA "Answer" button navigates to QuestionsPanel. Secondary "Dismiss" hides until next poll cycle.

---

### D6 — OverviewPage as new default landing page

**Decision:** Add `OverviewPage.tsx`. Change default `Page` state in `App.tsx` from `'messages'` to `'overview'`. Add `'overview'` to the `Page` union type.

**Layout (top to bottom):**
1. **Agent health row** — 3-column grid of compact agent cards (status dot, name, role tags, ctx bar, last-seen). Click navigates to Agents page with that agent selected.
2. **QuestionInterruptCard** — shown only when unanswered > 0.
3. **Task summary** — kanban columns with counts; click opens Tasks page.
4. **Activity ticker** — 28px bar at the bottom of the main area showing a horizontally scrolling live event feed from `useSSE`.

---

### D7 — Full kanban: 7 status columns

**Decision:** Expand `TasksBoard` from 4 columns to 7. Column order:

| # | Status key       | Label            | Accent color     |
|---|------------------|------------------|------------------|
| 1 | `pending`        | Pending          | —                |
| 2 | `assigned`       | Assigned         | —                |
| 3 | `in_progress`    | In Progress      | blue             |
| 4 | `under_review`   | Under Review     | amber            |
| 5 | `completed`      | Completed        | —                |
| 6 | `approved`       | Approved         | green            |
| 7 | `revision_needed`| Needs Revision   | red              |

`rejected` status tasks are shown in a collapsed "Rejected" section below `revision_needed` (not a full column, as they are terminal).

Add an agent filter chip row above the board: "All" + one chip per agent name. Chips filter the visible tasks by `task.assignee`.

---

### D8 — Font loading

**Decision:** Add Google Fonts `<link>` tags to `hub/ui/index.html` for Inter (400, 500, 600) and JetBrains Mono (400, 500). Set CSS `font-family` defaults in `index.css` body rule.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

**Alternative considered:** Bundle fonts as static assets. Rejected for simplicity — Hub is self-hosted and has internet access in typical deployment.

---

## Risks / Trade-offs

- **Token rename blast radius** — Every component uses inline `var(--token)` references. Any missed token rename silently falls back to browser default (usually black/white), which is detectable during testing but requires component-by-component review. Mitigation: grep for all `var(--` usages before and after migration; CI lint step.

- **M3 class removal may miss edge cases** — `m3-*` classes appear in JSX className strings. A grep for `m3-` in `hub/ui/src/` before starting will enumerate all usages. Mitigation: run `grep -r 'm3-' hub/ui/src/` before starting; treat the result as a checklist.

- **MissionControlPage removal** — Any user with a browser bookmark or deep link to Mission Control will lose it. Mitigation: the "Grid view" toggle in AgentsPage preserves equivalent functionality.

- **7-column kanban on small screens** — At 1280px wide, 7 columns at ~160px each fits. Below 1280px columns compress or require horizontal scroll. Mitigation: add `overflow-x: auto` to the kanban container; accept horizontal scroll for now.

- **Light mode** — Token inversion for light mode must be defined. If only dark mode is implemented initially, the light mode toggle produces broken results. Mitigation: define both `[data-mode="dark"]` and `[data-mode="light"]` token sets in the same PR.

---

## Migration Plan

1. Update `hub/ui/index.html` — add font links.
2. Rewrite `hub/ui/src/index.css` — replace all tokens; remove all `m3-*` utility classes; add new token set for dark + light mode.
3. Rewrite `hub/ui/src/components/layout/Sidebar.tsx`.
4. Rewrite `hub/ui/src/components/layout/StatusBar.tsx`.
5. Add `hub/ui/src/components/common/QuestionInterruptCard.tsx`.
6. Add `hub/ui/src/components/overview/OverviewPage.tsx`.
7. Rewrite `hub/ui/src/components/agents/AgentsPage.tsx` + add `AgentDetailPanel.tsx`; delete `MissionControlPage.tsx`.
8. Rewrite `hub/ui/src/components/agents/AgentCard.tsx`.
9. Rewrite `hub/ui/src/components/tasks/TasksBoard.tsx`.
10. Rewrite `hub/ui/src/components/tasks/TaskCard.tsx`.
11. Update `hub/ui/src/components/common/Badge.tsx`.
12. Update remaining components (`MessagesFeed`, `QuestionsPanel`, `LogsView`, `ActivityLog`, `JobsPage`, `QualityHealthPanel`) — token + class updates only, no structural changes.
13. Update `hub/ui/src/App.tsx` — add `'overview'` to Page type; import OverviewPage; set default page to `'overview'`; remove MissionControlPage import.

**Rollback:** Revert the branch. No database migrations, no API changes.

---

## Open Questions

- *(none — scope is fully defined by exploration session and reference concept `ui-concepts/new-concepts/01-linear-shadcn.html`)*
