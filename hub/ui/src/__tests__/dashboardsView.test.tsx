import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { DashboardRun, PanelRun } from '@/api/dashboards'
import { DashboardsView } from '@/components/dashboards/DashboardsView'

const panel = (p: Partial<PanelRun> & Pick<PanelRun, 'id' | 'title' | 'kind' | 'columns' | 'rows'>): PanelRun => ({
  query: 'select 1', row_count: p.rows.length, truncated: false, elapsed_ms: 1, error: null, warning: null, ...p,
})
const LONG = `${'x'.repeat(2000)}MARKER-42`
const run = (panels: PanelRun[], fetched = '2026-11-13T10:00:00Z'): DashboardRun => ({
  id: 'd1', name: 'D', description: '', author: 'Architect', updated_at: null, fetched_at: fetched, panels,
})
const summary = { id: 'd1', name: 'Spend', description: '', author: 'Architect', created_at: null, updated_at: '2026-11-12T10:00:00Z', panel_count: 1 }

function open(panels: PanelRun[], extra: Partial<React.ComponentProps<typeof DashboardsView>> = {}) {
  return render(
    <DashboardsView dashboards={[summary]} selectedId="d1" run={run(panels)} refreshing={false}
      onSelect={() => {}} onRefresh={() => {}} onDelete={() => {}} {...extra} />,
  )
}

describe('DashboardsView', () => {
  it('lists name and author, and selects on click', () => {
    const onSelect = vi.fn()
    render(<DashboardsView dashboards={[summary]} selectedId={null} run={null} refreshing={false}
      onSelect={onSelect} onRefresh={() => {}} onDelete={() => {}} />)
    fireEvent.click(screen.getByText('Spend'))
    expect(screen.getByText('Architect')).toBeTruthy()
    expect(onSelect).toHaveBeenCalledWith('d1')
  })

  it('draws one panel of each chart kind', () => {
    open([
      panel({ id: 'a', title: 'n', kind: 'number', columns: ['c'], rows: [[5]] }),
      panel({ id: 'b', title: 't', kind: 'table', columns: ['c'], rows: [['v']] }),
      panel({ id: 'c', title: 'b', kind: 'bar', columns: ['l', 'v'], rows: [['x', 1], ['y', 2]] }),
      panel({ id: 'd', title: 's', kind: 'stacked_bar', columns: ['l', 'v', 'w'], rows: [['x', 1, 2]] }),
      panel({ id: 'e', title: 'l', kind: 'line', columns: ['l', 'v'], rows: [['x', 1], ['y', 2]] }),
    ])
    for (const id of ['chart-number', 'chart-table', 'chart-bar', 'chart-stacked-bar', 'chart-line']) {
      expect(screen.getByTestId(id)).toBeTruthy()
    }
  })

  it('shows a 2,000-character value in full, marker included', () => {
    open([panel({ id: 'a', title: 't', kind: 'table', columns: ['out'], rows: [[LONG]] })])
    expect(screen.getByTestId('chart-table').textContent).toContain(LONG)
  })

  it('shows the error, the warning, and still draws the working panel', () => {
    open([
      panel({ id: 'a', title: 'bad', kind: 'bar', columns: [], rows: [], error: { message: 'no such column: nope' } }),
      panel({ id: 'b', title: 'flat', kind: 'line', columns: ['l', 'v'], rows: [['x', 'y']], warning: 'needs a numeric column' }),
      panel({ id: 'c', title: 'ok', kind: 'number', columns: ['c'], rows: [[7]] }),
    ])
    expect(screen.getByTestId('dashboard-panel-error').textContent).toContain('no such column: nope')
    expect(screen.getByTestId('dashboard-panel-warning').textContent).toContain('needs a numeric column')
    expect(screen.getByTestId('dashboard-number').textContent).toBe('7')
  })

  it('refreshes, and deletes only after confirming', () => {
    const onRefresh = vi.fn()
    const onDelete = vi.fn()
    open([], { onRefresh, onDelete })
    fireEvent.click(screen.getByText('Refresh'))
    expect(onRefresh).toHaveBeenCalled()
    fireEvent.click(screen.getByText('Delete'))
    expect(onDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Delete dashboard'))
    expect(onDelete).toHaveBeenCalledWith(summary)
    expect(screen.getByTestId('dashboard-fetched-at').getAttribute('data-fetched-at')).toMatch(/^\d{4}-\d\d-\d\dT/)
    expect(screen.getByTestId('dashboard-view').getAttribute('data-dashboard-id')).toBe(summary.id)
    expect(screen.getByTestId('dashboard-refresh')).toBeTruthy()
  })

  it('carries the acceptance drive ids: panels by kind, SVG bars, table cells', () => {
    open([
      panel({ id: 'c', title: 'b', kind: 'bar', columns: ['l', 'v'], rows: [['x', 1], ['y', 2]] }),
      panel({ id: 'd', title: 's', kind: 'stacked_bar', columns: ['l', 'v', 'w'], rows: [['x', 1, 2]] }),
      panel({ id: 'b', title: 't', kind: 'table', columns: ['c'], rows: [['v']] }),
    ])
    for (const kind of ['bar', 'stacked_bar']) {
      const panel = document.querySelector(`[data-testid=dashboard-panel][data-kind=${kind}]`)
      expect(panel?.querySelector('svg')).toBeTruthy()
    }
    expect(screen.getAllByTestId('dashboard-table-cell').length).toBeGreaterThan(0)
  })

  it('offers Undo only when the run says there is a version to restore', () => {
    const onUndo = vi.fn()
    const { unmount } = open([], { onUndo })
    expect(screen.queryByTestId('dashboard-undo')).toBeNull()
    unmount()
    render(<DashboardsView dashboards={[summary]} selectedId="d1" run={{ ...run([]), can_undo: true }} refreshing={false}
      onSelect={() => {}} onRefresh={() => {}} onDelete={() => {}} onUndo={onUndo} />)
    fireEvent.click(screen.getByTestId('dashboard-undo'))
    expect(onUndo).toHaveBeenCalledWith(summary)
  })

  it('shows who last edited it and when', () => {
    render(<DashboardsView dashboards={[summary]} selectedId="d1" refreshing={false}
      run={{ ...run([]), edited_by: 'Developer', edited_at: '2026-11-14T08:15:00Z' }}
      onSelect={() => {}} onRefresh={() => {}} onDelete={() => {}} />)
    expect(screen.getByTestId('dashboard-edited-by').textContent).toContain('Edited by Developer')
    expect(screen.getByTestId('dashboard-edited-by').getAttribute('data-edited-at')).toBe('2026-11-14T08:15:00Z')
    expect(screen.getByTestId('dashboard-edited-by').textContent).not.toContain('—')
  })

  it('Ask to change picks an agent and reports it, and does nothing before that', () => {
    const onAsk = vi.fn()
    open([], { agents: ['Architect', 'QA'], onAskToChange: onAsk })
    fireEvent.click(screen.getByTestId('dashboard-ask-to-change'))
    expect(onAsk).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('QA'))
    expect(onAsk).toHaveBeenCalledWith(summary, 'QA')
  })
})
