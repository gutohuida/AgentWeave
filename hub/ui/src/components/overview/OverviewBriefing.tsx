import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { hubDate } from '@/lib/hubTime'
import { TaskStageWord } from '@/components/tasks/TaskStageWord'
import { formatAgo, formatAgoLong, formatCost, formatDateTime, formatDay, formatMoney } from '@/lib/format'
import '@/styles/overview-briefing.css'
import type { ActivityOutcome, DashActivity, DashBuild, DashNeed, OverviewTarget } from './OverviewDashboard'
import { BUDGET_NEAR, budgetRatio, healthOf, type FinishedTally, type HealthLevel, type MainHealth, type SpendFigures } from './overviewDashboardModel'
import { OUTCOME_ORDER, headline, summary } from './overviewBriefingModel'

/** The Overview as a morning briefing: a headline and a short summary in plain words, then short
 *  sections in priority order, each sentence carrying its own way one step deeper. Reading first,
 *  no tiles. Presentational: props in, callbacks out, no fetching. */

export interface OverviewBriefingProps {
  projectName: string
  /** When the operator last looked at this project; null when the Hub has no record. */
  lastSeenAt: string | null
  needs: DashNeed[]
  running: DashActivity[]
  /** What ended recently, newest first. */
  finished: DashActivity[]
  finishedToday: FinishedTally | null
  spend: SpendFigures | null
  main: MainHealth
  builds: DashBuild[]
  onNavigate: (target: OverviewTarget) => void
  now: Date
  /** The manager's note on what changed; absent until one is written. */
  note?: BriefingNote | null
}

export interface BriefingNote {
  writtenAt: string
  text: string
  /** What the note names, each opening its detail. */
  links: { key: string; label: string; onOpen: () => void }[]
  writing: boolean
  /** Why no note was written by the latest attempt; the previous note stays shown. */
  problem: string | null
  refreshing: boolean
  onRefresh: () => void
}

const LEVEL: Record<HealthLevel, { icon: string; word: string }> = {
  healthy: { icon: 'check_circle', word: 'All well' },
  attention: { icon: 'hand', word: 'Needs you' },
  trouble: { icon: 'alert_triangle', word: 'Trouble' },
}

const OUTCOME_HEAD: Record<ActivityOutcome, { icon: string; word: string }> = {
  running: { icon: 'hammer', word: 'Running' },
  landed: { icon: 'check', word: 'Landed' },
  sent_back: { icon: 'undo', word: 'Sent back' },
  failed: { icon: 'x', word: 'Failed' },
  stopped: { icon: 'stop', word: 'Stopped' },
}

/** One need as a sentence; the action is offered after it. */
function needSentence(kind: DashNeed['kind'], agent: string | null, title: string): React.ReactNode {
  const who = agent ? <strong>{agent}</strong> : null
  switch (kind) {
    case 'question':
      return <>{who} asks: &ldquo;{title}&rdquo;</>
    case 'review':
      return <>{who} finished &ldquo;{title}&rdquo; and wants your review.</>
    case 'permission':
      return <>{who} needs your permission: {title.charAt(0).toLowerCase() + title.slice(1)}.</>
    default:
      return <>{who ? <>{who}: </> : null}{title}.</>
  }
}

function lastSeenWords(lastSeenAt: string | null, now: Date): string | null {
  return lastSeenAt ? formatAgoLong(lastSeenAt, now) : null
}

function SpendBars({ trend, now }: { trend: SpendFigures['trend']; now: Date }) {
  const known = trend.filter((t): t is { day: string; usd: number } => t.usd != null)
  if (trend.length < 2 || known.length === 0) return null
  const max = Math.max(...known.map((k) => k.usd))
  const label = `Daily spend, last ${trend.length} days: ${trend.map((t) => `${formatDay(t.day, now)} ${t.usd == null ? 'not priced' : formatMoney(t.usd)}`).join(', ')}`
  const lastIndex = trend.length - 1
  return (
    <div className="aw-ob-chart" role="img" aria-label={label}>
      <div className="aw-ob-bars">
        {trend.map((t, i) => (
          <div key={t.day} className="aw-ob-bar-col" title={t.usd == null ? `${formatDay(t.day, now)}: not priced` : `${formatDay(t.day, now)}: ${formatCost(t.usd)}`}>
            {t.usd != null && i === lastIndex ? <span className="aw-ob-bar-value tabular">{formatMoney(t.usd)}</span> : null}
            {t.usd == null ? <span className="aw-ob-bar aw-ob-bar-unknown" /> : <span className="aw-ob-bar" data-today={i === lastIndex ? 'true' : 'false'} style={{ height: `${Math.max(6, (t.usd / max) * 100)}%` }} />}
          </div>
        ))}
      </div>
      <div className="aw-ob-axis" aria-hidden>
        <span>{formatDay(trend[0]!.day, now)}</span>
        <span>today</span>
      </div>
    </div>
  )
}

