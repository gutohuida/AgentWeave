import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  usePanelTabsStore,
  selectProjectPanel,
  specTabId,
  fileTabId,
  loopTabId,
  loopId,
  isLoopTabId,
  tabKind,
  migratePanelTabs,
  PANEL_TABS_VERSION,
  PANEL_TABS_STORAGE_KEY as KEY,
} from '@/store/panelTabsStore'

const P1 = 'proj-one'
const P2 = 'proj-two'

function panel(projectId = P1) {
  return selectProjectPanel(usePanelTabsStore.getState(), projectId)
}

function tabIds(projectId = P1) {
  return panel(projectId).tabs.map((tab) => tab.id)
}

function stored() {
  return JSON.parse(localStorage.getItem(KEY) ?? '{}') as {
    version?: number
    projects?: Record<string, { tabs?: { id: string }[]; activeTabId?: string | null; isOpen?: boolean }>
  }
}

/** The store reads localStorage once at module init, so a load-path test has to re-import it. */
async function loadFrom(payload: unknown) {
  localStorage.setItem(KEY, JSON.stringify(payload))
  vi.resetModules()
  return await import('@/store/panelTabsStore')
}

describe('panelTabsStore — tab identity', () => {
  it('derives kind from id for every kind in the union', () => {
    expect(tabKind('specs')).toBe('specs')
    expect(tabKind('files')).toBe('files')
    expect(tabKind('loops')).toBe('loops')
    expect(tabKind(specTabId('doc-7'))).toBe('spec')
    expect(tabKind(fileTabId('src/main.py'))).toBe('file')
    expect(tabKind(loopTabId('loop-9'))).toBe('loop')
  })

  it('keys a spec tab by document id and a file tab by path (design D4)', () => {
    expect(specTabId('doc-7')).toBe('spec:doc-7')
    expect(fileTabId('src/a b/c.ts')).toBe('file:src/a b/c.ts')
  })

  it('keys a loop tab by the Loop row id (task B5, "a loop writes its own queue")', () => {
    expect(loopTabId('loop-9')).toBe('loop:loop-9')
    expect(loopId(loopTabId('loop-9'))).toBe('loop-9')
    expect(isLoopTabId(loopTabId('loop-9'))).toBe(true)
    expect(isLoopTabId('specs')).toBe(false)
  })
})

describe('panelTabsStore — open, close, activate, reorder', () => {
  beforeEach(() => {
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
  })

  it('opening a tab makes it visible and opens the shell', () => {
    usePanelTabsStore.getState().openTab(P1, 'specs')

    expect(tabIds()).toEqual(['specs'])
    expect(panel().activeTabId).toBe('specs')
    expect(panel().isOpen).toBe(true)
  })

  it('reopening an already-open tab refocuses and re-reveals rather than duplicating', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, specTabId('doc-1'))
    store.openTab(P1, specTabId('doc-2'))
    expect(panel().activeTabId).toBe('spec:doc-2')
    const revealBefore = panel().tabs[0].revealRequestId

    store.openTab(P1, specTabId('doc-1'))

    expect(tabIds()).toEqual(['spec:doc-1', 'spec:doc-2'])
    expect(panel().activeTabId).toBe('spec:doc-1')
    expect(panel().tabs[0].revealRequestId).toBe(revealBefore + 1)
    // The untouched tab's counter must not move, or every tab would "re-reveal" on any open.
    expect(panel().tabs[1].revealRequestId).toBe(0)
  })

  it('closing the last tab closes the shell', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.closeTab(P1, 'specs')

    expect(tabIds()).toEqual([])
    expect(panel().activeTabId).toBeNull()
    expect(panel().isOpen).toBe(false)
  })

  it('closing the visible tab promotes a survivor and leaves the shell open', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, specTabId('doc-1'))
    store.openTab(P1, specTabId('doc-2'))
    store.activateTab(P1, specTabId('doc-1'))

    store.closeTab(P1, specTabId('doc-1'))

    expect(tabIds()).toEqual(['specs', 'spec:doc-2'])
    expect(panel().activeTabId).toBe('spec:doc-2')
    expect(panel().isOpen).toBe(true)
  })

  it('closing a non-visible tab leaves the visible one alone', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, specTabId('doc-1'))

    store.closeTab(P1, 'specs')

    expect(panel().activeTabId).toBe('spec:doc-1')
  })

  it('opening a file tab closes the files tree tab (design D8, 2026-08-18-one-shell-three-panels)', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'files')
    store.openTab(P1, fileTabId('src/a.ts'))

    expect(tabIds()).toEqual([fileTabId('src/a.ts')])
    expect(panel().activeTabId).toBe(fileTabId('src/a.ts'))
  })

  it('opening a second file tab does not disturb a specs tab left open beside it', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, 'files')
    store.openTab(P1, fileTabId('src/a.ts'))
    store.openTab(P1, fileTabId('src/b.ts'))

    expect(tabIds()).toEqual(['specs', fileTabId('src/a.ts'), fileTabId('src/b.ts')])
  })

  it('reopening the files tree after a file tab is open does not close the file tab (D8 is asymmetric)', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'files')
    store.openTab(P1, fileTabId('src/a.ts'))
    store.openTab(P1, 'files')

    expect(tabIds()).toEqual([fileTabId('src/a.ts'), 'files'])
  })

  it('opening a loop drill-down does not close the loops index — a governance glance, not a launcher (task B5.2)', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'loops')
    store.openTab(P1, loopTabId('loop-1'))

    expect(tabIds()).toEqual(['loops', loopTabId('loop-1')])
    expect(panel().activeTabId).toBe(loopTabId('loop-1'))
  })

  it('reorders by index and ignores out-of-range indices', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, 'files')
    store.openTab(P1, specTabId('doc-1'))

    store.reorderTab(P1, 2, 0)
    expect(tabIds()).toEqual(['spec:doc-1', 'specs', 'files'])

    store.reorderTab(P1, 0, 9)
    expect(tabIds()).toEqual(['spec:doc-1', 'specs', 'files'])
  })

  it('closeOthers, closeToRight and closeAll', () => {
    const store = usePanelTabsStore.getState()
    const open = () => {
      usePanelTabsStore.setState({ projects: {} })
      store.openTab(P1, 'specs')
      store.openTab(P1, 'files')
      store.openTab(P1, specTabId('doc-1'))
    }

    open()
    store.closeToRight(P1, 'files')
    expect(tabIds()).toEqual(['specs', 'files'])
    // The visible tab was to the right and is gone, so the anchor becomes visible.
    expect(panel().activeTabId).toBe('files')

    open()
    store.closeOthers(P1, 'files')
    expect(tabIds()).toEqual(['files'])
    expect(panel().activeTabId).toBe('files')

    open()
    store.closeAll(P1)
    expect(tabIds()).toEqual([])
    expect(panel().isOpen).toBe(false)
  })
})

