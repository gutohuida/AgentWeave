import * as React from 'react'
import type { QuestionOption } from '@/api/questions'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { agentColorVars } from '@/lib/agentColors'
import { formatAgo, formatDateTime, formatDuration, formatMoney, formatTokens, formatTokensExact } from '@/lib/format'
import '@/styles/overview.css'
import { LoadingThread } from '@/components/common/LoadingThread'

/** The Overview: what needs the operator, what is running, what just finished.
 *
 *  Replaces a page that opened on a seven-row table of unabbreviated token totals, then a second
 *  settings editor (Collaboration), with Attention below the fold, agent cards of unexplained chips
 *  and a "Navigate" block repeating the tabs. Spend is one line linking to the Ledger; the
 *  collaboration settings live in Settings. No page title: the active tab is the title. */

export type NeedKind = 'question' | 'merge' | 'review' | 'permission' | 'stall'

export interface NeedItem {
  id: string
  kind: NeedKind
  agent: string | null
  colorIndex?: number | null
  title: string
  detail?: string | null
  at: string
  /** A question: `true` when an agent holds a call open for the answer, `false` when none does.
   *  Absent for anything that is not a question. */
  waiting?: boolean
  /** A question's offered answers, answerable right here. */
  options?: QuestionOption[]
  primary: { label: string; onClick: () => void }
  secondary?: { label: string; onClick: () => void }
}

export interface RunningItem {
  id: string
  agent: string
  colorIndex?: number | null
  conversationTitle: string
  taskTitle?: string | null
  startedAt: string
  tokens?: number | null
  onOpen: () => void
}

export interface FinishedItem {
  id: string
  kind: 'merged' | 'approved' | 'turn'
  title: string
  detail: string
  at: string
  usd?: number | null
  onOpen?: () => void
}

export interface AgentStripItem {
  name: string
  colorIndex?: number | null
  /** `stalled` reads amber, like `waiting`: both are an agent not making progress. */
  state: 'running' | 'waiting' | 'stalled' | 'idle' | 'no-runner'
  /** One sentence: "Working on …", "Waiting for your answer", "Last active 1h ago". */
  doing: string
  /** Null when none of its turns was priced: a dash, never a $0.00 it did not spend. */
  usd: number | null
  /** The status word for the row's accessible name ("Open claude, Stalled"). */
  statusLabel?: string
  /** Controls of the agent's own, beside the row and never inside its button (its posture). */
  extra?: React.ReactNode
  onOpen: () => void
}

const NEED_ICON: Record<NeedKind, { icon: string; tone: 'amber' | 'red' | 'blue' }> = {
  question: { icon: 'help_circle', tone: 'amber' },
  merge: { icon: 'call_split', tone: 'red' },
  review: { icon: 'fact_check', tone: 'blue' },
  permission: { icon: 'lock', tone: 'amber' },
  stall: { icon: 'build', tone: 'red' },
}

