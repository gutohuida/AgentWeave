// The panel shell's tab configuration, per project.
//
// Which tabs are open, their order, which one is visible, and whether the shell is open at all —
// remembered per project and restored when the operator returns to it (design D5). Width is
// deliberately NOT here: it stays the single global value `specPreferences.ts` already persists,
// because nothing suggests the operator wants a different width per tab and that store already
// answered this question once.
//
// Persisting keyed tabs means persisting pointers to things that can stop existing, so this store
// carries machinery a naive one would not: a version with a real migration chain, reconciliation
// against what currently exists, and two restore rules that a naive implementation gets wrong.

import { create } from 'zustand'

/** The shape version carried *inside* the payload. Bump when `StoredProjects` changes, and add the
 *  matching step to `MIGRATIONS` in the same edit. */
export const PANEL_TABS_VERSION = 1

/** The key names the format *family*, the payload's `version` drives in-place migration. Two levels
 *  because they answer different questions: a wholly incompatible future shape can be written to a
 *  new key without ever reading this one, while an incremental change migrates in place. */
const STORAGE_KEY = 'aw.panel.tabs.v1'

export const PANEL_TABS_STORAGE_KEY = STORAGE_KEY

// --- Tab identity -----------------------------------------------------------------------------
//
// Index kinds take a fixed id, detail kinds a keyed one (design D3). The union is literal and
// exhaustively type-checkable; kinds are never constructed at runtime from external input.

export type IndexTabId = 'specs' | 'files' | 'loops'
export type SpecTabId = `spec:${string}`
export type FileTabId = `file:${string}`
export type LoopTabId = `loop:${string}`
export type TabId = IndexTabId | SpecTabId | FileTabId | LoopTabId

export type TabKind = 'specs' | 'files' | 'loops' | 'spec' | 'file' | 'loop'

/** Derived from the id rather than stored beside it, so the two cannot disagree. */
export function tabKind(id: TabId): TabKind {
  if (id === 'specs' || id === 'files' || id === 'loops') return id
  if (id.startsWith('spec:')) return 'spec'
  if (id.startsWith('loop:')) return 'loop'
  return 'file'
}

/** A specification document's tab is keyed by document id, which survives rename — `rename_spec_document`
 *  is an agent-callable MCP tool, so a path-keyed tab would dangle for a document that still exists
 *  (design D4). */
export function specTabId(documentId: string): SpecTabId {
  return `spec:${documentId}`
}

/** A file has no identity other than its path, so this is the one kind that can dangle. */
export function fileTabId(relativePath: string): FileTabId {
  return `file:${relativePath}`
}

/** A loop's tab is keyed by the `Loop` row's own id (design B4.3's `id`, distinct from the job
 *  id) — the same id `GET /projects/{project_id}/loops/{loop_id}` reads by, so it never dangles
 *  across a rename the way a path-keyed tab would (there is nothing to rename). */
export function loopTabId(loopId: string): LoopTabId {
  return `loop:${loopId}`
}

export function specDocumentId(id: SpecTabId): string {
  return id.slice('spec:'.length)
}

export function filePath(id: FileTabId): string {
  return id.slice('file:'.length)
}

export function loopId(id: LoopTabId): string {
  return id.slice('loop:'.length)
}

export function isSpecTabId(id: TabId): id is SpecTabId {
  return id.startsWith('spec:')
}

export function isFileTabId(id: TabId): id is FileTabId {
  return id.startsWith('file:')
}

export function isLoopTabId(id: TabId): id is LoopTabId {
  return id.startsWith('loop:')
}

function isTabId(value: unknown): value is TabId {
  if (typeof value !== 'string') return false
  if (value === 'specs' || value === 'files' || value === 'loops') return true
  if (value.startsWith('spec:')) return value.length > 'spec:'.length
  if (value.startsWith('file:')) return value.length > 'file:'.length
  if (value.startsWith('loop:')) return value.length > 'loop:'.length
  return false
}

export interface PanelTab {
  id: TabId
  /** Bumped every time an already-open tab is opened again. The tab's content watches it and
   *  re-reveals — "open this file again" and "scroll to it again" are the same operator intent
   *  (design D3, T3's `revealRequestId` shape). A counter rather than a boolean, so a second
   *  request while the first is still being handled is not swallowed. */
  revealRequestId: number
}

export interface ProjectPanelState {
  tabs: PanelTab[]
  activeTabId: TabId | null
  isOpen: boolean
}

export const EMPTY_PROJECT_PANEL: ProjectPanelState = Object.freeze({
  tabs: [],
  activeTabId: null,
  isOpen: false,
})

type StoredProjects = Record<string, ProjectPanelState>

// --- Persistence ------------------------------------------------------------------------------

/** Each step upgrades exactly one version. There are no steps today because there is only
 *  version 1 — the chain exists so that adding the first one is an edit here and nowhere else.
 *  Retrofitting versioning after shipping is what forces a silent data loss, so it is written now
 *  while it costs nothing. */
const MIGRATIONS: Record<number, (state: unknown) => unknown> = {}