describe('panelTabsStore — persistence is per project', () => {
  beforeEach(() => {
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
  })

  it('round-trips a project configuration through localStorage', async () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, specTabId('doc-1'))
    store.activateTab(P1, 'specs')

    expect(stored().version).toBe(PANEL_TABS_VERSION)

    vi.resetModules()
    const reloaded = await import('@/store/panelTabsStore')
    const restored = reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1)

    expect(restored.tabs.map((t) => t.id)).toEqual(['specs', 'spec:doc-1'])
    expect(restored.activeTabId).toBe('specs')
    expect(restored.isOpen).toBe(true)
  })

  it('does not leak tab configuration between projects', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P2, 'files')

    expect(tabIds(P1)).toEqual(['specs'])
    expect(tabIds(P2)).toEqual(['files'])

    store.closeAll(P1)
    expect(tabIds(P2)).toEqual(['files'])
    expect(panel(P2).isOpen).toBe(true)
  })

  it('returns an empty configuration for a project never opened, and for no project', () => {
    expect(panel('proj-unknown').tabs).toEqual([])
    expect(selectProjectPanel(usePanelTabsStore.getState(), null).isOpen).toBe(false)
  })

  it('persists no width — width stays specPreferences.ts\'s single global value (design D5)', () => {
    usePanelTabsStore.getState().openTab(P1, 'specs')
    expect(JSON.stringify(stored())).not.toMatch(/width/i)
  })
})

describe('panelTabsStore — migration', () => {
  beforeEach(() => {
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
  })

  it('discards a stale shape it has no migration step for, rather than guessing at it', async () => {
    const reloaded = await loadFrom({
      version: 0,
      projects: { [P1]: { tabs: [{ id: 'specs' }], activeTabId: 'specs', isOpen: true } },
    })

    expect(reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1).tabs).toEqual([])
  })

  it('discards state written by a newer version than this build understands', async () => {
    const reloaded = await loadFrom({
      version: PANEL_TABS_VERSION + 1,
      projects: { [P1]: { tabs: [{ id: 'specs' }], activeTabId: 'specs', isOpen: true } },
    })

    expect(reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1).tabs).toEqual([])
  })

  it('migratePanelTabs is a no-op at the current version and parses what it is given', () => {
    const migrated = migratePanelTabs(
      { [P1]: { tabs: [{ id: 'specs', revealRequestId: 3 }], activeTabId: 'specs', isOpen: true } },
      PANEL_TABS_VERSION,
    )

    expect(migrated[P1].tabs).toEqual([{ id: 'specs', revealRequestId: 3 }])
    expect(migrated[P1].activeTabId).toBe('specs')
  })

  it('survives unreadable, non-object and malformed persisted state', async () => {
    localStorage.setItem(KEY, 'not json at all')
    vi.resetModules()
    let reloaded = await import('@/store/panelTabsStore')
    expect(reloaded.usePanelTabsStore.getState().projects).toEqual({})

    reloaded = await loadFrom(['an', 'array'])
    expect(reloaded.usePanelTabsStore.getState().projects).toEqual({})

    // A tab id that is not in the literal union, and a keyed id with an empty key, are dropped —
    // the union is never constructed from persisted input.
    reloaded = await loadFrom({
      version: PANEL_TABS_VERSION,
      projects: {
        [P1]: {
          tabs: [{ id: 'jobs' }, { id: 'spec:' }, { id: 42 }, { id: 'specs' }],
          activeTabId: 'specs',
          isOpen: true,
        },
      },
    })
    const restored = reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1)
    expect(restored.tabs.map((t) => t.id)).toEqual(['specs'])
  })

  it('drops a duplicated persisted tab id rather than restoring two tabs for one item', async () => {
    const reloaded = await loadFrom({
      version: PANEL_TABS_VERSION,
      projects: {
        [P1]: {
          tabs: [{ id: 'spec:doc-1' }, { id: 'spec:doc-1' }],
          activeTabId: 'spec:doc-1',
          isOpen: true,
        },
      },
    })

    const restored = reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1)
    expect(restored.tabs.map((t) => t.id)).toEqual(['spec:doc-1'])
  })
})