export function OverviewView({
  needs,
  running,
  finished,
  agents,
  spend,
  onOpenLedger,
  onAnswer,
  onOpenQuestions,
  taskTotal,
  heldByBudget,
  onOpenTasks,
  notice,
  loading,
  onAddAgent,
  now,
}: {
  needs: NeedItem[]
  running: RunningItem[]
  finished: FinishedItem[]
  agents: AgentStripItem[]
  spend: {
    /** Null when no turn was priced: the credits stand in, or a dash. */
    usd: number | null
    tokens: number
    period: string
    /** The credits the project's turns reported (Copilot); the figure itself when usd is null. */
    credits?: string | null
    /** What the figure leaves out or is measured by ("1 turn unpriced", the allowance). */
    notes?: string[]
  }
  onOpenLedger: () => void
  onAnswer?: (need: NeedItem, option: QuestionOption) => void
  /** Answered questions and permission decisions, reachable with nothing open (F636). */
  onOpenQuestions?: () => void
  /** The ledger's own task total, never the length of a page of it (F202). */
  taskTotal?: number
  /** Turns waiting only for the budget: they need the operator, so they are not "nothing" (F953). */
  heldByBudget?: number
  onOpenTasks?: () => void
  /** A project-wide condition worth one line above everything (a paused budget). */
  notice?: React.ReactNode
  loading?: boolean
  /** Opens the Add-agent dialog (F808: agents are added in the app, not with a CLI command). */
  onAddAgent?: () => void
  now: Date
}) {
  if (loading) {
    return (
      <div className="aw-overview">
        <LoadingThread label="Loading overview" minHeight={240} />
      </div>
    )
  }
  return (
    <div className="aw-overview">
      {notice ? <div className="aw-overview-notice">{notice}</div> : null}
      <div className="aw-overview-summary">
        <p className="aw-overview-status">
          {needs.length ? (
            <span className="aw-overview-status-need">
              {needs.length} {needs.length === 1 ? 'thing needs' : 'things need'} you
            </span>
          ) : heldByBudget ? null : (
            <span>Nothing needs you</span>
          )}
          {heldByBudget ? (
            <>
              {needs.length ? <span aria-hidden="true">·</span> : null}
              <span className="aw-overview-status-need">
                {heldByBudget} {heldByBudget === 1 ? 'turn' : 'turns'} held by the budget
              </span>
            </>
          ) : null}
          <span aria-hidden="true">·</span>
          <span>{running.length ? `${running.length} running` : 'Nothing running'}</span>
          {taskTotal != null ? (
            <>
              <span aria-hidden="true">·</span>
              <button data-slot="overview-tasks" type="button" className="aw-overview-link" onClick={onOpenTasks}>
                {taskTotal} {taskTotal === 1 ? 'task' : 'tasks'}
              </button>
            </>
          ) : null}
        </p>
        <button data-slot="spend-line" type="button" className="aw-overview-spend" onClick={onOpenLedger} title={formatTokensExact(spend.tokens)}>
          <span className="tabular">{spend.usd != null ? formatMoney(spend.usd) : (spend.credits ?? '—')}</span> {spend.period}
          <span aria-hidden="true">·</span>
          <span className="tabular">{formatTokens(spend.tokens)}</span>
          {[spend.usd != null ? spend.credits : null, ...(spend.notes ?? [])].filter(Boolean).map((note) => (
            <React.Fragment key={note}>
              <span aria-hidden="true">·</span>
              <span>{note}</span>
            </React.Fragment>
          ))}
          <span className="aw-overview-spend-link">
            Ledger <Icon name="arrow_forward" size={12} />
          </span>
        </button>
      </div>

      <section className="aw-ov-section" aria-labelledby="ov-needs">
        <div className="aw-ov-heading-row">
          <h2 id="ov-needs" className="aw-ov-heading">
            Needs you {needs.length ? <span className="aw-ov-count" data-tone="amber">{needs.length}</span> : null}
          </h2>
          {onOpenQuestions ? (
            <button data-slot="overview-questions" type="button" className="aw-overview-link" data-testid="overview-questions-link" onClick={onOpenQuestions}>
              Answered questions and permission decisions
            </button>
          ) : null}
        </div>
        {needs.length === 0 ? (
          <div className="aw-ov-calm">
            <Icon name="check_circle" size={15} /> No questions, approvals or failed merges are waiting.
          </div>
        ) : (
          <ul className="aw-ov-needs">
            {needs.map((need) => {
              const meta = NEED_ICON[need.kind]
              const color = need.agent ? agentColorVars(need.colorIndex) : null
              return (
                <li key={need.id} className="aw-ov-need" data-tone={meta.tone}>
                  <span className="aw-ov-need-icon" aria-hidden="true">
                    <Icon name={meta.icon} size={15} />
                  </span>
                  <div className="aw-ov-need-body">
                    <p className="aw-ov-need-title">{need.title}</p>
                    {need.detail ? <p className="aw-ov-need-detail">{need.detail}</p> : null}
                    {need.options?.length ? (
                      <div className="aw-ov-options" role="group" aria-label="Answers">
                        {need.options.map((option) => (
                          <button
                            key={option.label}
                            data-slot="answer-option"
                            type="button"
                            className="aw-ov-option"
                            title={option.description}
                            onClick={() => onAnswer?.(need, option)}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <p className="aw-ov-need-meta">
                      {need.agent ? (
                        <span className="aw-ov-agent" style={{ '--agent-accent': color!.accent } as React.CSSProperties}>
                          <span className="aw-agent-dot" /> {need.agent}
                          {need.waiting === undefined ? '' : need.waiting ? ' is waiting' : ' is asking'}
                        </span>
                      ) : null}
                      <time dateTime={need.at} title={formatDateTime(need.at, now)}>
                        {formatAgo(need.at, now)} ago
                      </time>
                    </p>
                  </div>
                  <div className="aw-ov-need-actions">
                    {need.secondary ? (
                      <Button variant="ghost" size="sm" onClick={need.secondary.onClick}>
                        {need.secondary.label}
                      </Button>
                    ) : null}
                    <Button variant={need.options?.length ? 'outline' : 'primary'} size="sm" onClick={need.primary.onClick}>
                      {need.primary.label}
                    </Button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section className="aw-ov-section" aria-labelledby="ov-running">
        <h2 id="ov-running" className="aw-ov-heading">
          Running now {running.length ? <span className="aw-ov-count" data-tone="green">{running.length}</span> : null}
        </h2>
        {running.length === 0 ? (
          <div className="aw-ov-calm">No agent is working right now.</div>
        ) : (
          <ul className="aw-ov-list">
            {running.map((r) => (
              <RunningRow key={r.id} item={r} now={now} />
            ))}
          </ul>
        )}
      </section>

      <div className="aw-ov-columns">
        <section className="aw-ov-section" aria-labelledby="ov-finished">
          <h2 id="ov-finished" className="aw-ov-heading">Recently finished</h2>
          {finished.length === 0 ? <div className="aw-ov-calm">Nothing has merged yet.</div> : null}
          <ul className="aw-ov-list">
            {finished.map((f) => (
              <li key={f.id}>
                <button data-slot="finished-row" type="button" className="aw-ov-row" onClick={f.onOpen}>
                  <span className="aw-ov-row-icon" data-kind={f.kind} aria-hidden="true">
                    <Icon name={f.kind === 'merged' ? 'call_split' : f.kind === 'approved' ? 'check_circle' : 'smart_toy'} size={13} />
                  </span>
                  <span className="aw-ov-row-text">
                    <span className="aw-ov-row-title">{f.title}</span>
                    <span className="aw-ov-row-detail">{f.detail}</span>
                  </span>
                  <span className="aw-ov-row-end">
                    {f.usd != null ? <span className="tabular">{formatMoney(f.usd)}</span> : null}
                    <time dateTime={f.at} title={formatDateTime(f.at, now)}>
                      {formatAgo(f.at, now)}
                    </time>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="aw-ov-section" aria-labelledby="ov-agents">
          <h2 id="ov-agents" className="aw-ov-heading">Agents</h2>
          {agents.length === 0 ? (
            <div className="aw-ov-calm">
              No agents yet.{' '}
              {onAddAgent ? (
                <button data-slot="add-agent" type="button" className="aw-overview-link" onClick={onAddAgent}>
                  Add agent
                </button>
              ) : (
                'Add one from the sidebar.'
              )}
            </div>
          ) : null}
          <ul className="aw-ov-list">
            {agents.map((a) => {
              const color = agentColorVars(a.colorIndex)
              return (
                <li key={a.name} data-testid={`agent-card-${a.name}`}>
                  <button
                    data-slot="agent-row"
                    type="button"
                    className="aw-ov-row aw-ov-agent-row"
                    data-state={a.state}
                    onClick={a.onOpen}
                    aria-label={a.statusLabel ? `Open ${a.name}, ${a.statusLabel}` : undefined}
                    style={{ '--agent-accent': color.accent } as React.CSSProperties}
                  >
                    <span className={['aw-agent-dot', a.state === 'running' ? 'aw-pulse' : ''].join(' ')} aria-hidden="true" />
                    <span className="aw-ov-row-text">
                      <span className="aw-ov-row-title">{a.name}</span>
                      <span className="aw-ov-row-detail" data-state={a.state}>
                        {a.doing}
                      </span>
                    </span>
                    <span className="aw-ov-row-end tabular" title="Spent so far">
                      {a.usd != null ? formatMoney(a.usd) : '—'}
                    </span>
                  </button>
                  {a.extra ? <div className="aw-ov-agent-extra">{a.extra}</div> : null}
                </li>
              )
            })}
          </ul>
        </section>
      </div>
    </div>
  )
}

/** Elapsed time ticks once a second through a ref, so the page does not re-render per tick. */
function RunningRow({ item, now }: { item: RunningItem; now: Date }) {
  const color = agentColorVars(item.colorIndex)
  const elapsedRef = React.useRef<HTMLSpanElement>(null)
  React.useEffect(() => {
    const started = Date.parse(item.startedAt)
    const offset = now.getTime() - Date.now()
    const tick = () => {
      if (elapsedRef.current) elapsedRef.current.textContent = formatDuration((Date.now() + offset - started) / 1000)
    }
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [item.startedAt, now])
  return (
    <li>
      <button
        data-slot="running-row"
        type="button"
        className="aw-ov-row aw-ov-running"
        onClick={item.onOpen}
        style={{ '--agent-accent': color.accent, '--agent-tint': color.tint } as React.CSSProperties}
      >
        <span className="aw-ov-running-badge" aria-hidden="true">
          {item.agent.slice(0, 1)}
          <span className="aw-ov-running-dot aw-pulse" />
        </span>
        <span className="aw-ov-row-text">
          <span className="aw-ov-row-title">
            <strong>{item.agent}</strong> · {item.conversationTitle}
          </span>
          {item.taskTitle ? <span className="aw-ov-row-detail">Task: {item.taskTitle}</span> : null}
        </span>
        <span className="aw-ov-row-end">
          <span ref={elapsedRef} className="tabular aw-ov-elapsed" />
          {item.tokens != null ? <span className="tabular">{formatTokens(item.tokens)}</span> : null}
          <span className="aw-ov-open">
            Open <Icon name="arrow_forward" size={12} />
          </span>
        </span>
      </button>
    </li>
  )
}
