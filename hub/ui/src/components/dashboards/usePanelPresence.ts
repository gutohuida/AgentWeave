import * as React from 'react'
import type { PanelRun } from '@/api/dashboards'

export interface PresentPanel {
  panel: PanelRun
  /** `new`: an edit added it since the dashboard was opened; `leaving`: an edit removed it, and it
   *  stays on screen only long enough to fade out. */
  state: 'shown' | 'new' | 'leaving'
}

/**
 * Which panels to draw, so an edit is visible as an edit: a panel added since the dashboard was
 * opened is marked new, and one removed is kept, where it was, for `leaveMs` while it fades. On
 * first opening a dashboard nothing is new; its panels simply arrive.
 */
export function usePanelPresence(dashboardId: string | null, panels: PanelRun[] | null, leaveMs = 280): PresentPanel[] {
  const seen = React.useRef<{ dashboardId: string | null; panels: PanelRun[] | null; added: Set<string> }>({
    dashboardId,
    panels: null,
    added: new Set(),
  })
  const [leaving, setLeaving] = React.useState<{ panel: PanelRun; index: number }[]>([])

  if (seen.current.dashboardId !== dashboardId) seen.current = { dashboardId, panels: null, added: new Set() }
  const before = seen.current.panels
  if (before && panels) {
    const had = new Set(before.map((p) => p.id))
    for (const p of panels) if (!had.has(p.id)) seen.current.added.add(p.id)
  }

  React.useEffect(() => {
    const previous = seen.current.panels
    seen.current.panels = panels
    if (!previous || !panels) {
      setLeaving([])
      return
    }
    const now = new Set(panels.map((p) => p.id))
    const gone = previous.flatMap((panel, index) => (now.has(panel.id) ? [] : [{ panel, index }]))
    if (!gone.length) return
    setLeaving(gone)
    const timer = window.setTimeout(() => setLeaving([]), leaveMs)
    return () => window.clearTimeout(timer)
  }, [panels, leaveMs])

  const shown: PresentPanel[] = (panels ?? []).map((panel) => ({ panel, state: seen.current.added.has(panel.id) ? 'new' : 'shown' }))
  for (const { panel, index } of leaving) {
    if (shown.some((p) => p.panel.id === panel.id)) continue
    shown.splice(Math.min(index, shown.length), 0, { panel, state: 'leaving' })
  }
  return shown
}
