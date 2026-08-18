import { useRef } from 'react'
import { Icon } from '@/components/common/Icon'
import { RowMenu, type RowMenuItem } from '@/components/layout/RowMenu'
import {
  selectProjectPanel,
  usePanelTabsStore,
  type PanelTab,
  type TabId,
} from '@/store/panelTabsStore'

/** What a tab looks like in the strip and in the plus menu — never the raw `TabId`, which is an
 *  internal key, not a caption. */
export interface PanelTabDescriptor {
  id: TabId
  label: string
  icon: string
}

interface PanelShellProps {
  projectId: string
  /** Index tabs the plus affordance can open, in a fixed display order. Only entries not already
   *  open are offered — "the plus adds what is not open" (design D2). */
  availableTabs: PanelTabDescriptor[]
  /** Resolves display info for any open tab, index or keyed detail — the shell itself has no idea
   *  what a `spec:` or `file:` tab is named; the caller does. */
  describeTab: (id: TabId) => PanelTabDescriptor
  /** Renders the active tab's content. Called for the visible tab only — "one tab's content
   *  rendered at a time" (task 2.1). */
  renderTabContent: (tab: PanelTab) => React.ReactNode
}

/**
 * The shell that owns the tab strip, the plus affordance, and the visible tab's content.
 *
 * Re-hosting `ConversationView`'s panel block (task 2.2), the resize/overlay behaviour (2.3/2.4)
 * and real tenants (section 3+) are deliberately later tasks — this component is deliberately
 * generic so none of that has to be re-plumbed once they land (openspec change
 * `2026-08-18-one-shell-three-panels`, task list section 1→2→3 ordering).
 *
 * Keyboard follows the WAI-ARIA `tablist` pattern with **automatic activation** (design D11: "the
 * first controls of their kind in this codebase, so nothing exists to inherit" — this is a stated
 * choice, not an inherited one). Arrow keys move focus between tabs and activate as they go; only
 * the active tab sits in the page's Tab sequence (roving `tabIndex`), so a plain `Tab` press
 * leaves the strip in one step. `Enter`/`Space` activate the focused tab via the browser's native
 * button behaviour — no extra handler needed. The close control is a second, ordinary button
 * inside the same tab, so `Tab` reaches it right after its tab; it needs no roving index of its
 * own because it is never a stop arrow keys visit.
 */
export function PanelShell({ projectId, availableTabs, describeTab, renderTabContent }: PanelShellProps) {
  const projects = usePanelTabsStore((state) => state.projects)
  const openTab = usePanelTabsStore((state) => state.openTab)
  const closeTab = usePanelTabsStore((state) => state.closeTab)
  const activateTab = usePanelTabsStore((state) => state.activateTab)

  const panel = selectProjectPanel({ projects }, projectId)
  const activeTab = panel.tabs.find((tab) => tab.id === panel.activeTabId) ?? null

  const tabButtons = useRef<Map<TabId, HTMLButtonElement>>(new Map())
  const registerTabButton = (id: TabId) => (el: HTMLButtonElement | null) => {
    if (el) tabButtons.current.set(id, el)
    else tabButtons.current.delete(id)
  }

  function moveFocus(index: number) {
    const target = panel.tabs[index]
    if (!target) return
    activateTab(projectId, target.id)
    tabButtons.current.get(target.id)?.focus()
  }

  function handleStripKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (panel.tabs.length === 0) return
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault()
        moveFocus((index + 1) % panel.tabs.length)
        return
      case 'ArrowLeft':
        event.preventDefault()
        moveFocus((index - 1 + panel.tabs.length) % panel.tabs.length)
        return
      case 'Home':
        event.preventDefault()
        moveFocus(0)
        return
      case 'End':
        event.preventDefault()
        moveFocus(panel.tabs.length - 1)
        return
      default:
        return
    }
  }

  // Only tabs not already open are worth adding — the store already refocuses rather than
  // duplicating, but offering an already-open tab in the plus menu would read as "open a second
  // one" when it does no such thing.
  const menuItems: RowMenuItem[] = availableTabs
    .filter((descriptor) => !panel.tabs.some((tab) => tab.id === descriptor.id))
    .map((descriptor) => ({
      id: descriptor.id,
      label: descriptor.label,
      onSelect: () => openTab(projectId, descriptor.id),
    }))

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col" data-testid="panel-shell">
      <div
        role="tablist"
        aria-label="Panel"
        aria-orientation="horizontal"
        className="flex shrink-0 items-center gap-0.5 overflow-x-auto px-1"
        style={{ borderBottom: '1px solid var(--border)' }}
        data-testid="panel-tab-strip"
      >
        {panel.tabs.map((tab, index) => {
          const descriptor = describeTab(tab.id)
          const selected = tab.id === panel.activeTabId
          return (
            <div
              key={tab.id}
              className="flex shrink-0 items-center gap-1 rounded-t-[var(--radius-sm)] px-1.5 py-1"
              style={{
                background: selected ? 'var(--surface-2)' : 'transparent',
                color: selected ? 'var(--text-1)' : 'var(--text-2)',
              }}
            >
              <button
                type="button"
                role="tab"
                id={`panel-tab-${tab.id}`}
                aria-selected={selected}
                aria-controls={selected ? 'panel-tabpanel' : undefined}
                tabIndex={selected ? 0 : -1}
                ref={registerTabButton(tab.id)}
                data-testid={`panel-tab-${tab.id}`}
                className="flex min-w-0 items-center gap-1.5 border-0 bg-transparent"
                style={{ fontSize: 12, cursor: 'pointer', padding: '2px 2px' }}
                onClick={() => activateTab(projectId, tab.id)}
                onKeyDown={(event) => handleStripKeyDown(event, index)}
              >
                <Icon name={descriptor.icon} size={14} />
                <span className="max-w-[140px] truncate">{descriptor.label}</span>
              </button>
              <button
                type="button"
                aria-label={`Close ${descriptor.label}`}
                title={`Close ${descriptor.label}`}
                data-testid={`panel-tab-close-${tab.id}`}
                className="flex border-0 bg-transparent"
                style={{ cursor: 'pointer', color: 'var(--text-3)', padding: 2 }}
                onClick={(event) => {
                  // The tab's own onClick would otherwise fire too, activating a tab this same
                  // click is closing.
                  event.stopPropagation()
                  closeTab(projectId, tab.id)
                }}
              >
                <Icon name="close" size={12} />
              </button>
            </div>
          )
        })}
        {menuItems.length > 0 && (
          <RowMenu label="Add a tab" items={menuItems} testId="panel-tab-add" persistent icon="add" />
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {activeTab ? (
          <div
            role="tabpanel"
            id="panel-tabpanel"
            aria-labelledby={`panel-tab-${activeTab.id}`}
            className="h-full min-h-0"
            data-testid="panel-tab-content"
          >
            {renderTabContent(activeTab)}
          </div>
        ) : (
          // Task 2.1 / user test guide step 1: a shell with nothing open is a real, chosen state
          // (task 3's specs-index tenant is what usually fills this), never an empty grey box.
          <div
            className="flex h-full items-center justify-center p-4 text-center"
            style={{ color: 'var(--text-3)', fontSize: 12 }}
            data-testid="panel-empty-state"
          >
            No tabs open. Use the + button to add one.
          </div>
        )}
      </div>
    </div>
  )
}
