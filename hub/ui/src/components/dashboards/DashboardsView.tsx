import * as React from 'react'
import type { DashboardRun, DashboardSummary } from '@/api/dashboards'
import { Icon } from '@/components/common/Icon'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/menu'
import { PanelChart } from './PanelChart'
import { usePanelPresence } from './usePanelPresence'
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
  /** Restores the version the last edit replaced; offered only when the dashboard can_undo. */
  onUndo?: (dashboard: DashboardSummary) => void
  /** The agents Ask to change offers; the control is hidden when there are none. */
  askAgents?: string[]
  /** Opens that agent's conversation with the dashboard named in its composer, unsent. */
  onAskToChange?: (dashboard: DashboardSummary, agent: string) => void
}

const outlineButton = 'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs'

/**
 * The Dashboards tab (FR-11): the project's dashboards with name, author and date; opening one
 * shows its panels as the last run drew them, when that run was fetched, a Refresh button and, for
 * the operator, Delete. Props only, so the mock and the app render the same component.
 */
export function DashboardsView({ dashboards, selectedId, run, refreshing, error, onSelect, onRefresh, onDelete, onUndo, askAgents = [], onAskToChange }: DashboardsViewProps) {
  const [confirming, setConfirming] = React.useState(false)
  React.useEffect(() => setConfirming(false), [selectedId])
  const selected = dashboards.find((d) => d.id === selectedId) ?? null
  const present = usePanelPresence(selectedId, run?.panels ?? null)

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
            By {selected.author} · <span className="whitespace-nowrap">saved {when(selected.updated_at)}</span>
            {selected.edited_by && (
              <span data-testid="dashboard-edited-by" className="whitespace-nowrap">
                {' · '}edited by {selected.edited_by} {when(selected.edited_at ?? null)}
              </span>
            )}
            {run && (
              <>
                {' · '}
                <span data-testid="dashboard-fetched-at" data-fetched-at={hubDate(run.fetched_at).toISOString()}>Fetched {hubDate(run.fetched_at).toLocaleTimeString()}</span>
              </>
            )}
          </p>
        </div>
        {onAskToChange && askAgents.length > 0 && (
          <Menu>
            <MenuTrigger asChild>
              <button type="button" data-testid="dashboard-ask-to-change" className={outlineButton} style={{ border: '1px solid var(--border-hi)', color: 'var(--text)' }}>
                <Icon name="chat" size={13} /> Ask to change
              </button>
            </MenuTrigger>
            <MenuContent>
              <MenuLabel>Ask an agent to change it</MenuLabel>
              {askAgents.map((agent) => (
                <MenuItem key={agent} icon="smart_toy" data-testid="dashboard-ask-agent" onSelect={() => onAskToChange(selected, agent)}>
                  {agent}
                </MenuItem>
              ))}
            </MenuContent>
          </Menu>
        )}
        {onUndo && selected.can_undo && (
          <button
            type="button"
            data-testid="dashboard-undo"
            onClick={() => onUndo(selected)}
            title={selected.edited_by ? `Restore the version before ${selected.edited_by}'s edit` : 'Restore the previous version'}
            className={outlineButton}
            style={{ border: '1px solid var(--border-hi)', color: 'var(--text)' }}
          >
            <Icon name="undo" size={13} /> Undo
          </button>
        )}
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
      {!run && !error && <PanelSkeletons count={selected.panel_count} />}
      <div className={`aw-dash-panels grid gap-4${refreshing ? ' is-refreshing' : ''}`}>
        {present.map(({ panel, state }, i) => (
          <section
            key={panel.id}
            data-testid={state === 'leaving' ? 'dashboard-panel-leaving' : 'dashboard-panel'}
            data-panel-id={panel.id}
            data-kind={panel.kind}
            data-state={state}
            className={`aw-dash-panel rounded-lg p-4${state === 'new' ? ' is-new' : ''}${state === 'leaving' ? ' is-leaving' : ''}`}
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', ['--i' as string]: i } as React.CSSProperties}
          >
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

/** Stand-ins shaped like panels while a dashboard's queries first run. */
function PanelSkeletons({ count }: { count: number }) {
  return (
    <div className="grid gap-4" data-testid="dashboard-skeleton" aria-label="Running its queries" role="status">
      {Array.from({ length: Math.max(1, Math.min(count, 4)) }, (_, i) => (
        <div key={i} className="rounded-lg p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div className="aw-dash-skeleton mb-4 h-3.5 w-40" />
          <div className="flex flex-col gap-2">
            {[82, 64, 46, 30].map((w) => (
              <div key={w} className="aw-dash-skeleton h-3" style={{ width: `${w}%` }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
