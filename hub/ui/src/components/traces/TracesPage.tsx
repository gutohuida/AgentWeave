import * as React from 'react'
import type { TraceKind } from '@/api/traces'
import { Icon } from '@/components/common/Icon'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSelect, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { agentColorVars } from '@/lib/agentColors'
import { formatCount, formatDateTime, formatDuration, formatMoney, formatTokens, formatTokensExact } from '@/lib/format'
import {
  durationSeconds,
  errorLabel,
  GROUPING_LABELS,
  KIND_LABELS,
  modelLabel,
  RANGE_LABELS,
  type TimeRange,
  type TraceFilters,
  type TraceGroup,
  type TraceGrouping,
  type TraceRow,
  type TraceTotals,
  taskName,
} from './tracesModel'
import '@/styles/traces.css'

/**
 * The traces view (a-traces-view-with-filters-grouping-and-stats): every trace of the project,
 * agents' runs first, filtered, grouped and totalled. Presentational: the container owns the
 * query, the filters and the open trace; this draws them and reports what the operator chose.
 */

const MICROS = 1_000_000
const GROUP_ROWS = 10

/** The Hub's own traces: behind a quieter choice than the agents' runs (operator, 2026-11-02). */
const HUB_KINDS: TraceKind[] = ['worker', 'request', 'work', 'event']
const RANGES: TimeRange[] = ['hour', 'day', 'week', 'month', 'all']
const GROUPINGS: TraceGrouping[] = ['none', 'agent', 'model', 'task', 'conversation', 'day']

