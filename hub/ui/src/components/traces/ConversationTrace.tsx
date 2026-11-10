import * as React from 'react'
import type { TraceDetail, TraceTotals } from '@/api/traces'
import { Icon } from '@/components/common/Icon'
import { SpanDetail } from '@/components/traces/SpanDetail'
import {
  buildAxis,
  buildTimeline,
  conversationTotals,
  keepLabels,
  selectRuns,
  withRouteTotals,
  type ConversationRun,
  type RunSelection,
} from '@/components/traces/conversationTraceModel'
import { formatDuration, operationLabel, spanHint, spanToken } from '@/components/traces/traceModel'
import { formatCount, formatDateTime, formatMoney } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'
import { tint } from '@/lib/colorTint'
import '@/styles/conversation-trace.css'

type NumberedRun = ConversationRun & { turn: number }

/** The select's values are the drive's; the selection's own are `all`, `24h`, `6h`, `1h`. */
const SINCE_OPTIONS = [
  { value: 'all', option: 'any', label: 'Any time' },
  { value: '24h', option: '24h', label: 'Last 24 h' },
  { value: '6h', option: '6h', label: 'Last 6 h' },
  { value: '1h', option: '1h', label: 'Last hour' },
] as const

const INDENT_PX = 14

function plural(n: number, word: string): string {
  return `${formatCount(n)} ${word}${n === 1 ? '' : 's'}`
}

