import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { MenuSelect } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { agentColorVars } from '@/lib/agentColors'
import type { DigestDay, DigestKind, DigestRow } from '@/lib/activityDigest'
import { formatDateTime, formatDay, formatDuration, formatMoney, formatTokens } from '@/lib/format'
import '@/styles/activity.css'
import { hubDate } from '@/lib/hubTime'

/** The Activity digest: one sentence per thing that happened, grouped by day, newest first.
 *  A row opens to the raw events behind it, so nothing the old list showed is lost. */

export type DigestFilter = 'all' | 'turns' | 'work' | 'attention'

const FILTERS: Record<DigestFilter, (r: DigestRow) => boolean> = {
  all: () => true,
  turns: (r) => r.kind === 'turn',
  work: (r) => r.kind === 'task' || r.kind === 'merge' || r.kind === 'checkout' || r.kind === 'loop' || r.kind === 'message',
  attention: (r) => r.severity !== 'info',
}

const KIND_ICON: Record<DigestKind, string> = {
  turn: 'smart_toy',
  task: 'task_alt',
  message: 'chat',
  merge: 'call_split',
  loop: 'sync',
  warning: 'warning',
  checkout: 'folder',
  background: 'monitoring',
}

function dayLabel(day: string, now: Date): string {
  const today = now
  const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  if (day === key(today)) return 'Today'
  const y = new Date()
  y.setTime(today.getTime())
  y.setDate(y.getDate() - 1)
  if (day === key(y)) return 'Yesterday'
  return formatDay(day, now)
}

function clock(iso: string): string {
  const d = hubDate(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function ActivityDigest({
  days,
  agents,
  colorIndexOf,
  onOpenConversation,
  now,
}: {
  days: DigestDay[]
  agents: string[]
  colorIndexOf: (agent: string) => number | null | undefined
  onOpenConversation?: (agent: string, conversationId: string) => void
  now: Date
}) {
  const [filter, setFilter] = React.useState<DigestFilter>('all')
  const [agent, setAgent] = React.useState('__all')
  const [open, setOpen] = React.useState<Record<string, boolean>>({})

  const visible = days
    .map((d) => ({
      ...d,
      rows: d.rows.filter((r) => FILTERS[filter](r) && (agent === '__all' || r.agent === agent)),
    }))
    .filter((d) => d.rows.length || (filter === 'all' && agent === '__all' && d.background))

  const counts = {
    all: days.reduce((n, d) => n + d.rows.length, 0),
    attention: days.reduce((n, d) => n + d.rows.filter(FILTERS.attention).length, 0),
  }

  return (
    <div className="aw-digest">
      <div className="aw-digest-toolbar">
        <Segmented
          label="Show"
          size="xs"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'Everything', count: counts.all },
            { value: 'turns', label: 'Turns' },
            { value: 'work', label: 'Work' },
            { value: 'attention', label: 'Warnings', count: counts.attention },
          ]}
        />
        <MenuSelect
          label="Agent"
          value={agent}
          onChange={setAgent}
          maxWidth={200}
          options={[{ value: '__all', label: 'Every agent' }, ...agents.map((a) => ({ value: a, label: a, icon: <span className="aw-agent-dot" style={{ background: agentColorVars(colorIndexOf(a)).accent }} /> }))]}
        />
      </div>

      {visible.length === 0 ? (
        <div className="aw-digest-empty">
          <Icon name="monitoring" size={18} />
          <p>Nothing matches. Try “Everything” or another agent.</p>
        </div>
      ) : null}

      {visible.map((day) => (
        <section key={day.day} className="aw-digest-day" aria-label={dayLabel(day.day, now)}>
          <h2 className="aw-digest-day-label">
            {dayLabel(day.day, now)}
            <span className="aw-digest-day-count">{day.rows.length}</span>
          </h2>
          <ol className="aw-digest-list">
            {day.rows.map((row) => {
              const isOpen = !!open[row.id]
              const color = row.agent ? agentColorVars(colorIndexOf(row.agent)) : null
              const facts = [
                row.durationSeconds != null ? formatDuration(row.durationSeconds) : null,
                row.tokens != null ? formatTokens(row.tokens) : null,
                row.usd != null ? formatMoney(row.usd) : null,
              ].filter(Boolean)
              return (
                <li key={row.id} className="aw-digest-row" data-severity={row.severity} data-open={isOpen ? 'true' : 'false'}>
                  <button
                    data-slot="digest-row"
                    type="button"
                    className="aw-digest-row-main"
                    aria-expanded={isOpen}
                    onClick={() => setOpen((s) => ({ ...s, [row.id]: !isOpen }))}
                  >
                    <time className="aw-digest-time" dateTime={row.at} title={formatDateTime(row.at, now)}>
                      {clock(row.at)}
                    </time>
                    <span className="aw-digest-icon" data-kind={row.kind} style={color ? ({ '--agent-accent': color.accent, '--agent-tint': color.tint } as React.CSSProperties) : undefined}>
                      {row.kind === 'turn' && row.agent ? <span className="aw-digest-initial">{row.agent.slice(0, 1)}</span> : <Icon name={KIND_ICON[row.kind]} size={13} />}
                    </span>
                    <span className="aw-digest-text">
                      <span className="aw-digest-sentence">
                        {row.lead ? <strong style={color ? { color: color.accent } : undefined}>{row.lead} </strong> : null}
                        {row.text}
                      </span>
                      {row.detail ? <span className="aw-digest-detail">{row.detail}</span> : null}
                    </span>
                    {facts.length ? <span className="aw-digest-facts">{facts.join(' · ')}</span> : null}
                    <Icon name="chevron_right" size={13} className="aw-digest-chevron" />
                  </button>
                  <div className="aw-digest-raw" aria-hidden={!isOpen}>
                    <div className="aw-digest-raw-inner">
                      <ul className="aw-digest-events">
                        {row.events.map((e) => (
                          <li key={e.id}>
                            <span className="aw-digest-event-time">{clock(e.timestamp)}</span>
                            <span className="aw-digest-event-type">{e.event_type}</span>
                            <span className="aw-digest-event-data">{summarize(e.data)}</span>
                          </li>
                        ))}
                      </ul>
                      {row.kind === 'turn' && row.conversationId && row.agent && onOpenConversation ? (
                        <button data-slot="digest-link" type="button" className="aw-digest-link" onClick={() => onOpenConversation(row.agent!, row.conversationId!)}>
                          Open the conversation <Icon name="arrow_forward" size={12} />
                        </button>
                      ) : null}
                    </div>
                  </div>
                </li>
              )
            })}
            {day.background && filter === 'all' && agent === '__all' ? (
              <li className="aw-digest-background">
                <span className="aw-digest-time" />
                <Icon name="monitoring" size={12} />
                <span>Hub bookkeeping: {day.background.text}</span>
              </li>
            ) : null}
          </ol>
        </section>
      ))}
    </div>
  )
}

function summarize(data: Record<string, unknown> | undefined): string {
  if (!data) return ''
  return Object.entries(data)
    .filter(([k, v]) => v != null && v !== '' && typeof v !== 'object' && !['agent', 'session_id'].includes(k))
    .slice(0, 5)
    .map(([k, v]) => `${k}=${String(v).length > 48 ? String(v).slice(0, 47) + '…' : String(v)}`)
    .join('  ')
}
