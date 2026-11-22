import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { agentColorVars } from '@/lib/agentColors'
import { formatAgo, formatCost, formatDateTime, formatDay, formatMoney } from '@/lib/format'
import '@/styles/overview-dashboard.css'
import type { NeedKind } from './OverviewView'
import {
  BUDGET_NEAR,
  agentList,
  budgetRatio,
  healthOf,
  tallyWords,
  type FinishedTally,
  type HealthLevel,
  type MainHealth,
  type SpendFigures,
} from './overviewDashboardModel'

/** The Overview as a control room: one health sentence, five tiles that each answer one question
 *  and open the page that answers it in full, the builds under way, then what needs you beside what
 *  has been happening. A check of health, not of detail; every click goes one step deeper.
 *
 *  Presentational: props in, callbacks out, no fetching. The existing `OverviewView` is untouched. */

export type OverviewTarget = 'needs' | 'running' | 'finished' | 'spend' | 'main' | 'builds' | 'chapters' | 'profiles' | 'dashboards'

export interface DashNeed {
  id: string
  kind: NeedKind
  agent: string | null
  colorIndex?: number | null
  title: string
  /** The verb the row offers: "Answer", "Review", "Try again". */
  action: string
  at: string
  onOpen: () => void
}

export type ActivityOutcome = 'running' | 'landed' | 'sent_back' | 'failed' | 'stopped'

export interface DashActivity {
  id: string
  agent: string
  colorIndex?: number | null
  what: string
  outcome: ActivityOutcome
  /** When it started (running) or ended. */
  at: string
  usd?: number | null
  onOpen: () => void
}

export interface DashBuild {
  id: string
  title: string
  done: number
  total: number
  /** Stage words: "Building task 5", "Checking", "Stalled". */
  stage: string
  needsYou: boolean
  onOpen: () => void
}

export interface OverviewDashboardProps {
  projectName: string
  needs: DashNeed[]
  /** Everything running right now, the count the tile shows. */
  running: DashActivity[]
  /** What ended recently, newest first, for the timeline. */
  finished: DashActivity[]
  /** Today: the tally, or null when the Hub cannot say. */
  finishedToday: FinishedTally | null
  spend: SpendFigures | null
  main: MainHealth
  builds: DashBuild[]
  onNavigate: (target: OverviewTarget) => void
  now: Date
}

const NEED_KIND: Record<NeedKind, { icon: string; word: string }> = {
  question: { icon: 'help_circle', word: 'Question' },
  merge: { icon: 'call_split', word: 'Landing' },
  review: { icon: 'fact_check', word: 'Review' },
  permission: { icon: 'lock', word: 'Permission' },
  stall: { icon: 'build', word: 'Stalled' },
  blocked: { icon: 'hourglass_top', word: 'Blocked' },
  main: { icon: 'call_split', word: 'Main' },
  offer: { icon: 'edit_note', word: 'Offer' },
  check: { icon: 'build', word: 'Check' },
}

const OUTCOME: Record<ActivityOutcome, { icon: string; word: string }> = {
  running: { icon: 'hammer', word: 'Running' },
  landed: { icon: 'check', word: 'Landed' },
  sent_back: { icon: 'undo', word: 'Sent back' },
  failed: { icon: 'x', word: 'Failed' },
  stopped: { icon: 'stop', word: 'Stopped' },
}

const LEVEL_ICON: Record<HealthLevel, string> = { healthy: 'check_circle', attention: 'hand', trouble: 'alert_triangle' }

function AgentMark({ name, colorIndex }: { name: string | null; colorIndex?: number | null }) {
  if (!name) return null
  return (
    <span className="aw-od-agent">
      <span className="aw-od-agent-dot" style={{ background: agentColorVars(colorIndex).accent }} aria-hidden />
      {name}
    </span>
  )
}

/** One tile: a single button, so a click anywhere on it opens the page behind the figure. */
function Tile({
  label,
  icon,
  tone,
  status,
  figure,
  figureTitle,
  lines,
  opens,
  onOpen,
  children,
}: {
  label: string
  icon: string
  tone: 'calm' | 'amber' | 'red' | 'info'
  /** The state in a word, so colour is never the only carrier. */
  status: string
  figure: string
  figureTitle?: string
  lines: React.ReactNode[]
  /** Where the click goes, for the title and the accessible name. */
  opens: string
  onOpen: () => void
  children?: React.ReactNode
}) {
  return (
    <button type="button" data-slot="overview-tile" className="aw-od-tile" data-tone={tone} onClick={onOpen} title={`Opens ${opens}`} aria-label={`${label}: ${figure}, ${status}. Opens ${opens}`}>
      <span className="aw-od-tile-head">
        <Icon name={icon} size={15} />
        <span className="aw-od-tile-label">{label}</span>
        <span className="aw-od-tile-status">{status}</span>
      </span>
      <span className="aw-od-tile-figure tabular" title={figureTitle}>
        {figure}
      </span>
      {lines.map((line, i) => (
        <span key={i} className={i === 0 ? 'aw-od-tile-line' : 'aw-od-tile-line aw-od-tile-line-2'}>
          {line}
        </span>
      ))}
      {children}
    </button>
  )
}

