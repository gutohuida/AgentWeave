import * as React from 'react'
import type { DashboardRun, DashboardSummary, PanelRun } from '@/api/dashboards'
import { DashboardsView } from '@/components/dashboards/DashboardsView'
import { askToChangeLine } from '@/components/dashboards/askToChange'
import { toast } from '@/lib/toast'
import type { ScreenProps } from '../routes'

// mock state: the replica has no dashboards, so these are the shapes `GET .../run` answers, one
// panel of each chart kind plus the two refusals a panel can show. The long output line is the
// FR-15 case: the whole value, marker included, must be in the cell.
const LONG = `${'The agent ran the checks and reported each result in turn. '.repeat(34)}MARKER-7f3a`

const panel = (p: Partial<PanelRun> & Pick<PanelRun, 'id' | 'title' | 'kind' | 'columns' | 'rows'>): PanelRun => ({
  query: 'select …',
  row_count: p.rows.length,
  truncated: false,
  elapsed_ms: 4,
  error: null,
  warning: null,
  ...p,
})

const PANELS: PanelRun[] = [
  panel({ id: 'p1', title: 'Cost this week (USD)', kind: 'number', columns: ['cost'], rows: [[184.32]] }),
  panel({ id: 'p2', title: 'Cost per spec', kind: 'bar', columns: ['spec', 'cost'], rows: [['Dashboards', 61.2], ['Vault facts', 44.8], ['Thread chapters', 31.05], ['Landing', 12.6]] }),
  panel({ id: 'p3', title: 'Send-backs per model', kind: 'stacked_bar', columns: ['model', 'defect', 'regression', 'flaky'], rows: [['sonnet-5-5', 6, 2, 1], ['opus-5-5', 2, 1, 0], ['gpt-6.1-sol', 3, 3, 2]] }),
  panel({ id: 'p4', title: 'Runs per day', kind: 'line', columns: ['day', 'runs', 'failed'], rows: [['Nov 7', 22, 3], ['Nov 8', 31, 4], ['Nov 9', 12, 1], ['Nov 10', 40, 6], ['Nov 11', 37, 2], ['Nov 12', 52, 5]] }),
  panel({ id: 'p5', title: 'Latest agent output', kind: 'table', columns: ['run', 'agent', 'output'], rows: [['run-91c2', 'Developer', LONG], ['run-91c1', 'QA2', 'All six checks passed.'], ['run-91be', 'Architect', null]] }),
  panel({ id: 'p6', title: 'Send-backs by reason', kind: 'bar', columns: ['reason'], rows: [], error: { code: 'query_error', message: 'no such column: reason_class' } }),
  panel({ id: 'p7', title: 'Specs over time', kind: 'line', columns: ['spec', 'state'], rows: [['A', 'approved'], ['B', 'exploring']], warning: 'A line chart needs a numeric column after the first (label) column; none of state is numeric.' }),
]

// mock state (slice change-by-asking): dash-1 was edited by Developer, who added "Runs per day"
// (p4), so Undo restores the version without it; restoring is itself an edit, so Undo then puts it
// back. dash-2 was never edited and offers no Undo.
const SUMMARIES: DashboardSummary[] = [
  { id: 'dash-1', name: 'Where the spend goes', description: 'Cost, send-backs and run volume.', author: 'Architect', created_at: '2026-10-16T09:00:00Z', updated_at: '2026-10-17T10:30:00Z', panel_count: PANELS.length, version: 3, edited_by: 'Developer', edited_at: '2026-10-17T10:30:00Z', can_undo: true },
  { id: 'dash-2', name: 'Review queue', description: '', author: 'operator', created_at: '2026-10-15T09:00:00Z', updated_at: '2026-10-15T09:00:00Z', panel_count: 2, version: 1, edited_by: null, edited_at: null, can_undo: false },
]

// mock state: the project's agents, as Ask to change offers them.
const AGENTS = ['Architect', 'Developer', 'DeveloperOpus2', 'QA']

export default function Dashboards({ now }: ScreenProps) {
  const [dashboards, setDashboards] = React.useState(SUMMARIES)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [fetchedAt, setFetchedAt] = React.useState(now)
  const [withoutRunsPerDay, setWithoutRunsPerDay] = React.useState(false)
  const panels = withoutRunsPerDay ? PANELS.filter((p) => p.id !== 'p4') : PANELS
  const run: DashboardRun | null = selectedId
    ? { id: selectedId, name: '', description: '', author: '', updated_at: null, fetched_at: fetchedAt.toISOString(), panels }
    : null
  return (
    <DashboardsView
      dashboards={dashboards}
      selectedId={selectedId}
      run={run}
      refreshing={false}
      onSelect={setSelectedId}
      onRefresh={() => setFetchedAt(new Date())}
      askAgents={AGENTS}
      onAskToChange={(d, agent) =>
        toast({ title: `Opens ${agent}'s new conversation`, description: `Composer, unsent: ${askToChangeLine(d)}`, tone: 'neutral' })
      }
      onUndo={(d) => {
        const at = new Date().toISOString()
        setWithoutRunsPerDay((v) => !v)
        setDashboards((all) => all.map((x) => (x.id === d.id ? { ...x, version: (x.version ?? 1) + 1, edited_by: 'operator', edited_at: at, updated_at: at } : x)))
        toast({ title: `Restored the previous version of ${d.name}`, tone: 'success' })
      }}
      onDelete={(d) => {
        setDashboards((all) => all.filter((x) => x.id !== d.id))
        setSelectedId(null)
        toast({ title: `Deleted ${d.name}`, tone: 'success' })
      }}
    />
  )
}