export function OverviewBriefing({ projectName, lastSeenAt, needs, running, finished, finishedToday, spend, main, builds, onNavigate, now, note }: OverviewBriefingProps) {
  const health = healthOf({ needs: needs.length, main, spend })
  const ratio = budgetRatio(spend)
  const branch = main.branch ?? 'main'
  const seenMs = lastSeenAt ? hubDate(lastSeenAt).getTime() : null
  const since = seenMs == null ? finished : finished.filter((f) => hubDate(f.at).getTime() > seenMs)
  const earlier = finished.length - since.length
  const words = lastSeenWords(lastSeenAt, now)
  const lines = summary({ lastSeenWords: words, finished: since, working: running })
  const finishedTotal = finishedToday ? finishedToday.landed + finishedToday.sentBack + finishedToday.failed : null

  return (
    <article className="aw-ob" data-level={health.level}>
      <header className="aw-ob-head">
        <p className="aw-ob-kicker">
          {projectName} <span aria-hidden>&middot;</span> {formatDateTime(now, now)}
        </p>
        <p className="aw-ob-level" role="status">
          <Icon name={LEVEL[health.level].icon} size={15} /> {LEVEL[health.level].word}
        </p>
        <h1 className="aw-ob-headline">{headline({ needs: needs.length, main, spend })}</h1>
        <p className="aw-ob-summary">{lines.join(' ')}</p>
      </header>

      {note ? (
        <section className="aw-ob-sec" aria-labelledby="ob-note" data-slot="briefing-note">
          <h2 id="ob-note">Note from the manager</h2>
          {note.writing ? (
            <p className="aw-ob-muted" role="status" data-slot="briefing-note-writing">
              Writing a note&hellip;
            </p>
          ) : null}
          {note.text ? (
            <>
              <p className="aw-ob-prose" data-slot="briefing-note-text">{note.text}</p>
              <p className="aw-ob-meta">
                Written <span title={formatDateTime(note.writtenAt, now)}>{formatAgo(note.writtenAt, now)}</span>
              </p>
              {note.links.length > 0 ? (
                <ul className="aw-ob-list aw-ob-list-tight" aria-label="Named in the note">
                  {note.links.map((l) => (
                    <li key={l.key}>
                      <button type="button" data-slot="briefing-note-link" className="aw-ob-link" onClick={l.onOpen} title={`Opens ${l.label}`}>
                        {l.label}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : !note.writing ? (
            <p className="aw-ob-muted">No note has been written yet.</p>
          ) : null}
          {note.problem ? (
            <p className="aw-ob-flag" role="alert" data-slot="briefing-note-problem">
              No note was written: {note.problem}
            </p>
          ) : null}
          <button type="button" data-slot="briefing-note-refresh" className="aw-ob-link aw-ob-more" onClick={note.onRefresh} disabled={note.refreshing || note.writing}>
            Refresh note
          </button>
        </section>
      ) : null}

      <section className="aw-ob-sec" aria-labelledby="ob-needs">
        <h2 id="ob-needs">Needs you</h2>
        {needs.length === 0 ? (
          <p className="aw-ob-muted">Nothing is waiting on you.</p>
        ) : (
          <ul className="aw-ob-list">
            {needs.map((n) => (
              <li key={n.id}>
                <span className="aw-ob-sentence">{needSentence(n.kind, n.agent, n.title)}</span>{' '}
                <button type="button" data-slot="briefing-action" className="aw-ob-link aw-ob-action" onClick={n.onOpen} title={`${n.action}: opens \u201c${n.title}\u201d`} aria-label={`${n.action}: ${n.title}`}>
                  {n.action} <Icon name="arrow_forward" size={13} />
                </button>
                <span className="aw-ob-when" title={formatDateTime(n.at, now)}>
                  {formatAgo(n.at, now)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="aw-ob-sec" aria-labelledby="ob-flight">
        <h2 id="ob-flight">In flight</h2>
        {builds.length === 0 && running.length === 0 ? (
          <p className="aw-ob-muted">Nothing is running right now.</p>
        ) : (
          <ul className="aw-ob-list">
            {builds.map((b) => (
              <li key={b.id}>
                <span className="aw-ob-sentence">
                  The build{' '}
                  <button type="button" data-slot="briefing-link" className="aw-ob-link" onClick={b.onOpen} title={`Opens the build \u201c${b.title}\u201d`} aria-label={`Build: ${b.title}, ${b.done} of ${b.total} tasks done, ${b.stage}. Opens the build`}>
                    {b.title}
                  </button>{' '}
                  has {b.done} of {b.total} tasks done: {b.stage.charAt(0).toLowerCase() + b.stage.slice(1)}.
                  {b.needsYou ? (
                    <span className="aw-ob-flag">
                      <Icon name="hand" size={13} /> needs you
                    </span>
                  ) : null}
                </span>
                <span className="aw-ob-progress" role="progressbar" aria-label={`${b.title}: tasks done`} aria-valuemin={0} aria-valuemax={b.total} aria-valuenow={b.done}>
                  <span className="aw-ob-progress-fill" style={{ width: `${b.total ? (b.done / b.total) * 100 : 0}%` }} />
                </span>
              </li>
            ))}
            {running.map((r) => (
              <li key={r.id}>
                <span className="aw-ob-sentence">
                  <strong>{r.agent}</strong> has been on{' '}
                  <button type="button" data-slot="briefing-link" className="aw-ob-link" onClick={r.onOpen} title={`Opens \u201c${r.what}\u201d`} aria-label={`${r.agent}: ${r.what}, running. Opens it`}>
                    {r.what}
                  </button>{' '}
                  for {formatAgo(r.at, now)}.
                </span>
                {r.stage ? <> <TaskStageWord stage={r.stage} check={r.check} size="xs" /></> : null}
              </li>
            ))}
          </ul>
        )}
        {builds.length > 0 ? (
          <button type="button" data-slot="briefing-more" className="aw-ob-link aw-ob-more" onClick={() => onNavigate('builds')} title="Opens every build, running and finished">
            All builds <Icon name="chevron_right" size={13} />
          </button>
        ) : null}
      </section>

      <section className="aw-ob-sec" aria-labelledby="ob-since">
        <h2 id="ob-since">{words ? 'Since you last looked' : 'Recently finished'}</h2>
        {words ? (
          <p className="aw-ob-marker">
            <span aria-hidden className="aw-ob-marker-rule" />
            <span title={lastSeenAt ? formatDateTime(lastSeenAt, now) : undefined}>You last looked {words}</span>
            <span aria-hidden className="aw-ob-marker-rule" />
          </p>
        ) : null}
        {since.length === 0 ? (
          <p className="aw-ob-muted">{words ? 'Nothing has finished since then.' : 'Nothing has finished yet.'}</p>
        ) : (
          OUTCOME_ORDER.map((o) => {
            const items = since.filter((s) => s.outcome === o)
            if (items.length === 0) return null
            return (
              <div key={o} className="aw-ob-group" data-outcome={o}>
                <h3>
                  <Icon name={OUTCOME_HEAD[o].icon} size={14} /> {OUTCOME_HEAD[o].word} <span className="aw-ob-count tabular">{items.length}</span>
                </h3>
                <ul className="aw-ob-list aw-ob-list-tight">
                  {items.map((a) => (
                    <li key={a.id}>
                      <button type="button" data-slot="briefing-link" className="aw-ob-link" onClick={a.onOpen} title={`Opens \u201c${a.what}\u201d`} aria-label={`${a.agent}: ${a.what}, ${OUTCOME_HEAD[a.outcome].word}. Opens it`}>
                        {a.what}
                      </button>
                      <span className="aw-ob-meta">
                        {a.agent}, <span title={formatDateTime(a.at, now)}>{formatAgo(a.at, now)}</span>
                        {a.usd != null ? <span className="tabular">, {formatCost(a.usd)}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })
        )}
        <button type="button" data-slot="briefing-more" className="aw-ob-link aw-ob-more" onClick={() => onNavigate('finished')} title="Opens the activity log">
          {words && earlier > 0 ? `${earlier} more finished earlier today. Open the log` : finishedTotal != null && finishedTotal > 0 ? `${finishedTotal} finished today. Open the log` : 'Open the log'} <Icon name="chevron_right" size={13} />
        </button>
      </section>

      <section className="aw-ob-sec" aria-labelledby="ob-spend">
        <h2 id="ob-spend">Spend</h2>
        {spend == null ? (
          <p className="aw-ob-muted">Spend is not measured for this project.</p>
        ) : (
          <>
            <p className="aw-ob-prose">
              {spend.todayUsd != null ? (
                <>
                  Today so far, <strong className="tabular">{formatMoney(spend.todayUsd)}</strong>.
                </>
              ) : (
                <>No turn today could be priced.</>
              )}{' '}
              {spend.periodUsd != null ? (
                <>
                  <strong className="tabular">{formatMoney(spend.periodUsd)}</strong> {spend.periodLabel}
                  {ratio != null && spend.budgetUsd != null ? (
                    <>
                      , {Math.round(ratio * 100)}% of the {formatMoney(spend.budgetUsd)} budget{ratio >= BUDGET_NEAR ? ': nearly all of it' : ''}
                    </>
                  ) : (
                    <>, with no budget set</>
                  )}
                  .
                </>
              ) : null}{' '}
              {spend.unpricedTurns > 0 ? `${spend.unpricedTurns} ${spend.unpricedTurns === 1 ? 'turn' : 'turns'} could not be priced, so the real figure is higher.` : null}
            </p>
            {ratio != null ? (
              <span className="aw-ob-meter" role="meter" aria-label="Budget used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(100, Math.round(ratio * 100))} data-near={ratio >= BUDGET_NEAR ? 'true' : 'false'}>
                <span style={{ width: `${Math.min(100, Math.round(ratio * 100))}%` }} />
              </span>
            ) : null}
            <SpendBars trend={spend.trend} now={now} />
          </>
        )}
        <button type="button" data-slot="briefing-more" className="aw-ob-link aw-ob-more" onClick={() => onNavigate('spend')} title="Opens the spend ledger">
          Open the spend ledger <Icon name="chevron_right" size={13} />
        </button>
      </section>

      <section className="aw-ob-sec" aria-labelledby="ob-main">
        <h2 id="ob-main">The main branch</h2>
        <p className="aw-ob-prose">
          {main.state === 'green' ? <><strong>{branch}</strong> is green. </> : main.state === 'failing' ? <><strong>{branch}</strong> is failing. </> : main.state === 'held' ? <>Landing on <strong>{branch}</strong> is held. </> : <>The health of <strong>{branch}</strong> has not been checked. </>}
          {main.detail && main.state !== 'green' ? `${main.detail}. ` : ''}
          {main.heldLandings ? `${main.heldLandings} ${main.heldLandings === 1 ? 'landing is' : 'landings are'} held. ` : ''}
          {main.knownFailing == null ? 'Known failures have not been checked.' : `${main.knownFailing} known failing.`}
        </p>
        <button type="button" data-slot="briefing-more" className="aw-ob-link aw-ob-more" onClick={() => onNavigate('main')} title="Opens the branch and its checks">
          Open the checks <Icon name="chevron_right" size={13} />
        </button>
      </section>

      <nav className="aw-ob-foot" aria-label="More about this project">
        <button type="button" data-slot="briefing-foot" onClick={() => onNavigate('chapters')} title="Opens the story of this project, chapter by chapter">
          <Icon name="route" size={15} /> Chapters
        </button>
        <button type="button" data-slot="briefing-foot" onClick={() => onNavigate('profiles')} title="Opens every profile and its settings">
          <Icon name="group" size={15} /> Profiles
        </button>
        <button type="button" data-slot="briefing-foot" onClick={() => onNavigate('dashboards')} title="Opens the dashboards of this project">
          <Icon name="bar_chart" size={15} /> Dashboards
        </button>
      </nav>
    </article>
  )
}