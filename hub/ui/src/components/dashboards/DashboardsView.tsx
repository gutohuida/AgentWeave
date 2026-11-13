import * as React from 'react'
import type { DashboardRun, DashboardSummary } from '@/api/dashboards'
import { Icon } from '@/components/common/Icon'
import { PanelChart } from './PanelChart'
import { hubDate } from '@/lib/hubTime'

const when = (iso: string | null) => (iso ? hubDate(iso).toLocaleString() : '—')

export interface DashboardsViewProps {
  dashboards: DashboardSummary[]
  selectedId: string | null
  /** The opened dashboard's last run; null while it is being fetched. */
  run: DashboardRun | null
  refreshing: boolean
  /** Why the list or the run could not be read, shown in place of it. */
  error?: string | null
  onSelect: (id: string | null) => void
  onRefresh: () => void
  onDelete: (dashboard: DashboardSummary) => void
}

/**
 * The Dashboards tab (FR-11): the project's dashboards with name, author and date; opening one
 * shows its panels as the last run drew them, when that run was fetched, a Refresh button and, for
 * the operator, Delete. Props only, so the mock and the app render the same component.
 */
export function DashboardsView({ dashboards, selectedId, run, refreshing, error, onSelect, onRefresh, onDelete }: DashboardsViewProps) {
  const [confirming, setConfirming] = React.useState(false)
  React.useEffect(() => setConfirming(false), [selectedId])
  const selected = dashboards.find((d) => d.id === selectedId) ?? null

  if (!selected) {
    return (
      <div className="mx-auto max-w-3xl p-6" data-testid="dashboards-list">
        <h1 className="mb-4 text-lg font-semibold" style={{ color: 'var(--text)' }}>
          Dashboards
        </h1>
        {error && (
          <div role="alert" className="mb-3 rounded-md px-3 py-2 text-xs" style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)' }}>
            {error}
          </div>
        )}
        {dashboards.length === 0 && !error ? (
          <div className="rounded-lg p-8 text-center text-sm" style={{ border: '1px dashed var(--border-hi)', color: 'var(--text-3)' }}>
            <Icon name="insights" size={18} />
            <p className="mt-2">No dashboards yet. Ask any agent for one and it will appear here.</p>
          </div>
        ) : (
          <ul className="flex flex-col" style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
            {dashboards.map((d, i) => (
              <li key={d.id} style={{ borderTop: i ? '1px solid var(--border)' : undefined }}>
                <button
                  type="button"
                  data-testid="dashboard-row"
                  data-dashboard-id={d.id}
                  onClick={() => onSelect(d.id)}
                  className="flex w-full items-baseline gap-3 px-4 py-3 text-left"
                  style={{ color: 'var(--text)' }}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{d.name}</span>
                    {d.description && (
                      <span className="block truncate text-xs" style={{ color: 'var(--text-3)' }}>
                        {d.description}
                      </span>
                    )}
                  </span>
                  <span className="text-xs" style={{ color: 'var(--text-2)' }}>
                    {d.author}
                  </span>
                  <span className="text-xs tabular-nums" style={{ color: 'var(--text-3)' }}>
                    {when(d.updated_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl p-6" data-testid="dashboard-view" data-dashboard-id={selected.id}>
      <button type="button" onClick={() => onSelect(null)} className="mb-3 inline-flex items-center gap-1 text-xs" style={{ color: 'var(--text-2)' }}>
        <Icon name="arrow_back" size={13} /> All dashboards
      </button>
      <div className="mb-4 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
            {selected.name}
          </h1>
          {selected.description && (
            <p className="text-sm" style={{ color: 'var(--text-2)' }}>
              {selected.description}
            </p>
          )}
          <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
            By {selected.author} · saved {when(selected.updated_at)}
            {run && (
              <>
                {' · '}
                <span data-testid="dashboard-fetched-at" data-fetched-at={hubDate(run.fetched_at).toISOString()}>Fetched {hubDate(run.fetched_at).toLocaleTimeString()}</span>
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          data-testid="dashboard-refresh"
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs"
          style={{ border: '1px solid var(--border-hi)', color: 'var(--text)', opacity: refreshing ? 0.6 : 1 }}
        >
          <Icon name="refresh" size={13} /> {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
        {confirming ? (
          <span className="inline-flex items-center gap-2 text-xs">
            <button
              type="button"
              data-testid="dashboard-delete-confirm"
              onClick={() => onDelete(selected)}
              className="rounded-md px-3 py-1.5"
              style={{ background: 'var(--destructive)', color: 'var(--destructive-fg)' }}
            >
              Delete dashboard
            </button>
            <button type="button" onClick={() => setConfirming(false)} style={{ color: 'var(--text-2)' }}>
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            data-testid="dashboard-delete"
            onClick={() => setConfirming(true)}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs"
            style={{ border: '1px solid var(--border-hi)', color: 'var(--destructive)' }}
          >
            <Icon name="delete" size={13} /> Delete
          </button>
        )}
      </div>
      {error && (
        <div role="alert" className="mb-3 rounded-md px-3 py-2 text-xs" style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)' }}>
          {error}
        </div>
      )}
      {!run && !error && (
        <p className="text-sm" style={{ color: 'var(--text-3)' }}>
          Running its queries…
        </p>
      )}
      <div className="grid gap-4">
        {run?.panels.map((panel) => (
          <section key={panel.id} data-testid="dashboard-panel" data-panel-id={panel.id} data-kind={panel.kind} className="rounded-lg p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <h2 className="mb-3 text-sm font-medium" style={{ color: 'var(--text)' }}>
              {panel.title}
            </h2>
            <PanelChart panel={panel} />
            {panel.truncated && (
              <p className="mt-2 text-xs" style={{ color: 'var(--text-3)' }}>
                Showing the first {panel.rows.length} of {panel.row_count} rows.
              </p>
            )}
          </section>
        ))}
      </div>
    </div>
  )
}
