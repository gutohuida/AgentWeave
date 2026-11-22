import { Icon } from '@/components/common/Icon'
import { agentColorVars } from '@/lib/agentColors'
import { formatAgo, formatDateTime, formatMoney } from '@/lib/format'
import '@/styles/overview-lanes.css'
import type { ActivityOutcome, DashBuild, OverviewTarget } from './OverviewDashboard'
import { BUDGET_NEAR, budgetRatio, healthOf, tallyWords, type FinishedTally, type HealthLevel, type MainHealth, type SpendFigures } from './overviewDashboardModel'
import { compareLanes, spendShare, type LaneStatus } from './overviewLanesModel'

/** The Overview by who is doing what: a slim strip with the verdict and the five counts, one lane
 *  per profile, then the builds under way. Presentational: props in, callbacks out, no fetching. */

export interface OverviewLane {
  id: string
  name: string
  colorIndex?: number | null
  status: LaneStatus
  /** What it is doing now (or what it is waiting for), and since when. */
  doing: { what: string; since: string } | null
  /** Its last finished piece of work. */
  last: { what: string; outcome: ActivityOutcome; at: string } | null
  /** What it has open with the operator, one title each. */
  asks: string[]
  /** Spent today; null = turns the Hub could not price, never zero. */
  spendToday: number | null
  /** Opens its current thread. */
  onOpen: () => void
  /** Opens what it is waiting on you for. */
  onOpenAsks: () => void
}

export interface OverviewLanesProps {
  projectName: string
  lanes: OverviewLane[]
  needsCount: number
  runningCount: number
  finishedToday: FinishedTally | null
  spend: SpendFigures | null
  main: MainHealth
  builds: DashBuild[]
  onNavigate: (target: OverviewTarget) => void
  now: Date
}

const STATUS: Record<LaneStatus, { icon: string; word: string }> = {
  waiting: { icon: 'hand', word: 'Waiting on you' },
  stalled: { icon: 'alert_triangle', word: 'Stalled' },
  working: { icon: 'hammer', word: 'Working' },
  idle: { icon: 'clock', word: 'Idle' },
}
const OUTCOME: Record<ActivityOutcome, { icon: string; word: string }> = {
  running: { icon: 'hammer', word: 'Running' },
  landed: { icon: 'check', word: 'Landed' },
  sent_back: { icon: 'undo', word: 'Sent back' },
  failed: { icon: 'x', word: 'Failed' },
  stopped: { icon: 'stop', word: 'Stopped' },
}
const LEVEL: Record<HealthLevel, { icon: string }> = { healthy: { icon: 'check_circle' }, attention: { icon: 'hand' }, trouble: { icon: 'alert_triangle' } }

function Count({ label, value, hint, tone, opens, onOpen }: { label: string; value: string; hint?: string; tone?: 'amber' | 'red' | 'blue'; opens: string; onOpen: () => void }) {
  return (
    <button type="button" data-slot="lanes-count" className="aw-ol-count" data-tone={tone} onClick={onOpen} title={`Opens ${opens}`} aria-label={`${label}: ${value}${hint ? `, ${hint}` : ''}. Opens ${opens}`}>
      <span className="aw-ol-count-value tabular">{value}</span>
      <span className="aw-ol-count-label">{label}</span>
      {hint ? <span className="aw-ol-count-hint">{hint}</span> : null}
    </button>
  )
}