function money(micros: number | null): string {
  if (micros === null) return '—'
  return micros > 0 && micros < 10_000 ? '<$0.01' : formatMoney(micros / MICROS)
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatCount(n)} ${n === 1 ? one : many}`
}

export interface TracesPageProps {
  filters: TraceFilters
  onFilters: (next: TraceFilters) => void
  grouping: TraceGrouping
  onGrouping: (next: TraceGrouping) => void
  /** Over everything the filters match, not the loaded page (FR-8). */
  totals: TraceTotals
  /** How many traces of each kind the other filters leave, for the Hub internals menu. */
  kindCounts: Partial<Record<TraceKind, number>>
  /** The loaded page, newest first, when ungrouped. */
  rows: TraceRow[]
  hasMore: boolean
  onMore: () => void
  /** When grouped: every group the filter matches, with its totals. */
  groups: TraceGroup[]
  agents: string[]
  colorIndexOf: (agent: string) => number | null | undefined
  onOpen: (row: TraceRow) => void
  now: Date
}

export function TracesPage(props: TracesPageProps) {
  const { filters, onFilters, grouping, onGrouping, totals, kindCounts, agents } = props
  const isRuns = filters.kind === 'run'
  const set = (patch: Partial<TraceFilters>) => onFilters({ ...filters, ...patch })
  const named = (['task', 'conversation', 'run'] as const).filter((k) => filters[k])
  const narrowed = Boolean(filters.agent || filters.range !== 'all' || named.length)

  return (
    <div className="aw-traces" data-testid="traces-page">
      <div className="aw-traces-filters" role="group" aria-label="Filters">
        <MenuSelect
          label="Agent"
          value={filters.agent ?? '__all'}
          onChange={(v) => set({ agent: v === '__all' ? null : v })}
          options={[
            { value: '__all', label: 'Every agent' },
            ...agents.map((a) => ({ value: a, label: a, icon: <span className="aw-agent-dot" style={{ background: agentColorVars(props.colorIndexOf(a)).accent }} /> })),
          ]}
        />
        <MenuSelect label="Time range" value={filters.range} onChange={(range) => set({ range })} options={RANGES.map((r) => ({ value: r, label: RANGE_LABELS[r] }))} />
        <span className="aw-traces-filters-gap" />
        <Menu>
          <MenuTrigger data-slot="traces-hub" className="aw-traces-hub" data-active={isRuns ? undefined : 'true'}>
            <Icon name="settings" size={12} />
            {isRuns ? 'Hub internals' : `Hub internals: ${KIND_LABELS[filters.kind]}`}
            <Icon name="expand_more" size={12} />
          </MenuTrigger>
          <MenuContent>
            <MenuLabel>What the Hub did itself</MenuLabel>
            {HUB_KINDS.map((k) => (
              <MenuItem key={k} icon={filters.kind === k ? 'check' : undefined} onSelect={() => set({ kind: k })}>
                {KIND_LABELS[k]}
                {kindCounts[k] !== undefined ? <span className="aw-traces-hub-count">{formatCount(kindCounts[k]!)}</span> : null}
              </MenuItem>
            ))}
            {isRuns ? null : (
              <>
                <MenuSeparator />
                <MenuItem icon="arrow_left" onSelect={() => set({ kind: 'run' })}>
                  Back to agent runs
                </MenuItem>
              </>
            )}
          </MenuContent>
        </Menu>
      </div>

      {named.length || narrowed ? (
        <div className="aw-traces-chips">
          {named.map((k) => (
            <button key={k} type="button" data-slot="traces-chip" className="aw-traces-chip" title="Remove this filter" onClick={() => set({ [k]: null })}>
              <span className="aw-traces-chip-kind">{k === 'task' ? 'Task' : k === 'conversation' ? 'Conversation' : 'Run'}</span>
              <span className="truncate">{filters[k]!.label}</span>
              <Icon name="close" size={12} />
            </button>
          ))}
          {narrowed ? (
            <button type="button" data-slot="traces-clear" className="aw-traces-clear" onClick={() => onFilters({ ...filters, agent: null, range: 'all', task: null, conversation: null, run: null })}>
              Clear filters
            </button>
          ) : null}
        </div>
      ) : null}

      <Headline totals={totals} isRuns={isRuns} />

      <div className="aw-traces-groupbar">
        <span className="aw-traces-groupbar-label">Group by</span>
        <Segmented
          label="Group by"
          size="xs"
          value={grouping}
          onChange={onGrouping}
          options={GROUPINGS.filter((g) => isRuns || g === 'none' || g === 'agent' || g === 'day').map((g) => ({ value: g, label: GROUPING_LABELS[g] }))}
        />
        <span className="aw-traces-groupbar-count">
          {totals.count.toLocaleString('en-US')} {isRuns ? (totals.count === 1 ? 'run' : 'runs') : totals.count === 1 ? 'trace' : 'traces'}
        </span>
      </div>

      {totals.count === 0 ? (
        <p className="aw-traces-empty">Nothing matches these filters.</p>
      ) : grouping === 'none' ? (
        <>
          <TraceTable {...props} rows={props.rows} isRuns={isRuns} />
          {props.hasMore ? (
            <button type="button" data-slot="traces-more" className="aw-traces-more" onClick={props.onMore}>
              Show more
            </button>
          ) : null}
        </>
      ) : (
        <div className="aw-traces-groups">
          <div className="aw-traces-group-head aw-traces-group-cols" aria-hidden="true">
            <span>{GROUPING_LABELS[grouping]}</span>
            <span>{isRuns ? 'Runs' : 'Traces'}</span>
            <span>Cost</span>
            <span>Took</span>
            <span>Errors</span>
            <span />
          </div>
          {props.groups.map((g) => (
            <Group key={g.key} group={g} total={totals} isRuns={isRuns} {...props} />
          ))}
        </div>
      )}
    </div>
  )
}

function Headline({ totals, isRuns }: { totals: TraceTotals; isRuns: boolean }) {
  const kinds = totals.error_kinds
  const errorParts = [
    kinds.failed ? `${kinds.failed} failed` : null,
    kinds.stopped ? `${kinds.stopped} stopped` : null,
    kinds.trace_error ? `${kinds.trace_error} ended in error` : null,
  ].filter(Boolean)
  return (
    <section className="aw-traces-stats" aria-label="Totals">
      <div className="aw-traces-tile" data-testid="traces-cost">
        <span className="aw-traces-tile-label">Cost</span>
        <strong>{isRuns ? money(totals.cost_micros) : '—'}</strong>
        <small>
          {!isRuns
            ? 'The Hub’s own work is not billed'
            : totals.unpriced
              ? `${plural(totals.unpriced, 'unpriced run')} left out`
              : 'Every run priced'}
        </small>
      </div>
      <div className="aw-traces-tile" data-testid="traces-duration">
        <span className="aw-traces-tile-label">Duration</span>
        <strong>{formatDuration(totals.duration_total)}</strong>
        <small>
          {totals.duration_avg === null ? 'Nothing has finished' : `${formatDuration(totals.duration_avg)} on average`}
          {totals.running ? ` · ${totals.running} still running` : ''}
        </small>
      </div>
      <div className="aw-traces-tile" data-testid="traces-errors" data-bad={totals.errors ? 'true' : undefined}>
        <span className="aw-traces-tile-label">Errors</span>
        <strong>{formatCount(totals.errors)}</strong>
        <small>{errorParts.length ? errorParts.join(' · ') : `None of ${plural(totals.count, isRuns ? 'run' : 'trace')}`}</small>
      </div>
      {isRuns ? (
        <div className="aw-traces-secondary" data-testid="traces-secondary">
          {totals.tokens ? (
            <span
              title={`${formatTokensExact(totals.tokens.input)} in (${formatTokensExact(totals.tokens.cache_read)} read from cache) · ${formatTokensExact(totals.tokens.output)} out`}
            >
              {formatTokens(totals.tokens.input + totals.tokens.output)}
            </span>
          ) : null}
          <span>{plural(totals.model_calls, 'model call')}</span>
          <span>{plural(totals.tool_calls, 'tool call')}</span>
          <span>{totals.wait_seconds ? `${formatDuration(totals.wait_seconds)} waiting on you` : 'No waiting on you'}</span>
        </div>
      ) : null}
    </section>
  )
}

function Group({
  group,
  total,
  isRuns,
  filters,
  onFilters,
  ...rest
}: TracesPageProps & { group: TraceGroup; total: TraceTotals; isRuns: boolean }) {
  const [open, setOpen] = React.useState(false)
  const [shown, setShown] = React.useState(GROUP_ROWS)
  const t = group.totals
  const share = isRuns && total.cost_micros && t.cost_micros !== null ? t.cost_micros / total.cost_micros : null
  const agentDot = rest.grouping === 'agent' && group.key ? agentColorVars(rest.colorIndexOf(group.key)).accent : null
  return (
    <section className="aw-traces-group" data-open={open ? 'true' : 'false'}>
      <div className="aw-traces-group-head">
        <button type="button" data-slot="traces-group" className="aw-traces-group-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Icon name={open ? 'expand_less' : 'expand_more'} size={14} />
          {agentDot ? <span className="aw-agent-dot" style={{ background: agentDot }} /> : null}
          <span className="aw-traces-group-name">
            <span className="truncate">{group.label}</span>
            {group.detail ? <small className="truncate">{group.detail}</small> : null}
          </span>
        </button>
        <span className="aw-traces-group-num" title="Runs">
          {formatCount(t.count)}
        </span>
        <span className="aw-traces-group-num aw-traces-group-cost">
          {isRuns ? (t.cost_micros === null ? <em>unpriced</em> : money(t.cost_micros)) : '—'}
          {isRuns && t.unpriced && t.cost_micros !== null ? <small>+{t.unpriced} unpriced</small> : null}
          {share !== null ? <span className="aw-traces-share" style={{ ['--share' as string]: `${Math.max(2, share * 100)}%` }} /> : null}
        </span>
        <span className="aw-traces-group-num">
          {formatDuration(t.duration_total)}
          <small>{t.duration_avg === null ? '' : `${formatDuration(t.duration_avg)} avg`}</small>
        </span>
        <span className="aw-traces-group-num" data-bad={t.errors ? 'true' : undefined}>
          {t.errors ? plural(t.errors, 'error') : '—'}
        </span>
        <span className="aw-traces-group-act">
          {group.narrow ? (
            <button type="button" data-slot="traces-narrow" className="aw-link aw-link-inline" onClick={() => onFilters({ ...filters, ...group.narrow })}>
              Only this
            </button>
          ) : null}
        </span>
      </div>
      {open ? (
        <>
          <TraceTable {...rest} rows={group.rows.slice(0, shown)} isRuns={isRuns} filters={filters} onFilters={onFilters} />
          {group.rows.length > shown ? (
            <button type="button" data-slot="traces-more" className="aw-traces-more" onClick={() => setShown((n) => n + 50)}>
              Show more of {formatCount(group.rows.length)}
            </button>
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function TraceTable({
  rows,
  isRuns,
  filters,
  onFilters,
  onOpen,
  colorIndexOf,
  now,
}: Pick<TracesPageProps, 'filters' | 'onFilters' | 'onOpen' | 'colorIndexOf' | 'now'> & { rows: TraceRow[]; isRuns: boolean }) {
  return (
    <table className="aw-traces-table">
      <thead>
        <tr>
          <th>Started</th>
          <th>Agent</th>
          {isRuns ? (
            <>
              <th>Model</th>
              <th>Task or conversation</th>
            </>
          ) : (
            <th>What</th>
          )}
          <th className="aw-traces-num">Took</th>
          {isRuns ? <th className="aw-traces-num">Cost</th> : null}
          <th>Outcome</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const d = durationSeconds(row)
          const err = errorLabel(row)
          return (
            <tr
              key={row.trace_id}
              tabIndex={0}
              data-error={err ? 'true' : undefined}
              title={row.status_message ?? undefined}
              onClick={() => onOpen(row)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onOpen(row)
              }}
            >
              <td className="aw-traces-when">{formatDateTime(row.start_time, now)}</td>
              <td>
                {row.agent ? (
                  <span className="aw-traces-agent">
                    <span className="aw-agent-dot" style={{ background: agentColorVars(colorIndexOf(row.agent)).accent }} />
                    {row.agent}
                  </span>
                ) : (
                  <span className="aw-traces-none">Hub</span>
                )}
              </td>
              {isRuns ? (
                <>
                  <td className="aw-traces-model">{modelLabel(row.model)}</td>
                  <td className="aw-traces-task">
                    {row.task_id ? (
                      <span className="aw-traces-subject" title={row.task_ref ? taskName(row).title : row.task_id ?? undefined} data-gone={row.task_ref ? undefined : 'true'}>
                        {row.task_ref ? <span className="aw-traces-ref">{row.task_ref}</span> : null}
                        <span className="truncate">{taskName(row).title}</span>
                        <NarrowButton
                          label={`Only runs on ${row.task_ref ?? 'this task'}`}
                          onClick={() => onFilters({ ...filters, task: { id: row.task_id!, label: taskName(row).ref ?? taskName(row).title } })}
                        />
                      </span>
                    ) : row.conversation_id ? (
                      <span className="aw-traces-subject" data-conversation="true" title="A conversation turn, no task">
                        <Icon name="chat" size={12} className="aw-traces-conv-icon" />
                        <span className="truncate">{row.conversation_title ?? 'Untitled conversation'}</span>
                        <NarrowButton
                          label="Only this conversation’s runs"
                          onClick={() => onFilters({ ...filters, conversation: { id: row.conversation_id!, label: row.conversation_title ?? 'conversation' } })}
                        />
                      </span>
                    ) : (
                      <span className="aw-traces-none">no task</span>
                    )}
                  </td>
                </>
              ) : (
                <td className="aw-traces-task">
                  <span className="truncate">{row.name}</span>
                </td>
              )}
              <td className="aw-traces-num">{d === null ? <em>running</em> : formatDuration(d)}</td>
              {isRuns ? (
                <td className="aw-traces-num">{d === null ? <em>—</em> : row.cost_usd_micros === null ? <em title="The Hub could not measure this run’s cost">unpriced</em> : money(row.cost_usd_micros)}</td>
              ) : null}
              <td className="aw-traces-outcome">
                {err ? (
                  <span className="aw-traces-err">
                    <Icon name="error_outline" size={12} />
                    {err}
                  </span>
                ) : d === null ? (
                  <span className="aw-traces-none">running</span>
                ) : (
                  <span className="aw-traces-ok">{isRuns ? row.run_status ?? 'ended' : 'ok'}</span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** Narrows the view to a row's task or conversation. Shown on the row's hover or focus, so a click
 *  anywhere else on the row opens its trace rather than filtering by accident. */
function NarrowButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      data-slot="traces-narrow-row"
      className="aw-traces-narrow-row"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <Icon name="filter_list" size={12} />
    </button>
  )
}
