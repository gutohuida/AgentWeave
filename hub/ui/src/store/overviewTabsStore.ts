// The Overview's two tabs, per project: their order and the one last opened (design D9).
//
// Browser display preferences, as the panel tabs are (`panelTabsStore.ts`), so they live in this
// browser's localStorage and not in a Hub setting. A project the operator has never reordered reads
// Dashboard first and opens on it.

import { create } from 'zustand'

export type OverviewTabId = 'dashboard' | 'briefing'

export const OVERVIEW_TABS_STORAGE_KEY = 'aw.overview.tabs.v1'

export interface OverviewTabsState {
  order: OverviewTabId[]
  last: OverviewTabId
}

export const DEFAULT_OVERVIEW_TABS: OverviewTabsState = Object.freeze({
  order: ['dashboard', 'briefing'] as OverviewTabId[],
  last: 'dashboard' as OverviewTabId,
})

const isTab = (v: unknown): v is OverviewTabId => v === 'dashboard' || v === 'briefing'

function parseEntry(value: unknown): OverviewTabsState | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  const order = Array.isArray(record.order) ? record.order.filter(isTab) : []
  // Both tabs exactly once; anything else is not a choice the operator made.
  if (order.length !== 2 || order[0] === order[1]) return null
  return { order, last: isTab(record.last) ? record.last : order[0] }
}

function load(): Record<string, OverviewTabsState> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(OVERVIEW_TABS_STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const out: Record<string, OverviewTabsState> = {}
    for (const [projectId, entry] of Object.entries(parsed as Record<string, unknown>)) {
      const state = parseEntry(entry)
      if (state) out[projectId] = state
    }
    return out
  } catch {
    // Unavailable or unreadable storage: the defaults stand.
    return {}
  }
}

function save(projects: Record<string, OverviewTabsState>): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(OVERVIEW_TABS_STORAGE_KEY, JSON.stringify(projects))
  } catch {
    // Best-effort: the tabs still work without remembering.
  }
}

interface Store {
  projects: Record<string, OverviewTabsState>
  /** The tab open when the operator last left each project's Overview in this page session. A
   *  reload clears it, so a fresh Overview opens on the first tab (FR-1); moving between pages
   *  brings the operator back to the tab they were on. */
  session: Record<string, OverviewTabId>
  /** Puts `tab` at `index` in this project's order. */
  moveTab: (projectId: string, tab: OverviewTabId, index: number) => void
  openTab: (projectId: string, tab: OverviewTabId) => void
  /** Re-reads storage: what a reload does. */
  reload: () => void
}

export function selectOverviewTabs(state: Pick<Store, 'projects'>, projectId: string | null): OverviewTabsState {
  return (projectId && state.projects[projectId]) || DEFAULT_OVERVIEW_TABS
}

/** The tab the Overview opens on: the one left open in this page session, else the first. */
export function selectOpeningTab(state: Pick<Store, 'projects' | 'session'>, projectId: string | null): OverviewTabId {
  return (projectId && state.session[projectId]) || selectOverviewTabs(state, projectId).order[0]
}

export const useOverviewTabsStore = create<Store>()((set, get) => {
  function update(projectId: string, mutate: (s: OverviewTabsState) => OverviewTabsState) {
    const projects = { ...get().projects, [projectId]: mutate(selectOverviewTabs(get(), projectId)) }
    save(projects)
    set({ projects })
  }
  return {
    projects: load(),
    session: {},
    moveTab: (projectId, tab, index) =>
      update(projectId, (s) => {
        const rest = s.order.filter((t) => t !== tab)
        const at = Math.max(0, Math.min(rest.length, index))
        const order = [...rest.slice(0, at), tab, ...rest.slice(at)]
        return { ...s, order }
      }),
    openTab: (projectId, tab) => {
      set({ session: { ...get().session, [projectId]: tab } })
      update(projectId, (s) => ({ ...s, last: tab }))
    },
    reload: () => set({ projects: load(), session: {} }),
  }
})