export function OverviewLanes({ projectName, lanes, needsCount, runningCount, finishedToday, spend, main, builds, onNavigate, now }: OverviewLanesProps) {
  const health = healthOf({ needs: needsCount, main, spend })
  const ratio = budgetRatio(spend)
  const finishedTotal = finishedToday ? finishedToday.landed + finishedToday.sentBack + finishedToday.failed : null
  const sorted = [...lanes].sort((a, b) => compareLanes({ status: a.status, asks: a.asks.length, name: a.name }, { status: b.status, asks: b.asks.length, name: b.name }))
  const allSpend = lanes.map((l) => l.spendToday)
  const branch = main.branch ?? 'main'
  const mainWord = { green: 'Green', held: 'Held', failing: 'Failing', unknown: 'Unknown' }[main.state]

  return (
    <div className="aw-ol" data-level={health.level}>
      <header className="aw-ol-strip">
        <div className="aw-ol-verdict" role="status" aria-label={`Project health: ${health.label}. ${health.sentence}`}>
          <span className="aw-ol-verdict-icon" aria-hidden>
            <Icon name={LEVEL[health.level].icon} size={18} />
          </span>
          <div className="aw-ol-verdict-text">
            <span className="aw-ol-project">{projectName}</span>
            <span className="aw-ol-sentence">
              <strong>{health.label}</strong> <span aria-hidden>&mdash;</span> {health.sentence}
            </span>
          </div>
        </div>
        <div className="aw-ol-counts">
          <Count label="Needs you" value={String(needsCount)} tone={needsCount > 0 ? 'amber' : undefined} opens="everything waiting on you" onOpen={() => onNavigate('needs')} />
          <Count label="Running" value={String(runningCount)} tone={runningCount > 0 ? 'blue' : undefined} opens="the running work" onOpen={() => onNavigate('running')} />
          <Count
            label="Finished today"
            value={finishedTotal == null ? '\u2014' : String(finishedTotal)}
            hint={finishedToday ? (finishedTotal ? tallyWords(finishedToday) : undefined) : 'not counted'}
            tone={finishedToday && finishedToday.failed > 0 ? 'red' : undefined}
            opens="the activity log"
            onOpen={() => onNavigate('finished')}
          />
          <Count
            label="Spend today"
            value={spend?.todayUsd != null ? formatMoney(spend.todayUsd) : '\u2014'}
            hint={ratio != null ? `${Math.round(ratio * 100)}% of budget` : spend ? undefined : 'not measured'}
            tone={ratio != null && ratio >= BUDGET_NEAR ? 'red' : undefined}
            opens="the spend ledger"
            onOpen={() => onNavigate('spend')}
          />
          <Count label={`Main`} value={mainWord} hint={branch} tone={main.state === 'failing' ? 'red' : main.state === 'held' || main.state === 'unknown' ? 'amber' : undefined} opens="the branch and its checks" onOpen={() => onNavigate('main')} />
        </div>
      </header>

      <section className="aw-ol-sec" aria-labelledby="ol-lanes">
        <div className="aw-ol-sec-head">
          <h2 id="ol-lanes">Team</h2>
          <span className="aw-ol-sub">needs you first, then working, then idle</span>
          <button type="button" data-slot="lanes-more" className="aw-ol-more" onClick={() => onNavigate('profiles')} title="Opens every profile and its settings">
            All profiles <Icon name="chevron_right" size={14} />
          </button>
        </div>
        <div className="aw-ol-colhead" aria-hidden>
          <span>Profile</span>
          <span>Doing now</span>
          <span>Last result</span>
          <span>Needs you</span>
          <span>Spend today</span>
        </div>
        <ul className="aw-ol-lanes">
          {sorted.map((l) => {
            const share = spendShare(l.spendToday, allSpend)
            const color = agentColorVars(l.colorIndex)
            const st = STATUS[l.status]
            return (
              <li key={l.id} className="aw-ol-lane" data-status={l.status} data-asks={l.asks.length > 0 ? 'true' : 'false'}>
                <div className="aw-ol-who">
                  <span className="aw-ol-avatar" aria-hidden style={{ borderColor: color.accent, background: color.tint }}>
                    {l.name.charAt(0).toUpperCase()}
                  </span>
                  <span className="aw-ol-who-text">
                    <button
                      type="button"
                      data-slot="lanes-open"
                      className="aw-ol-open"
                      onClick={l.onOpen}
                      title={`Opens ${l.name}'s current thread`}
                      aria-label={`${l.name}: ${st.word.toLowerCase()}${l.doing ? `, ${l.doing.what}` : ''}${l.asks.length ? `, ${l.asks.length} open ${l.asks.length === 1 ? 'question' : 'questions'} for you` : ''}. Opens its current thread`}
                    >
                      {l.name}
                    </button>
                    <span className="aw-ol-status" data-status={l.status}>
                      <Icon name={st.icon} size={13} /> {st.word}
                    </span>
                  </span>
                </div>
                <div className="aw-ol-cell aw-ol-doing">
                  {l.doing ? (
                    <>
                      <span className="aw-ol-text">{l.doing.what}</span>
                      <span className="aw-ol-sub-line tabular" title={formatDateTime(l.doing.since, now)}>
                        {l.status === 'waiting' ? 'waiting' : 'for'} {formatAgo(l.doing.since, now)}
                      </span>
                    </>
                  ) : (
                    <span className="aw-ol-muted">Nothing in progress</span>
                  )}
                </div>
                <div className="aw-ol-cell aw-ol-last">
                  {l.last ? (
                    <>
                      <span className="aw-ol-text">{l.last.what}</span>
                      <span className="aw-ol-sub-line" data-outcome={l.last.outcome}>
                        <Icon name={OUTCOME[l.last.outcome].icon} size={12} />
                        <span className="aw-ol-outcome">{OUTCOME[l.last.outcome].word}</span>
                        <span className="tabular" title={formatDateTime(l.last.at, now)}>
                          {formatAgo(l.last.at, now)}
                        </span>
                      </span>
                    </>
                  ) : (
                    <span className="aw-ol-muted">No finished work yet</span>
                  )}
                </div>
                <div className="aw-ol-cell aw-ol-asks">
                  {l.asks.length > 0 ? (
                    <button type="button" data-slot="lanes-asks" className="aw-ol-ask" onClick={l.onOpenAsks} title={l.asks.join('\n')} aria-label={`${l.name} has ${l.asks.length} open ${l.asks.length === 1 ? 'item' : 'items'} for you: ${l.asks.join('; ')}. Opens them`}>
                      <Icon name="hand" size={13} />
                      <span className="tabular">{l.asks.length}</span> open
                    </button>
                  ) : (
                    <span className="aw-ol-muted">None</span>
                  )}
                </div>
                <div className="aw-ol-cell aw-ol-spend">
                  {l.spendToday == null ? (
                    <span className="aw-ol-muted" title="The Hub could not price this profile's turns today">
                      Not priced
                    </span>
                  ) : (
                    <>
                      <span className="aw-ol-money tabular">{formatMoney(l.spendToday)}</span>
                      <span className="aw-ol-bar" role="img" aria-label={`${Math.round((share ?? 0) * 100)}% of the highest profile today`}>
                        <span style={{ width: `${Math.round((share ?? 0) * 100)}%` }} />
                      </span>
                    </>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </section>

      {builds.length > 0 ? (
        <section className="aw-ol-sec" aria-labelledby="ol-builds">
          <div className="aw-ol-sec-head">
            <h2 id="ol-builds">Builds</h2>
            <span className="aw-ol-badge tabular">{builds.length}</span>
            <button type="button" data-slot="lanes-more" className="aw-ol-more" onClick={() => onNavigate('builds')} title="Opens every build, running and finished">
              All builds <Icon name="chevron_right" size={14} />
            </button>
          </div>
          <ul className="aw-ol-builds">
            {builds.map((b) => (
              <li key={b.id}>
                <button type="button" data-slot="lanes-build" className="aw-ol-build" onClick={b.onOpen} title={`Opens the build \u201c${b.title}\u201d`} aria-label={`Build: ${b.title}, ${b.done} of ${b.total} tasks done, ${b.stage}. Opens the build`}>
                  <span className="aw-ol-build-title">{b.title}</span>
                  <span className="aw-ol-progress" role="progressbar" aria-label={`${b.title}: tasks done`} aria-valuemin={0} aria-valuemax={b.total} aria-valuenow={b.done}>
                    <span style={{ width: `${b.total ? (b.done / b.total) * 100 : 0}%` }} />
                  </span>
                  <span className="aw-ol-build-count tabular">
                    {b.done}/{b.total}
                  </span>
                  <span className="aw-ol-build-stage" data-needs={b.needsYou ? 'true' : 'false'}>
                    {b.needsYou ? <Icon name="hand" size={13} /> : null}
                    {b.stage}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <nav className="aw-ol-foot" aria-label="More about this project">
        <button type="button" data-slot="lanes-foot" onClick={() => onNavigate('chapters')} title="Opens the story of this project, chapter by chapter">
          <Icon name="route" size={15} /> Chapters
        </button>
        <button type="button" data-slot="lanes-foot" onClick={() => onNavigate('profiles')} title="Opens every profile and its settings">
          <Icon name="group" size={15} /> Profiles
        </button>
        <button type="button" data-slot="lanes-foot" onClick={() => onNavigate('dashboards')} title="Opens the dashboards of this project">
          <Icon name="bar_chart" size={15} /> Dashboards
        </button>
      </nav>
    </div>
  )
}