function hhmm(tMs: number): string {
  const d = new Date(tMs)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** A turn the operator started says so; the rest were started by a message, a hand-off or a schedule. */
function initiatorLabel(initiator: string | null | undefined): string | null {
  return initiator === 'operator' ? 'you' : null
}

/**
 * A whole conversation's trace: every run on one timeline, long idle gaps folded into marked
 * breaks, a run's spans shown when its turn is unfolded, and the selected span's detail below.
 * Presentational: the caller owns the runs, their traces and the selection.
 */
export function ConversationTrace({
  conversationId,
  title,
  agent,
  runs,
  details,
  selection,
  onSelection,
  continuedFrom,
  onOpenContinued,
  onUnfold,
  totals: routeTotals,
  now,
}: {
  conversationId?: string
  title: string
  agent: string
  /** Every run of the conversation, numbered in start order. */
  runs: NumberedRun[]
  /** Each run's trace, by run id; a run whose trace is not loaded yet shows its row only. */
  details: Record<string, TraceDetail | null | undefined>
  selection: RunSelection
  onSelection: (next: RunSelection) => void
  /** The conversation this one was carried over from, when it was. */
  continuedFrom?: { id?: string; title: string } | null
  onOpenContinued?: () => void
  /** A turn was unfolded for the first time: the caller reads its spans now. */
  onUnfold?: (runId: string) => void
  /** The Hub's totals over the turns shown: `undefined` takes them from the turn rows, `null`
   *  while they are being read. The list's rows carry no call or wait counts, so only the Hub's
   *  totals can say them. */
  totals?: TraceTotals | null
  now: Date
}) {
  const nowMs = now.getTime()
  const shown = React.useMemo(() => selectRuns(runs, selection, nowMs), [runs, selection, nowMs])
  const axis = React.useMemo(() => buildAxis(shown, nowMs), [shown, nowMs])
  const [unfolded, setUnfolded] = React.useState<Set<string>>(() => new Set())
  const rows = React.useMemo(() => buildTimeline(shown, details, unfolded, axis, nowMs), [shown, details, unfolded, axis, nowMs])
  const groups = React.useMemo(() => {
    const out: Array<{ run: NumberedRun; rows: typeof rows }> = []
    for (const r of rows) {
      const last = out[out.length - 1]
      if (last && last.run.run_id === r.run.run_id) last.rows.push(r)
      else out.push({ run: r.run, rows: [r] })
    }
    return out
  }, [rows])
  const totals = React.useMemo(() => conversationTotals(shown, nowMs), [shown, nowMs])
  const stats = React.useMemo(() => withRouteTotals(totals, routeTotals), [totals, routeTotals])
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const selected = rows.find((r) => r.row.span.span_id === selectedId) ?? rows[0]

  // Labels print only where they fit (about one per 11% of the track); the rest are in titles.
  const tickShown = React.useMemo(() => keepLabels(axis.segments.filter((g) => g.kind === 'time').map((g) => g.x0), 0.11), [axis])
  const breakShown = React.useMemo(() => keepLabels(axis.segments.filter((g) => g.kind === 'break').map((g) => (g.x0 + g.x1) / 2), 0.11), [axis])
  // A printed time names its day too, the first time and whenever the day changed since the last printed one.
  const tickLabels = React.useMemo(() => {
    let lastDay = ''
    let t = 0
    return axis.segments.map((seg) => {
      if (seg.kind !== 'time' || !tickShown[t++]) return ''
      const day = new Date(seg.startMs).toDateString()
      const label = day !== lastDay ? formatDateTime(new Date(seg.startMs), now) : hhmm(seg.startMs)
      lastDay = day
      return label
    })
  }, [axis, now, tickShown])

  const toggle = (runId: string) =>
    setUnfolded((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) next.delete(runId)
      else {
        next.add(runId)
        onUnfold?.(runId)
      }
      return next
    })

  const turnOptions = runs.map((r) => ({
    value: String(r.turn),
    label: `Turn ${r.turn}`,
    detail: formatDateTime(r.start_time, now),
  }))
  const allTurns = selection.from === 1 && selection.to === runs.length && selection.since === 'all'

  return (
    <div className="aw-ctrace" data-testid="conversation-trace" data-conversation-id={conversationId}>
      <header className="aw-ctrace-head">
        <div className="aw-ctrace-title">
          <strong>{title}</strong>
          <span>{agent}</span>
        </div>
        {continuedFrom ? (
          <button type="button" data-slot="ctrace-continued" data-testid="conversation-trace-continued" data-conversation-id={continuedFrom.id} className="aw-ctrace-continued" onClick={onOpenContinued}>
            <Icon name="move_up" size={12} />
            Continued from “{continuedFrom.title}” · open its trace
          </button>
        ) : null}
      </header>

      <div className="aw-ctrace-controls">
        <span className="aw-ctrace-label">Turns</span>
        <select
          aria-label="First turn shown"
          data-testid="conversation-trace-from"
          className="control-field"
          value={String(selection.from)}
          onChange={(e) => onSelection({ ...selection, from: Number(e.target.value), to: Math.max(Number(e.target.value), selection.to) })}
        >
          {turnOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label} · {o.detail}</option>
          ))}
        </select>
        <span className="aw-ctrace-label">to</span>
        <select
          aria-label="Last turn shown"
          data-testid="conversation-trace-to"
          className="control-field"
          value={String(selection.to)}
          onChange={(e) => onSelection({ ...selection, to: Number(e.target.value), from: Math.min(Number(e.target.value), selection.from) })}
        >
          {turnOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label} · {o.detail}</option>
          ))}
        </select>
        <span className="aw-ctrace-label">started</span>
        <select
          aria-label="Started"
          data-testid="conversation-trace-since"
          className="control-field"
          value={SINCE_OPTIONS.find((o) => o.value === selection.since)?.option ?? 'any'}
          onChange={(e) => onSelection({ ...selection, since: SINCE_OPTIONS.find((o) => o.option === e.target.value)?.value ?? 'all' })}
        >
          {SINCE_OPTIONS.map((o) => (
            <option key={o.option} value={o.option}>{o.label}</option>
          ))}
        </select>
        {!allTurns ? (
          <button
            type="button"
            data-slot="ctrace-reset"
            data-testid="conversation-trace-show-all"
            className="aw-link aw-link-inline"
            onClick={() => onSelection({ from: 1, to: runs.length, since: 'all' })}
          >
            Show every turn
          </button>
        ) : null}
      </div>

      <section
        className="aw-ctrace-stats"
        aria-label="Totals"
        data-testid="conversation-totals"
        data-turns={shown.length}
        data-of={runs.length}
        data-working-seconds={Math.round(stats.workingMs / 1000)}
        data-cost-usd-micros={stats.priced ? stats.costUsdMicros : ''}
        data-unpriced={stats.unpriced}
        data-failed={stats.failedRuns}
        data-model-calls={stats.modelCalls ?? ''}
        data-tool-calls={stats.toolCalls ?? ''}
        data-tool-errors={stats.toolErrors}
      >
        <div>
          <span>Turns</span>
          <strong>{shown.length === runs.length ? formatCount(runs.length) : `${formatCount(shown.length)} of ${formatCount(runs.length)}`}</strong>
        </div>
        <div>
          <span>Working</span>
          <strong>{formatDuration(stats.workingMs)}</strong>
          <small>over {formatDuration(stats.elapsedMs)}</small>
        </div>
        <div>
          <span>Cost</span>
          <strong>{stats.priced ? formatMoney(stats.costUsdMicros / 1_000_000) : '—'}</strong>
          <small>{stats.unpriced ? `${plural(stats.unpriced, 'unpriced turn')} left out` : 'Every turn priced'}</small>
        </div>
        <div data-bad={stats.failedRuns || stats.toolErrors ? 'true' : undefined}>
          <span>Errors</span>
          <strong>{formatCount(stats.failedRuns + stats.toolErrors)}</strong>
          <small>
            {stats.failedRuns || stats.toolErrors
              ? [stats.failedRuns ? plural(stats.failedRuns, 'failed turn') : null, stats.toolErrors ? plural(stats.toolErrors, 'tool error') : null].filter(Boolean).join(' · ')
              : 'None'}
          </small>
        </div>
        <p className="aw-ctrace-secondary">
          <span>{stats.modelCalls === null ? 'Model calls …' : plural(stats.modelCalls, 'model call')}</span>
          <span>{stats.toolCalls === null ? 'Tool calls …' : plural(stats.toolCalls, 'tool call')}</span>
          <span>
            {stats.waitSeconds === null ? 'Waiting on you …' : stats.waitSeconds ? `${formatDuration(stats.waitSeconds * 1000)} waiting on you` : 'No waiting on you'}
          </span>
        </p>
      </section>

      {shown.length === 0 ? (
        <p className="aw-ctrace-empty" data-testid="conversation-trace-empty">No turn of this conversation matches. Widen the turns or the start time.</p>
      ) : (
        <div className="aw-ctrace-body">
          <div className="aw-ctrace-timeline" data-testid="ctrace-timeline">
            <div className="aw-ctrace-row aw-ctrace-axis" aria-hidden="true">
              <span />
              <div className="aw-ctrace-track">
                {(() => {
                  let t = 0
                  let b = 0
                  return axis.segments.map((seg, i) => {
                    const gap = formatDuration(seg.endMs - seg.startMs)
                    if (seg.kind === 'break') {
                      const show = breakShown[b++]
                      return (
                        <span
                          key={i}
                          className="aw-ctrace-break-label"
                          data-testid="conversation-break"
                          data-label={`${gap} later`}
                          data-quiet={show ? undefined : 'true'}
                          style={{ left: `${((seg.x0 + seg.x1) / 2) * 100}%` }}
                          title={`${gap} with no turn running, folded`}
                        >
                          {show ? `${gap} later` : null}
                        </span>
                      )
                    }
                    const show = tickShown[t++]
                    return (
                      <span key={i} className="aw-ctrace-tick" data-quiet={show ? undefined : 'true'} style={{ left: `${seg.x0 * 100}%` }} title={formatDateTime(new Date(seg.startMs), now)}>
                        {show ? tickLabels[i] : null}
                      </span>
                    )
                  })
                })()}
              </div>
              <span className="aw-ctrace-dur">Duration</span>
            </div>
            {groups.map((group) => (
              <div key={group.run.run_id} data-testid="conversation-turn" data-run-id={group.run.run_id} data-number={group.run.turn} style={{ display: 'contents' }}>
            {group.rows.map((r) => {
              const isRun = r.kind === 'run'
              const token = isRun ? (r.run.status === 'error' ? 'var(--red)' : 'var(--purple)') : spanToken(r.row.span)
              const left = Math.min(r.x0 * 100, 99.6)
              const width = Math.max((r.x1 - r.x0) * 100, 0.35)
              const hint = isRun ? null : spanHint(r.row.span)
              const who = isRun ? initiatorLabel(r.run.initiator) : null
              const open = unfolded.has(r.run.run_id)
              const isSelected = selected?.row.span.span_id === r.row.span.span_id
              return (
                <React.Fragment key={`${r.run.run_id}:${r.row.span.span_id}`}>
                <div
                  className="aw-ctrace-row"
                  data-kind={r.kind}
                  data-testid={isRun ? undefined : 'conversation-span'}
                  data-span-id={isRun ? undefined : r.row.span.span_id}
                  data-left={isRun ? undefined : r.x0}
                  data-selected={isSelected ? 'true' : undefined}
                  data-status={r.row.span.status}
                >
                  <span className="aw-ctrace-name" style={{ paddingLeft: isRun ? 0 : r.row.depth * INDENT_PX }}>
                    {isRun ? (
                      <button
                        type="button"
                        data-slot="ctrace-fold"
                        data-testid="conversation-turn-toggle"
                        className="aw-ctrace-fold"
                        aria-expanded={open}
                        aria-label={open ? `Fold turn ${r.run.turn}` : `Unfold turn ${r.run.turn}`}
                        onClick={() => toggle(r.run.run_id)}
                      >
                        <Icon name={open ? 'expand_more' : 'chevron_right'} size={14} />
                      </button>
                    ) : (
                      <span className="aw-ctrace-dot" style={{ background: token }} aria-hidden="true" />
                    )}
                    <button
                      type="button"
                      data-slot="ctrace-select"
                      className="aw-ctrace-select"
                      aria-pressed={isSelected}
                      onClick={() => setSelectedId(r.row.span.span_id)}
                    >
                      {isRun ? (
                        <>
                          <strong>Turn {r.run.turn}</strong>
                          <small>
                            {hhmm(hubDate(r.run.start_time).getTime())}
                            {who ? <span data-testid="conversation-turn-from-you">{` · from ${who}`}</span> : null}
                            {r.run.cost_usd_micros != null ? ` · ${formatMoney(r.run.cost_usd_micros / 1_000_000)}` : ''}
                          </small>
                        </>
                      ) : (
                        <>
                          <span className="aw-ctrace-span-name" title={r.row.span.name}>{r.row.span.name}</span>
                          <small>{operationLabel(r.row.span.operation)}</small>
                          {hint ? <small className="aw-ctrace-hint" title={hint}>· {hint}</small> : null}
                        </>
                      )}
                    </button>
                  </span>
                  <div className="aw-ctrace-track" data-zoomed={r.zoomed ? 'true' : undefined} onClick={() => setSelectedId(r.row.span.span_id)}>
                    {!r.zoomed && axis.segments
                      .filter((s) => s.kind === 'break')
                      .map((s, i) => (
                        <span key={i} className="aw-ctrace-break" style={{ left: `${s.x0 * 100}%`, width: `${(s.x1 - s.x0) * 100}%` }} />
                      ))}
                    <span
                      className="aw-ctrace-bar"
                      data-testid={isRun ? 'conversation-turn-bar' : undefined}
                      data-left={left / 100}
                      data-width={Math.min(width, 100 - left) / 100}
                      data-open={r.row.open ? 'true' : undefined}
                      style={{
                        left: `${left}%`,
                        width: `${Math.min(width, 100 - left)}%`,
                        background: r.row.open ? tint(token, 45) : isRun ? tint(token, 70) : token,
                        border: r.row.open ? `1px dashed ${token}` : isRun ? `1px solid ${token}` : undefined,
                      }}
                    />
                  </div>
                  <span className="aw-ctrace-dur" data-bad={r.row.span.status === 'error' ? 'true' : undefined}>
                    {formatDuration(r.row.durationMs)}
                    {r.row.open ? '…' : ''}
                  </span>
                </div>
                {isRun && open ? (
                  <p className="aw-ctrace-zoom-note" data-testid="conversation-turn-scale-note">Turn {r.run.turn}’s spans, drawn across its own {formatDuration(r.row.durationMs)}</p>
                ) : null}
                {isRun && open && details[r.run.run_id] === null ? (
                  <p className="aw-ctrace-zoom-note" data-testid="conversation-turn-no-trace">Turn {r.run.turn} has no trace: it was cleared or never recorded.</p>
                ) : isRun && open && details[r.run.run_id] === undefined ? (
                  <p className="aw-ctrace-zoom-note">Reading turn {r.run.turn}’s spans…</p>
                ) : null}
                </React.Fragment>
              )
            })}
              </div>
            ))}
          </div>
          {selected ? (
            <div className="aw-ctrace-detail" data-testid="conversation-detail">
              <p className="aw-ctrace-detail-of">
                Turn {selected.run.turn}
                {selected.kind === 'span' ? ` · ${selected.row.span.name}` : ''}
              </p>
              <SpanDetail span={selected.row.span} nowMs={nowMs} />
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