/** Runs the migration chain from `fromVersion` up to current. A version with no step forward is
 *  discarded rather than guessed at: an unreadable tab configuration costs the operator a few
 *  clicks, whereas a misread one restores tabs pointing at the wrong things. */
export function migratePanelTabs(state: unknown, fromVersion: number): StoredProjects {
  let current = state
  let version = fromVersion
  while (version < PANEL_TABS_VERSION) {
    const step = MIGRATIONS[version]
    if (!step) return {}
    current = step(current)
    version += 1
  }
  return parseProjects(current)
}

function parseTab(value: unknown): PanelTab | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (!isTabId(record.id)) return null
  const reveal = record.revealRequestId
  return {
    id: record.id,
    revealRequestId: typeof reveal === 'number' && Number.isFinite(reveal) ? reveal : 0,
  }
}

function parseProjectPanel(value: unknown): ProjectPanelState | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (!Array.isArray(record.tabs)) return null

  const seen = new Set<TabId>()
  const tabs: PanelTab[] = []
  for (const entry of record.tabs) {
    const tab = parseTab(entry)
    if (!tab || seen.has(tab.id)) continue
    seen.add(tab.id)
    tabs.push(tab)
  }

  const activeTabId = isTabId(record.activeTabId) ? record.activeTabId : null
  return normalize({
    tabs,
    activeTabId,
    isOpen: record.isOpen === true,
  })
}

function parseProjects(value: unknown): StoredProjects {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {}
  const out: StoredProjects = {}
  for (const [projectId, entry] of Object.entries(value as Record<string, unknown>)) {
    const panel = parseProjectPanel(entry)
    if (panel) out[projectId] = panel
  }
  return out
}

function loadProjects(): StoredProjects {
  if (typeof window === 'undefined') return {}
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable (privacy mode, disabled cookies).
    return {}
  }
  if (!raw) return {}

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return {}
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}

  const payload = parsed as Record<string, unknown>
  const version = typeof payload.version === 'number' ? payload.version : 0
  if (version > PANEL_TABS_VERSION) return {}
  return migratePanelTabs(payload.projects, version)
}

function saveProjects(projects: StoredProjects): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: PANEL_TABS_VERSION, projects }),
    )
  } catch {
    // Persisting tab configuration is best-effort; the shell must still work without it.
  }
}

// --- The two restore rules --------------------------------------------------------------------

/**
 * Both rules from design D5, taken verbatim from T3 because both describe failures a naive
 * implementation will have:
 *
 * 1. Every tab dropped ⇒ the shell restores **closed**, not open and empty.
 * 2. The visible tab dropped but others surviving ⇒ promote a survivor, rather than an open shell
 *    with nothing shown.
 *
 * Applied on load and after reconciliation — not on every mutation. A shell deliberately opened
 * with no tabs yet is a live state the shell component may choose to render (task 2.1); a
 * *restored* one is not, because the operator never asked for it.
 */
function normalize(panel: ProjectPanelState): ProjectPanelState {
  if (panel.tabs.length === 0) {
    return { tabs: [], activeTabId: null, isOpen: false }
  }
  const activeSurvives =
    panel.activeTabId !== null && panel.tabs.some((tab) => tab.id === panel.activeTabId)
  return {
    tabs: panel.tabs,
    activeTabId: activeSurvives ? panel.activeTabId : panel.tabs[0].id,
    isOpen: panel.isOpen,
  }
}

/** Which tab becomes visible when the visible one is closed: the tab that took its place, else the
 *  new last one. Left as `null` only when nothing survives. */
function promoteAfterRemoval(tabs: PanelTab[], removedIndex: number): TabId | null {
  if (tabs.length === 0) return null
  return tabs[Math.min(removedIndex, tabs.length - 1)].id
}

// --- What reconciliation is told exists -------------------------------------------------------

/**
 * Each field is optional and means "this listing is known". An absent field means the caller does
 * not yet know what exists of that kind, and tabs of that kind are left alone — a listing that has
 * not loaded yet must never be read as "nothing exists", which would drop every tab the operator
 * had open.
 */
export interface WorkspaceInventory {
  /** Every path the workspace path listing currently returns, byte-for-byte. */
  filePaths?: readonly string[]
  /** Every document id that still exists at all. A `spec:` tab is keyed by id and survives rename,
   *  phase change and archival, so it reconciles only against outright absence (design D4). */
  documentIds?: readonly string[]
}

interface PanelTabsState {
  projects: StoredProjects
  /** Opens `id`, or refocuses and re-reveals it when already open — never a second tab for the
   *  same item. Opening always makes the tab visible and the shell open. */
  openTab: (projectId: string, id: TabId) => void
  closeTab: (projectId: string, id: TabId) => void
  activateTab: (projectId: string, id: TabId) => void
  /** Moves the tab at `fromIndex` to `toIndex`. Out-of-range indices are a no-op. */
  reorderTab: (projectId: string, fromIndex: number, toIndex: number) => void
  closeOthers: (projectId: string, id: TabId) => void
  closeToRight: (projectId: string, id: TabId) => void
  closeAll: (projectId: string) => void
  setShellOpen: (projectId: string, isOpen: boolean) => void
  /** Drops detail tabs whose item no longer exists, then applies both restore rules. */
  reconcile: (projectId: string, inventory: WorkspaceInventory) => void
}

