import * as React from 'react'
import type { TraceDetail } from '@/api/traces'
import { Icon } from '@/components/common/Icon'
import { MenuSelect } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { SpanDetail } from '@/components/traces/SpanDetail'
import {
  buildAxis,
  buildTimeline,
  conversationTotals,
  keepLabels,
  selectRuns,
  type ConversationRun,
  type RunSelection,
} from '@/components/traces/conversationTraceModel'
import { formatDuration, operationLabel, spanHint, spanToken } from '@/components/traces/traceModel'
import { formatCount, formatDateTime, formatMoney } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'
import { tint } from '@/lib/colorTint'
import '@/styles/conversation-trace.css'

type NumberedRun = ConversationRun & { turn: number }

const SINCE_OPTIONS = [
  { value: 'all', label: 'Any time' },
  { value: '24h', label: 'Last 24 h' },
  { value: '6h', label: 'Last 6 h' },
  { value: '1h', label: 'Last hour' },
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
  title,
  agent,
  runs,
  details,
  selection,
  onSelection,
  continuedFrom,
  onOpenContinued,
  now,
}: {
  title: string
  agent: string
  /** Every run of the conversation, numbered in start order. */
  runs: NumberedRun[]
  /** Each run's trace, by run id; a run whose trace is not loaded yet shows its row only. */
  details: Record<string, TraceDetail | undefined>
  selection: RunSelection
  onSelection: (next: RunSelection) => void
  /** The conversation this one was carried over from, when it was. */
  continuedFrom?: { title: string } | null
  onOpenContinued?: () => void
  now: Date
}) {
  const nowMs = now.getTime()
  const shown = React.useMemo(() => selectRuns(runs, selection, nowMs), [runs, selection, nowMs])
  const axis = React.useMemo(() => buildAxis(shown, nowMs), [shown, nowMs])
  const [unfolded, setUnfolded] = React.useState<Set<string>>(() => new Set())
  const rows = React.useMemo(() => buildTimeline(shown, details, unfolded, axis, nowMs), [shown, details, unfolded, axis, nowMs])
  const totals = React.useMemo(() => conversationTotals(shown, nowMs), [shown, nowMs])
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
      else next.add(runId)
      return next
    })

  const turnOptions = runs.map((r) => ({
    value: String(r.turn),
    label: `Turn ${r.turn}`,
    detail: formatDateTime(r.start_time, now),
  }))
  const allTurns = selection.from === 1 && selection.to === runs.length && selection.since === 'all'

  return (
    <div className="aw-ctrace" data-testid="conversation-trace">
      <header className="aw-ctrace-head">
        <div className="aw-ctrace-title">
          <strong>{title}</strong>
          <span>{agent}</span>
        </div>
        {continuedFrom ? (
          <button type="button" data-slot="ctrace-continued" className="aw-ctrace-continued" onClick={onOpenContinued}>
            <Icon name="move_up" size={12} />
            Continued from “{continuedFrom.title}” · open its trace
          </button>
        ) : null}
      </header>

      <div className="aw-ctrace-controls">
        <span className="aw-ctrace-label">Turns</span>
        <MenuSelect
          label="First turn shown"
          value={String(selection.from)}
          onChange={(v) => onSelection({ ...selection, from: Number(v), to: Math.max(Number(v), selection.to) })}
          options={turnOptions}
          testId="ctrace-from"
        />
        <span className="aw-ctrace-label">to</span>
        <MenuSelect
          label="Last turn shown"
          value={String(selection.to)}
          onChange={(v) => onSelection({ ...selection, to: Number(v), from: Math.min(Number(v), selection.from) })}
          options={turnOptions}
          testId="ctrace-to"
        />
        <span className="aw-ctrace-label">started</span>
        <Segmented
          label="Started"
          size="xs"
          value={selection.since}
          onChange={(since) => onSelection({ ...selection, since })}
          options={SINCE_OPTIONS}
        />
        {!allTurns ? (
          <button
            type="button"
            data-slot="ctrace-reset"
            className="aw-link aw-link-inline"
            onClick={() => onSelection({ from: 1, to: runs.length, since: 'all' })}
          >
            Show every turn
          </button>
        ) : null}
      </div>

      <section className="aw-ctrace-stats" aria-label="Totals" data-testid="ctrace-totals">
        <div>
          <span>Turns</span>
          <strong>{shown.length === runs.length ? formatCount(runs.length) : `${formatCount(shown.length)} of ${formatCount(runs.length)}`}</strong>
        </div>
        <div>
          <span>Working</span>
          <strong>{formatDuration(totals.workingMs)}</strong>
          <small>over {formatDuration(totals.elapsedMs)}</small>
        </div>
        <div>
          <span>Cost</span>
          <strong>{totals.runs - totals.unpriced ? formatMoney(totals.costUsdMicros / 1_000_000) : '—'}</strong>
          <small>{totals.unpriced ? `${plural(totals.unpriced, 'unpriced turn')} left out` : 'Every turn priced'}</small>
        </div>
        <div data-bad={totals.failedRuns || totals.toolErrors ? 'true' : undefined}>
          <span>Errors</span>
          <strong>{formatCount(totals.failedRuns + totals.toolErrors)}</strong>
          <small>
            {totals.failedRuns || totals.toolErrors
              ? [totals.failedRuns ? plural(totals.failedRuns, 'failed turn') : null, totals.toolErrors ? plural(totals.toolErrors, 'tool error') : null].filter(Boolean).join(' · ')
              : 'None'}
          </small>
        </div>
        <p className="aw-ctrace-secondary">
          <span>{plural(totals.modelCalls, 'model call')}</span>
          <span>{plural(totals.toolCalls, 'tool call')}</span>
          <span>{totals.waitSeconds ? `${formatDuration(totals.waitSeconds * 1000)} waiting on you` : 'No waiting on you'}</span>
        </p>
      </section>

      {shown.length === 0 ? (
        <p className="aw-ctrace-empty">No turn of this conversation matches. Widen the turns or the start time.</p>
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
                      return show ? (
                        <span key={i} className="aw-ctrace-break-label" style={{ left: `${((seg.x0 + seg.x1) / 2) * 100}%` }} title={`${gap} with no turn running, folded`}>
                          {gap} later
                        </span>
                      ) : null
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
            {rows.map((r) => {
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
                  data-selected={isSelected ? 'true' : undefined}
                  data-status={r.row.span.status}
                >
                  <span className="aw-ctrace-name" style={{ paddingLeft: isRun ? 0 : r.row.depth * INDENT_PX }}>
                    {isRun ? (
                      <button
                        type="button"
                        data-slot="ctrace-fold"
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
                            {who ? ` · from ${who}` : ''}
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
                  <p className="aw-ctrace-zoom-note">Turn {r.run.turn}’s spans, drawn across its own {formatDuration(r.row.durationMs)}</p>
                ) : null}
                </React.Fragment>
              )
            })}
          </div>
          {selected ? (
            <div className="aw-ctrace-detail">
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