describe('panelTabsStore — reconciliation on load', () => {
  beforeEach(() => {
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
  })

  function openThree() {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, specTabId('doc-1'))
    store.openTab(P1, fileTabId('src/gone.ts'))
  }

  it('drops a file tab whose path is not in the workspace listing, and keeps the rest', () => {
    openThree()

    usePanelTabsStore.getState().reconcile(P1, { filePaths: ['src/kept.ts'] })

    expect(tabIds()).toEqual(['specs', 'spec:doc-1'])
  })

  it('keeps a file tab whose path is in the listing', () => {
    usePanelTabsStore.getState().openTab(P1, fileTabId('src/kept.ts'))

    usePanelTabsStore.getState().reconcile(P1, { filePaths: ['src/kept.ts', 'README.md'] })

    expect(tabIds()).toEqual(['file:src/kept.ts'])
  })

  it('drops a spec tab only when the document no longer exists at all', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, specTabId('doc-1'))
    store.openTab(P1, specTabId('doc-gone'))

    store.reconcile(P1, { documentIds: ['doc-1'] })

    expect(tabIds()).toEqual(['spec:doc-1'])
  })

  it('leaves a kind alone when its listing has not loaded yet', () => {
    openThree()

    // No `filePaths` — the workspace listing is unknown, not empty. Reading it as empty here
    // would drop every file tab the operator had open on a slow load.
    usePanelTabsStore.getState().reconcile(P1, { documentIds: ['doc-1'] })

    expect(tabIds()).toEqual(['specs', 'spec:doc-1', 'file:src/gone.ts'])
  })

  it('never touches index tabs, which key nothing and cannot dangle', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, 'files')

    store.reconcile(P1, { filePaths: [], documentIds: [] })

    expect(tabIds()).toEqual(['specs', 'files'])
  })
})

describe('panelTabsStore — the two restore rules (design D5)', () => {
  beforeEach(() => {
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
  })

  it('losing every tab restores the shell closed, not open and empty', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, fileTabId('src/gone.ts'))
    expect(panel().isOpen).toBe(true)

    store.reconcile(P1, { filePaths: [] })

    expect(tabIds()).toEqual([])
    expect(panel().activeTabId).toBeNull()
    expect(panel().isOpen).toBe(false)
  })

  it('losing every tab through persisted state restores the shell closed', async () => {
    const reloaded = await loadFrom({
      version: PANEL_TABS_VERSION,
      projects: { [P1]: { tabs: [], activeTabId: 'specs', isOpen: true } },
    })

    const restored = reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1)
    expect(restored.isOpen).toBe(false)
    expect(restored.activeTabId).toBeNull()
  })

  it('losing the visible tab while others survive promotes a survivor', () => {
    const store = usePanelTabsStore.getState()
    store.openTab(P1, 'specs')
    store.openTab(P1, fileTabId('src/gone.ts'))
    expect(panel().activeTabId).toBe('file:src/gone.ts')

    store.reconcile(P1, { filePaths: [] })

    expect(tabIds()).toEqual(['specs'])
    expect(panel().activeTabId).toBe('specs')
    expect(panel().isOpen).toBe(true)
  })

  it('a persisted activeTabId naming a tab that is not in the strip promotes a survivor', async () => {
    const reloaded = await loadFrom({
      version: PANEL_TABS_VERSION,
      projects: {
        [P1]: { tabs: [{ id: 'specs' }], activeTabId: 'spec:doc-vanished', isOpen: true },
      },
    })

    const restored = reloaded.selectProjectPanel(reloaded.usePanelTabsStore.getState(), P1)
    expect(restored.activeTabId).toBe('specs')
    expect(restored.isOpen).toBe(true)
  })
})
