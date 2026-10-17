import { useState, type CSSProperties, type ReactNode } from 'react'
import { StatePill } from '@/components/common/StatePill'
import { Expander } from '@/components/common/Expander'
import { useProjectLedger, type ProjectLedger as Ledger } from '@/api/ledger'
import { hubDate } from '@/lib/hubTime'
import { ApiError } from '@/api/client'
import { ActivityLog } from './ActivityLog'

/**
 * The project's ledger (slice project-ledger): what merged into main, what was spent and on what,
 * which runs diverged from their task, what agents told each other, where the work came from, and
 * the notices the live log would otherwise repeat line by line. Every lane renders in the order
 * `GET /ledger` returns it.
 */

const NOTICE_LABEL: Record<string, string> = { context_warning: 'Context warnings' }
const LANE_PREVIEW = 8

function money(value: number): string {
  if (value > 0 && value < 0.01) return '<$0.01'
  return `$${value.toFixed(2)}`
}

function tokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M tokens`
  if (value >= 1_000) return `${Math.round(value / 1_000)}k tokens`
  return `${value} tokens`
}

function relative(value: string | null): { label: string; exact: string } | null {
  if (!value) return null
  const date = hubDate(value)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  let label: string
  if (seconds < 45) label = 'just now'
  else if (seconds < 3600) label = `${Math.round(seconds / 60)}m ago`
  else if (seconds < 86400) label = `${Math.round(seconds / 3600)}h ago`
  else label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return { label, exact: date.toLocaleString() }
}

function Time({ value }: { value: string | null }) {
  const at = relative(value)
  return at ? <time title={at.exact}>{at.label}</time> : null
}

function dayLabel(day: string): string {
  // A UTC calendar day from the Hub; noon keeps it on the same date in every nearby time zone.
  const date = hubDate(`${day}T12:00:00Z`)
  return Number.isNaN(date.getTime()) ? day : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** Spend by day: one series, so no legend; each bar names its day and amount on hover. */
function SpendByDay({ days }: { days: Ledger['spend']['by_day'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(...days.map((d) => d.usd), 0)
  if (days.length === 0 || max === 0) return <p className="aw-tl-meta">Nothing was spent yet.</p>
  const shown = hover != null ? days[hover] : null
  return (
    <figure className="aw-ledger-chart" data-testid="ledger-spend-by-day">
      <div className="aw-ledger-chart-head">
        <span className="aw-tl-meta">{money(max)}</span>
        {shown ? (
          <span className="aw-ledger-chart-readout" role="status">
            {dayLabel(shown.day)} · <strong>{money(shown.usd)}</strong> · {tokens(shown.tokens)}
            {shown.worker_usd ? ` · ${money(shown.worker_usd)} by the Hub` : ''}
          </span>
        ) : null}
      </div>
      <div className="aw-ledger-bars" onMouseLeave={() => setHover(null)}>
        {days.map((day, index) => (
          <button
            key={day.day}
            type="button"
            className="aw-ledger-bar"
            data-active={hover === index ? 'true' : undefined}
            style={{ '--h': `${Math.max(2, (day.usd / max) * 100)}%`, '--i': index } as CSSProperties}
            onMouseEnter={() => setHover(index)}
            onFocus={() => setHover(index)}
            onBlur={() => setHover(null)}
            aria-label={`${dayLabel(day.day)}: ${money(day.usd)}`}
          >
            <span />
          </button>
        ))}
      </div>
      <div className="aw-ledger-axis aw-tl-meta">
        <span>{dayLabel(days[0].day)}</span>
        {days.length > 1 ? <span>{dayLabel(days[days.length - 1].day)}</span> : null}
      </div>
    </figure>
  )
}

/** A ranked magnitude: horizontal bars in one hue, the value in text ink beside each. */
function Ranked({
  rows,
  testId,
  onOpen,
}: {
  rows: Array<{ key: string; label: string; usd: number; detail: string }>
  testId: string
  onOpen?: (key: string) => void
}) {
  const [all, setAll] = useState(false)
  const max = Math.max(...rows.map((r) => r.usd), 0)
  if (rows.length === 0) return <p className="aw-tl-meta">None yet.</p>
  return (
    <div className="grid gap-1" data-testid={testId}>
      {(all ? rows : rows.slice(0, LANE_PREVIEW)).map((row, index) => (
        <div key={row.key} className="aw-ledger-rank" style={{ '--i': index } as CSSProperties} title={row.detail}>
          {onOpen ? (
            <button type="button" className="aw-inline-link aw-ledger-rank-label" onClick={() => onOpen(row.key)}>
              {row.label}
            </button>
          ) : (
            <span className="aw-ledger-rank-label">{row.label}</span>
          )}
          <span className="aw-ledger-rank-track">
            <span style={{ width: `${max ? Math.max(1.5, (row.usd / max) * 100) : 0}%` }} />
          </span>
          <span className="aw-ledger-rank-value">{money(row.usd)}</span>
        </div>
      ))}
      {rows.length > LANE_PREVIEW ? (
        <button type="button" className="aw-link" onClick={() => setAll((v) => !v)}>
          {all ? 'Show fewer' : `Show all ${rows.length}`}
        </button>
      ) : null}
    </div>
  )
}

function Lane<T>({
  title,
  rows,
  empty,
  testId,
  render,
}: {
  title: string
  rows: T[]
  empty: string
  testId: string
  render: (row: T) => ReactNode
}) {
  const [all, setAll] = useState(false)
  return (
    <section className="aw-req-section" data-testid={testId}>
      <h2 className="aw-req-heading">
        {title}
        <span className="aw-tl-meta" style={{ textTransform: 'none', letterSpacing: 0 }}>
          {rows.length}
        </span>
      </h2>
      {rows.length === 0 ? (
        <p className="aw-tl-meta">{empty}</p>
      ) : (
        <>
          <ul className="aw-req-list">{rows.slice(0, LANE_PREVIEW).map(render)}</ul>
          {rows.length > LANE_PREVIEW ? (
            <>
              <Expander open={all}>
                <ul className="aw-req-list" style={{ marginTop: 6 }}>
                  {rows.slice(LANE_PREVIEW).map(render)}
                </ul>
              </Expander>
              <button type="button" className="aw-link" onClick={() => setAll((v) => !v)}>
                {all ? 'Show fewer' : `Show all ${rows.length}`}
              </button>
            </>
          ) : null}
        </>
      )}
    </section>
  )
}

export function ProjectLedger({ onOpenTask }: { onOpenTask: (taskId: string) => void }) {
  const { data, isLoading, isError, error } = useProjectLedger()

  // A Hub that predates the ledger answers 404 (the committed bundle reaches a running Hub before
  // it restarts): the tab still opens on something useful, the live log, and says why.
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="flex h-full flex-col" data-testid="ledger-unavailable">
        <p className="px-4 pt-3 text-[12px]" style={{ color: 'var(--text-3)' }}>
          This Hub predates the ledger; it appears once the Hub restarts. Live activity meanwhile.
        </p>
        <div className="min-h-0 flex-1">
          <ActivityLog />
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="aw-evidence-page" aria-label="Loading the ledger">
        {[70, 90, 55].map((width, index) => (
          <div key={index} className="aw-skeleton" style={{ width: `${width}%`, height: 14 }} />
        ))}
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="aw-evidence-page">
        <p className="aw-callout tone-red" data-testid="ledger-error">
          The Hub did not answer for this project’s ledger. A Hub older than this view has no ledger
          to give; otherwise try again in a moment.
        </p>
      </div>
    )
  }

  const { spend, totals, origins } = data
  const skipped = totals.integrations - totals.merged
  const originParts = (
    [
      ['spec', 'from specs'],
      ['loop', 'from loops'],
      ['agent', 'by agents'],
      ['operator', 'by you'],
    ] as const
  )
    .filter(([key]) => origins[key] > 0)
    .map(([key, label]) => `${origins[key]} ${label}`)

  return (
    <div className="aw-evidence-page" data-testid="project-ledger">
      <header className="grid gap-1">
        <h1 className="text-[18px] font-semibold" style={{ color: 'var(--text)' }}>
          Ledger
        </h1>
        <p className="text-[12.5px]" style={{ color: 'var(--text-2)' }}>
          What this project merged, spent and decided, from what the Hub recorded.
        </p>
      </header>

      <div className="aw-story-summary" data-testid="ledger-totals">
        <div>
          <span className="aw-story-label">Spent</span>
          <span className="aw-story-value" data-testid="ledger-total-spend">{money(spend.total_usd)}</span>
          <small className="aw-tl-meta">
            {tokens(spend.total_tokens)}
            {spend.worker_usd ? ` · ${money(spend.worker_usd)} by the Hub` : ''}
          </small>
        </div>
        <div>
          <span className="aw-story-label">Merged into main</span>
          <span className="aw-story-value" data-testid="ledger-total-merged">{totals.merged}</span>
          <small className="aw-tl-meta">{skipped ? `${skipped} skipped` : 'none skipped'}</small>
        </div>
        <div>
          <span className="aw-story-label">Divergences</span>
          <span className="aw-story-value" data-testid="ledger-total-divergences">{totals.divergences}</span>
          <small className="aw-tl-meta">
            {totals.open_divergences ? `${totals.open_divergences} open` : totals.divergences ? 'all resolved' : 'none'}
          </small>
        </div>
        <div>
          <span className="aw-story-label">Tasks</span>
          <span className="aw-story-value">{totals.tasks}</span>
          <small className="aw-tl-meta">{originParts.join(' · ') || 'none yet'}</small>
        </div>
      </div>

      <section className="aw-req-section">
        <h2 className="aw-req-heading">Spend by day</h2>
        <SpendByDay days={spend.by_day} />
      </section>

      <div className="aw-ledger-columns">
        <section className="aw-req-section">
          <h2 className="aw-req-heading">By agent</h2>
          <Ranked
            testId="ledger-spend-by-agent"
            rows={spend.by_agent.map((a) => ({
              key: a.agent,
              label: a.agent,
              usd: a.usd,
              detail: `${a.turns} turns · ${tokens(a.tokens)}`,
            }))}
          />
        </section>
        <section className="aw-req-section">
          <h2 className="aw-req-heading">By task</h2>
          <Ranked
            testId="ledger-spend-by-task"
            onOpen={onOpenTask}
            rows={spend.by_task.map((t) => ({
              key: t.task_id,
              label: t.task_title ?? t.task_id,
              usd: t.usd,
              detail: `${t.turns} turns · ${tokens(t.tokens)}`,
            }))}
          />
        </section>
      </div>

      <Lane
        title="Into main"
        testId="ledger-merges"
        rows={data.merges}
        empty="Nothing has merged yet."
        render={(merge) => (
          <li key={merge.id} data-testid={`ledger-merge-${merge.id}`}>
            <StatePill tone={merge.outcome === 'merged' ? 'green' : merge.outcome === 'failed' ? 'red' : 'neutral'}>
              {merge.outcome}
            </StatePill>
            <button type="button" className="aw-inline-link aw-req-line" onClick={() => onOpenTask(merge.task_id)}>
              {merge.task_title ?? merge.task_id}
            </button>
            <span className="aw-tl-meta aw-ledger-meta" title={merge.reason || undefined}>
              {merge.commit_sha ? <code>{merge.commit_sha.slice(0, 8)}</code> : merge.reason?.slice(0, 40)}
              {merge.target_branch ? ` → ${merge.target_branch}` : ''} · <Time value={merge.at} />
            </span>
          </li>
        )}
      />

      <Lane
        title="Divergences"
        testId="ledger-divergences"
        rows={data.divergences}
        empty="No run ended out of step with its task."
        render={(row) => (
          <li key={row.id}>
            <StatePill tone={row.resolved_at ? 'neutral' : 'amber'}>{row.resolved_at ? 'resolved' : 'open'}</StatePill>
            <span className="aw-req-line">
              <strong>{row.agent}</strong> ended {row.run_exit_status ?? 'a run'} with{' '}
              {row.task_id ? (
                <button type="button" className="aw-inline-link" onClick={() => onOpenTask(row.task_id as string)}>
                  {row.task_title ?? row.task_id}
                </button>
              ) : (
                'its task'
              )}{' '}
              still {row.task_status_at_end?.replace(/_/g, ' ') ?? 'open'}
            </span>
            <span className="aw-tl-meta aw-ledger-meta">
              {row.outcome?.replace(/_/g, ' ')} · <Time value={row.at} />
            </span>
          </li>
        )}
      />

      <Lane
        title="Between agents"
        testId="ledger-messages"
        rows={data.messages}
        empty="Agents have not messaged each other."
        render={(message) => (
          <li key={message.id}>
            <span className="aw-ledger-meta">
              <strong>{message.sender}</strong> → <strong>{message.recipient}</strong>
            </span>
            <span className="aw-req-line" title={message.excerpt}>
              {message.subject || message.excerpt}
            </span>
            <span className="aw-tl-meta aw-ledger-meta">
              <Time value={message.at} />
            </span>
          </li>
        )}
      />

      {data.notices.length ? (
        <section className="aw-req-section" data-testid="ledger-notices">
          <h2 className="aw-req-heading">Repeated notices</h2>
          <ul className="aw-req-list">
            {data.notices.map((notice) => (
              <li key={notice.kind} data-testid={`ledger-notice-${notice.kind}`}>
                <StatePill tone="amber">{notice.count}</StatePill>
                <span className="aw-req-line">
                  {NOTICE_LABEL[notice.kind] ?? notice.kind.replace(/_/g, ' ')}
                  <span className="aw-tl-meta">
                    {' · '}
                    {notice.by_agent
                      .slice(0, 4)
                      .map((a) => `${a.agent ?? 'the Hub'} ${a.count}`)
                      .join(' · ')}
                  </span>
                </span>
                <span className="aw-tl-meta aw-ledger-meta">
                  latest <Time value={notice.last_at} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
