import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { selectOverviewTabs, useOverviewTabsStore, type OverviewTabId } from '@/store/overviewTabsStore'
import '@/styles/overview-tabs.css'
import { overviewPanelDomId, overviewTabDomId } from './overviewLiveModel'

/** The Overview's two tabs, side by side like browser tabs (FR-1). Drag one to put it first, or
 *  focus it and press Ctrl+Shift+Left/Right; the first tab is the one a fresh Overview opens on.
 *  Plain Left/Right move between the tabs, as a tab list's keys do. */

const LABEL: Record<OverviewTabId, { label: string; icon: string }> = {
  dashboard: { label: 'Dashboard', icon: 'bar_chart' },
  briefing: { label: 'Briefing', icon: 'edit_note' },
}


export function OverviewTabs({
  projectId,
  active,
  onOpen,
}: {
  projectId: string
  active: OverviewTabId
  onOpen: (tab: OverviewTabId) => void
}) {
  const { order } = useOverviewTabsStore((s) => selectOverviewTabs(s, projectId))
  const moveTab = useOverviewTabsStore((s) => s.moveTab)
  const [dragging, setDragging] = React.useState<OverviewTabId | null>(null)
  const [over, setOver] = React.useState<OverviewTabId | null>(null)
  const refs = React.useRef<Partial<Record<OverviewTabId, HTMLButtonElement | null>>>({})

  const endDrag = () => {
    setDragging(null)
    setOver(null)
  }
  const focusTab = (tab: OverviewTabId) => requestAnimationFrame(() => refs.current[tab]?.focus())

  const onKeyDown = (event: React.KeyboardEvent, tab: OverviewTabId, index: number) => {
    const step = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
    if (step === 0) return
    event.preventDefault()
    const target = Math.max(0, Math.min(order.length - 1, index + step))
    if (event.shiftKey && (event.ctrlKey || event.metaKey)) {
      if (target !== index) moveTab(projectId, tab, target)
      focusTab(tab)
      return
    }
    const next = order[target]!
    onOpen(next)
    focusTab(next)
  }

  return (
    <div className="aw-ovt" role="tablist" aria-label="Overview views" data-dragging={dragging ? 'true' : 'false'}>
      {order.map((tab, index) => (
        <button
          key={tab}
          ref={(el) => {
            refs.current[tab] = el
          }}
          type="button"
          role="tab"
          id={overviewTabDomId(tab)}
          aria-controls={overviewPanelDomId(tab)}
          aria-selected={tab === active}
          tabIndex={tab === active ? 0 : -1}
          data-slot="overview-tab"
          data-tab={tab}
          data-dragging={dragging === tab ? 'true' : undefined}
          data-drop={over === tab && dragging && dragging !== tab ? (order.indexOf(dragging) > index ? 'before' : 'after') : undefined}
          className="aw-ovt-tab"
          draggable
          title={`${LABEL[tab].label}. Drag, or press Ctrl+Shift+Left or Right, to move it; the first tab opens first`}
          aria-roledescription="draggable tab"
          onClick={() => onOpen(tab)}
          onKeyDown={(e) => onKeyDown(e, tab, index)}
          onDragStart={(e) => {
            setDragging(tab)
            e.dataTransfer.effectAllowed = 'move'
            // Firefox starts no drag without data.
            e.dataTransfer.setData('text/plain', tab)
          }}
          onDragEnter={(e) => {
            if (dragging && dragging !== tab) {
              e.preventDefault()
              setOver(tab)
            }
          }}
          onDragOver={(e) => {
            if (dragging && dragging !== tab) {
              e.preventDefault()
              e.dataTransfer.dropEffect = 'move'
              if (over !== tab) setOver(tab)
            }
          }}
          onDragLeave={() => setOver((current) => (current === tab ? null : current))}
          onDrop={(e) => {
            e.preventDefault()
            const moving = dragging ?? (e.dataTransfer.getData('text/plain') as OverviewTabId)
            if (moving && moving !== tab && (moving === 'dashboard' || moving === 'briefing')) {
              moveTab(projectId, moving, index)
              onOpen(moving)
            }
            endDrag()
          }}
          onDragEnd={endDrag}
        >
          <Icon name={LABEL[tab].icon} size={15} />
          <span>{LABEL[tab].label}</span>
        </button>
      ))}
    </div>
  )
}