/** Reads one project's configuration. Never returns undefined — a project never opened yet has the
 *  same shape as one whose tabs were all closed. */
export function selectProjectPanel(
  state: Pick<PanelTabsState, 'projects'>,
  projectId: string | null,
): ProjectPanelState {
  if (!projectId) return EMPTY_PROJECT_PANEL
  return state.projects[projectId] ?? EMPTY_PROJECT_PANEL
}

export const usePanelTabsStore = create<PanelTabsState>()((set, get) => {
  /** Every mutation goes through here, so persistence can never be forgotten at one call site. */
  function update(
    projectId: string,
    mutate: (panel: ProjectPanelState) => ProjectPanelState,
  ): void {
    const previous = get().projects[projectId] ?? EMPTY_PROJECT_PANEL
    const projects = { ...get().projects, [projectId]: mutate(previous) }
    saveProjects(projects)
    set({ projects })
  }

  return {
    projects: loadProjects(),

    openTab: (projectId, id) =>
      update(projectId, (panel) => {
        const existing = panel.tabs.find((tab) => tab.id === id)
        if (existing) {
          return {
            tabs: panel.tabs.map((tab) =>
              tab.id === id ? { ...tab, revealRequestId: tab.revealRequestId + 1 } : tab,
            ),
            activeTabId: id,
            isOpen: true,
          }
        }
        // Design D8's one asymmetry: opening a `file:` tab also closes the `files` tree tab — the
        // tree is a launcher, and in a narrow column a tab spent on the thing that only got you
        // here is a tab wasted. The loops index deliberately does not behave that way (a
        // governance glance, not navigation), so this stays a rule about `file:` tabs specifically
        // rather than a general "index gives way to detail" applied to every kind.
        const tabs = isFileTabId(id) ? panel.tabs.filter((tab) => tab.id !== 'files') : panel.tabs
        return {
          tabs: [...tabs, { id, revealRequestId: 0 }],
          activeTabId: id,
          isOpen: true,
        }
      }),

    closeTab: (projectId, id) =>
      update(projectId, (panel) => {
        const index = panel.tabs.findIndex((tab) => tab.id === id)
        if (index === -1) return panel
        const tabs = panel.tabs.filter((tab) => tab.id !== id)
        // Closing the last tab closes the shell — the requirement, not an inferred tidy-up.
        if (tabs.length === 0) return { tabs, activeTabId: null, isOpen: false }
        return {
          tabs,
          activeTabId:
            panel.activeTabId === id ? promoteAfterRemoval(tabs, index) : panel.activeTabId,
          isOpen: panel.isOpen,
        }
      }),

    activateTab: (projectId, id) =>
      update(projectId, (panel) =>
        panel.tabs.some((tab) => tab.id === id)
          ? { ...panel, activeTabId: id, isOpen: true }
          : panel,
      ),

    reorderTab: (projectId, fromIndex, toIndex) =>
      update(projectId, (panel) => {
        const last = panel.tabs.length - 1
        if (fromIndex < 0 || fromIndex > last || toIndex < 0 || toIndex > last) return panel
        if (fromIndex === toIndex) return panel
        const tabs = [...panel.tabs]
        const [moved] = tabs.splice(fromIndex, 1)
        tabs.splice(toIndex, 0, moved)
        return { ...panel, tabs }
      }),

    closeOthers: (projectId, id) =>
      update(projectId, (panel) => {
        const kept = panel.tabs.filter((tab) => tab.id === id)
        if (kept.length === 0) return panel
        return { tabs: kept, activeTabId: id, isOpen: panel.isOpen }
      }),

    closeToRight: (projectId, id) =>
      update(projectId, (panel) => {
        const index = panel.tabs.findIndex((tab) => tab.id === id)
        if (index === -1) return panel
        const tabs = panel.tabs.slice(0, index + 1)
        const activeSurvives = tabs.some((tab) => tab.id === panel.activeTabId)
        return {
          tabs,
          activeTabId: activeSurvives ? panel.activeTabId : id,
          isOpen: panel.isOpen,
        }
      }),

    closeAll: (projectId) =>
      update(projectId, () => ({ tabs: [], activeTabId: null, isOpen: false })),

    setShellOpen: (projectId, isOpen) => update(projectId, (panel) => ({ ...panel, isOpen })),

    reconcile: (projectId, inventory) =>
      update(projectId, (panel) => {
        const { filePaths, documentIds } = inventory
        const files = filePaths ? new Set(filePaths) : null
        const documents = documentIds ? new Set(documentIds) : null

        const tabs = panel.tabs.filter((tab) => {
          if (isFileTabId(tab.id)) return files === null || files.has(filePath(tab.id))
          if (isSpecTabId(tab.id)) return documents === null || documents.has(specDocumentId(tab.id))
          return true
        })
        if (tabs.length === panel.tabs.length) return panel
        return normalize({ ...panel, tabs })
      }),
  }
})