/** A thin line of the last days of spend. Days the Hub could not price break the line and say so in
 *  their hover text; they are never drawn as zero. */
function Sparkline({ trend, now }: { trend: SpendFigures['trend']; now: Date }) {
  const W = 132
  const H = 30
  const PAD = 5
  const known = trend.filter((t): t is { day: string; usd: number } => t.usd != null)
  if (trend.length < 2 || known.length === 0) return null
  const max = Math.max(...known.map((k) => k.usd))
  const x = (i: number) => PAD + (i * (W - PAD * 2)) / (trend.length - 1)
  const y = (v: number) => H - PAD - (v / (max || 1)) * (H - PAD * 2)
  const segments: string[] = []
  let run: string[] = []
  trend.forEach((t, i) => {
    if (t.usd == null) {
      if (run.length > 1) segments.push(run.join(' '))
      run = []
      return
    }
    run.push(`${run.length ? 'L' : 'M'}${x(i).toFixed(1)} ${y(t.usd).toFixed(1)}`)
  })
  if (run.length > 1) segments.push(run.join(' '))
  const lastIndex = trend.reduce((acc, t, i) => (t.usd != null ? i : acc), -1)
  const first = known[0]!
  const last = known[known.length - 1]!
  const label = `Daily spend, last ${trend.length} days: ${formatMoney(first.usd)} on ${formatDay(first.day, now)} to ${formatMoney(last.usd)} on ${formatDay(last.day, now)}`
  return (
    <svg className="aw-od-spark" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {segments.map((d, i) => (
        <path key={i} d={d} fill="none" stroke="var(--od-series)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {trend.map((t, i) =>
        t.usd == null ? (
          <g key={t.day}>
            <circle cx={x(i)} cy={H - PAD} r={3} fill="none" stroke="var(--text-3)" strokeWidth={1.5} />
            <circle cx={x(i)} cy={H / 2} r={9} fill="transparent">
              <title>{`${formatDay(t.day, now)}: not priced`}</title>
            </circle>
          </g>
        ) : (
          <g key={t.day}>
            {i === lastIndex ? <circle cx={x(i)} cy={y(t.usd)} r={4} fill="var(--od-series)" stroke="var(--surface)" strokeWidth={2} /> : null}
            <circle cx={x(i)} cy={y(t.usd)} r={8} fill="transparent">
              <title>{`${formatDay(t.day, now)}: ${formatCost(t.usd)}`}</title>
            </circle>
          </g>
        ),
      )}
    </svg>
  )
}

function Meter({ ratio, label }: { ratio: number; label: string }) {
  const pct = Math.min(100, Math.round(ratio * 100))
  return (
    <span className="aw-od-meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} data-near={ratio >= BUDGET_NEAR ? 'true' : 'false'}>
      <span className="aw-od-meter-fill" style={{ width: `${pct}%` }} />
    </span>
  )
}

export function OverviewDashboard({ projectName, needs, running, finished, finishedToday, spend, main, builds, onNavigate, now }: OverviewDashboardProps) {
  const health = healthOf({ needs: needs.length, main, spend })
  const ratio = budgetRatio(spend)
  const branch = main.branch ?? 'main'
  const finishedTotal = finishedToday ? finishedToday.landed + finishedToday.sentBack + finishedToday.failed : null
  const topNeed = needs[0]
  const timeline = [...running, ...finished]
  const shownNeeds = needs.slice(0, 4)
  const shownTimeline = timeline.slice(0, 6)

  const mainTone = main.state === 'failing' ? 'red' : main.state === 'held' || main.state === 'unknown' ? 'amber' : 'calm'
  const mainFigure = { green: 'Green', held: 'Held', failing: 'Failing', unknown: 'Unknown' }[main.state]
  const mainStatus = { green: 'All clear', held: 'Landing held', failing: 'Needs fixing', unknown: 'Not checked' }[main.state]
  const knownFailingWords = main.knownFailing == null ? 'known failures not checked' : `${main.knownFailing} known failing`
  const spendStatus = ratio == null ? (spend?.budgetUsd == null ? 'No budget' : 'Unknown') : ratio >= BUDGET_NEAR ? 'Near the limit' : 'Within budget'

  return (
    <div className="aw-od" data-level={health.level}>
      <header className="aw-od-health" role="status" aria-label={`Project health: ${health.label}. ${health.sentence}`}>
        <span className="aw-od-health-icon" aria-hidden>
          <Icon name={LEVEL_ICON[health.level]} size={22} />
        </span>
        <div className="aw-od-health-text">
          <span className="aw-od-project">{projectName}</span>
          <p className="aw-od-sentence">
            <strong>{health.label}</strong> <span aria-hidden>&mdash;</span> {health.sentence}
          </p>
        </div>
      </header>

      <section className="aw-od-tiles" aria-label="Project at a glance">
        <Tile
          label="Needs you"
          icon="hand"
          tone={needs.length > 0 ? 'amber' : 'calm'}
          status={needs.length > 0 ? 'Waiting on you' : 'Nothing waiting'}
          figure={String(needs.length)}
          lines={[topNeed ? topNeed.title : 'No question, review or approval is open.']}
          opens="everything waiting on you"
          onOpen={() => onNavigate('needs')}
        />
        <Tile
          label="Running"
          icon="hammer"
          tone={running.length > 0 ? 'info' : 'calm'}
          status={running.length > 0 ? 'Working' : 'Idle'}
          figure={String(running.length)}
          lines={[running.length > 0 ? agentList(running.map((r) => r.agent)) : 'No agent is working right now.']}
          opens="the running work"
          onOpen={() => onNavigate('running')}
        />
        <Tile
          label="Finished today"
          icon="check_circle"
          tone={finishedToday && finishedToday.failed > 0 ? 'red' : 'calm'}
          status={finishedToday == null ? 'Unknown' : finishedToday.failed > 0 ? 'Some failed' : 'No failures'}
          figure={finishedTotal == null ? '\u2014' : String(finishedTotal)}
          figureTitle={finishedTotal == null ? 'The Hub could not count the work finished today' : undefined}
          lines={[finishedToday == null ? 'Could not be counted.' : finishedTotal === 0 ? 'Nothing has finished yet today.' : tallyWords(finishedToday)]}
          opens="the activity log"
          onOpen={() => onNavigate('finished')}
        />
        <Tile
          label="Spend"
          icon="coins"
          tone={ratio != null && ratio >= BUDGET_NEAR ? 'red' : 'calm'}
          status={spendStatus}
          figure={spend?.todayUsd != null ? formatMoney(spend.todayUsd) : '\u2014'}
          figureTitle={spend?.todayUsd == null ? 'No turn today could be priced' : 'Spent today'}
          lines={[
            spend ? `today${spend.periodUsd != null ? ` \u00b7 ${formatMoney(spend.periodUsd)} ${spend.periodLabel}` : ''}` : 'Not measured',
            ratio != null && spend?.budgetUsd != null ? `${Math.round(ratio * 100)}% of the ${formatMoney(spend.budgetUsd)} budget` : null,
          ].filter((l): l is string => l != null)}
          opens="the spend ledger"
          onOpen={() => onNavigate('spend')}
        >
          {spend ? <Sparkline trend={spend.trend} now={now} /> : null}
          {ratio != null ? <Meter ratio={ratio} label="Budget used" /> : null}
        </Tile>
        <Tile
          label="Main and checks"
          icon="git_merge"
          tone={mainTone}
          status={mainStatus}
          figure={mainFigure}
          lines={[
            main.detail ?? `${branch}${main.state === 'green' ? ' passes its checks' : ''}`,
            [main.heldLandings ? `${main.heldLandings} ${main.heldLandings === 1 ? 'landing' : 'landings'} held` : null, knownFailingWords].filter(Boolean).join(' \u00b7 '),
          ]}
          opens="the branch and its checks"
          onOpen={() => onNavigate('main')}
        />
      </section>
      {builds.length > 0 ? (
        <section className="aw-od-builds" aria-labelledby="od-builds">
          <div className="aw-od-sec-head">
            <h2 id="od-builds">Builds in progress</h2>
            <span className="aw-od-badge tabular">{builds.length}</span>
            <button type="button" data-slot="overview-see-all" className="aw-od-more" onClick={() => onNavigate('builds')} title="Opens every build, running and finished">
              All builds <Icon name="chevron_right" size={14} />
            </button>
          </div>
          <ul className="aw-od-build-list">
            {builds.map((b) => (
              <li key={b.id}>
                <button type="button" data-slot="overview-build" className="aw-od-build" onClick={b.onOpen} title={`Opens the build \u201c${b.title}\u201d`} aria-label={`Build: ${b.title}, ${b.done} of ${b.total} tasks done, ${b.stage}. Opens the build`}>
                  <span className="aw-od-build-title">{b.title}</span>
                  <span className="aw-od-progress" role="progressbar" aria-label={`${b.title}: tasks done`} aria-valuemin={0} aria-valuemax={b.total} aria-valuenow={b.done}>
                    <span className="aw-od-progress-fill" style={{ width: `${b.total ? (b.done / b.total) * 100 : 0}%` }} />
                  </span>
                  <span className="aw-od-build-count tabular">
                    {b.done}/{b.total}
                  </span>
                  <span className="aw-od-build-stage" data-needs={b.needsYou ? 'true' : 'false'}>
                    {b.needsYou ? <Icon name="hand" size={13} /> : null}
                    {b.stage}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="aw-od-body">
        <section className="aw-od-panel" aria-labelledby="od-needs">
          <div className="aw-od-sec-head">
            <h2 id="od-needs">Needs you</h2>
            <span className="aw-od-badge tabular" data-tone={needs.length > 0 ? 'amber' : undefined}>
              {needs.length}
            </span>
            {needs.length > shownNeeds.length ? (
              <button type="button" data-slot="overview-see-all" className="aw-od-more" onClick={() => onNavigate('needs')} title="Opens everything waiting on you">
                See all {needs.length} <Icon name="chevron_right" size={14} />
              </button>
            ) : null}
          </div>
          {shownNeeds.length === 0 ? (
            <p className="aw-od-calm">
              <Icon name="check_circle" size={16} /> Nothing is waiting on you.
            </p>
          ) : (
            <ul className="aw-od-rows">
              {shownNeeds.map((n) => (
                <li key={n.id}>
                  <button type="button" data-slot="overview-need" className="aw-od-row aw-od-need" onClick={n.onOpen} title={`${n.action}: opens \u201c${n.title}\u201d`} aria-label={`${NEED_KIND[n.kind].word}: ${n.title}. ${n.action}`}>
                    <span className="aw-od-kind">
                      <Icon name={NEED_KIND[n.kind].icon} size={15} />
                      <span>{NEED_KIND[n.kind].word}</span>
                    </span>
                    <span className="aw-od-row-main">
                      <span className="aw-od-row-title">{n.title}</span>
                      <span className="aw-od-row-sub">
                        <AgentMark name={n.agent} colorIndex={n.colorIndex} />
                        <span title={formatDateTime(n.at, now)}>{formatAgo(n.at, now)}</span>
                      </span>
                    </span>
                    <span className="aw-od-action">
                      {n.action} <Icon name="arrow_forward" size={13} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="aw-od-panel" aria-labelledby="od-activity">
          <div className="aw-od-sec-head">
            <h2 id="od-activity">Activity</h2>
            <span className="aw-od-sub">newest first</span>
            <button type="button" data-slot="overview-see-all" className="aw-od-more" onClick={() => onNavigate('finished')} title="Opens the activity log">
              Open log <Icon name="chevron_right" size={14} />
            </button>
          </div>
          {shownTimeline.length === 0 && running.length === 0 ? (
            <p className="aw-od-calm">
              <Icon name="clock" size={16} /> Nothing has run yet.
            </p>
          ) : (
            <ol className="aw-od-timeline">
              {running.length === 0 ? (
                <li className="aw-od-idle">
                  <span className="aw-od-node" aria-hidden />
                  <span>Nothing is running right now.</span>
                </li>
              ) : null}
              {shownTimeline.map((a) => (
                <li key={a.id}>
                  <button type="button" data-slot="overview-activity" className="aw-od-row aw-od-act" data-outcome={a.outcome} onClick={a.onOpen} title={`Opens \u201c${a.what}\u201d`} aria-label={`${a.agent}: ${a.what}, ${OUTCOME[a.outcome].word}. Opens it`}>
                    <span className="aw-od-node" aria-hidden>
                      <Icon name={OUTCOME[a.outcome].icon} size={12} />
                    </span>
                    <span className="aw-od-row-main">
                      <span className="aw-od-row-title">{a.what}</span>
                      <span className="aw-od-row-sub">
                        <AgentMark name={a.agent} colorIndex={a.colorIndex} />
                        <span className="aw-od-outcome">{OUTCOME[a.outcome].word}</span>
                        {a.usd != null ? <span className="tabular">{formatCost(a.usd)}</span> : null}
                      </span>
                    </span>
                    <span className="aw-od-when tabular" title={formatDateTime(a.at, now)}>
                      {a.outcome === 'running' ? `${formatAgo(a.at, now)} in` : formatAgo(a.at, now)}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <nav className="aw-od-foot" aria-label="More about this project">
        <button type="button" data-slot="overview-foot" onClick={() => onNavigate('chapters')} title="Opens the story of this project, chapter by chapter">
          <Icon name="route" size={15} /> Chapters
        </button>
        <button type="button" data-slot="overview-foot" onClick={() => onNavigate('profiles')} title="Opens every profile and its settings">
          <Icon name="group" size={15} /> Profiles
        </button>
        <button type="button" data-slot="overview-foot" onClick={() => onNavigate('dashboards')} title="Opens the dashboards of this project">
          <Icon name="bar_chart" size={15} /> Dashboards
        </button>
      </nav>
    </div>
  )
}