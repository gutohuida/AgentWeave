import { Fragment, useState } from 'react'
import { useProjectStats, ROLES, WALL_PARTS, type Grouping, type Role, type WallPart, type WorkGroup, type WorkRow, type WorkTally } from '@/api/stats'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Segmented } from '@/components/ui/segmented'
import { formatDuration, formatMoney } from '@/lib/format'

/**
 * The project's work (`project-stats-come-from-the-same-records`): where the work went, grouped by
 * spec, agent, model or level, from `GET /stats`, the same tally the spec page's build card reads.
 * Cost and run time are split by role with the mender on a line of its own; a figure no record
 * reports reads "unknown", never $0; an unpriced run is counted beside the cost.
 */

const GROUPINGS: Array<{ value: Grouping; label: string }> = [
  { value: 'spec', label: 'Spec' },
  { value: 'agent', label: 'Agent' },
  { value: 'model', label: 'Model' },
  { value: 'level', label: 'Level' },
]

const WALL_LABEL: Record<WallPart, string> = {
  building: 'building',
  reviewing: 'reviewing',
  checks: 'checks',
  held: 'held by a failed check',
  review: 'waiting for review',
  waiting: 'waiting to be handed out',
}

const MICROS = 1_000_000

/** Dollars from micros; null (nobody reported a cost) is unknown, or a dash where nothing ran. */
function money(micros: number | null, ran: number): string {
  if (micros === null) return ran > 0 ? 'unknown' : '—'
  return formatMoney(micros / MICROS)
}

function credits(row: WorkRow): string | null {
  const parts: string[] = []
  if (row.ai_nano_aiu !== null) parts.push(`${(row.ai_nano_aiu / 1e9).toFixed(2)} AIU`)
  if (row.premium_requests !== null) parts.push(`${row.premium_requests} premium requests`)
  return parts.length ? parts.join(' · ') : null
}

function RoleCell({ row, role }: { row: WorkRow; role: Role }) {
  const runs = row.runs[role]
  return (
    <td className="aw-work-num" data-role={role} data-testid={`work-${role}`}>
      <strong>{money(row.cost_micros[role], runs)}</strong>
      <small>{runs ? `${runs} run${runs === 1 ? '' : 's'} · ${formatDuration(row.run_seconds[role])}` : 'none'}</small>
    </td>
  )
}

function CostCell({ row }: { row: WorkRow }) {
  const extra = [row.unpriced ? `${row.unpriced} unpriced` : null, credits(row)].filter(Boolean)
  return (
    <td className="aw-work-num" data-testid="work-cost">
      <strong>{money(row.cost_micros.total, row.runs.total)}</strong>
      <small>
        {row.runs.total} run{row.runs.total === 1 ? '' : 's'}
        {extra.length ? ` · ${extra.join(' · ')}` : ''}
      </small>
    </td>
  )
}

function WallCell({ row, show }: { row: WorkRow; show: boolean }) {
  if (!show) return <td className="aw-work-num">—</td>
  const parts = WALL_PARTS.filter((p) => row.wall[p] > 0)
  return (
    <td className="aw-work-num" data-testid="work-wall">
      <strong>{row.wall.total ? formatDuration(row.wall.total) : '—'}</strong>
      <small>{parts.map((p) => `${formatDuration(row.wall[p])} ${WALL_LABEL[p]}`).join(' · ')}</small>
    </td>
  )
}

function QualityCells({ row }: { row: WorkRow }) {
  const { checks, send_backs: sb, pieces, beside_failing: beside } = row
  return (
    <>
      <td className="aw-work-num" data-testid="work-checks">
        <strong>{checks.runs ? `${checks.runs} run${checks.runs === 1 ? '' : 's'}` : '—'}</strong>
        <small>{checks.runs ? `${checks.passed} passed · ${checks.failed} failed · ${formatDuration(checks.seconds)}` : ''}</small>
      </td>
      <td className="aw-work-num" data-testid="work-sendbacks">
        <strong>{sb.made || sb.received ? `${sb.made} made · ${sb.received} received` : '—'}</strong>
      </td>
      <td className="aw-work-num" data-testid="work-pieces">
        <strong>
          {pieces.accepted || pieces.rejected || pieces.held || pieces.awaiting
            ? `${pieces.accepted} accepted · ${pieces.rejected} rejected · ${pieces.held} held`
            : '—'}
        </strong>
        <small>{pieces.awaiting ? `${pieces.awaiting} awaiting` : ''}</small>
      </td>
      <td className="aw-work-num" data-testid="work-beside">
        <strong>{beside.count ? `${beside.count} · ${money(beside.cost_micros, beside.count)}` : '—'}</strong>
        <small>{beside.count ? formatDuration(beside.run_seconds) : ''}</small>
      </td>
    </>
  )
}

function WorkRowCells({ row, showWall }: { row: WorkRow; showWall: boolean }) {
  return (
    <>
      <CostCell row={row} />
      {ROLES.filter((r) => r !== 'other').map((role) => (
        <RoleCell key={role} row={row} role={role} />
      ))}
      <WallCell row={row} show={showWall} />
      <QualityCells row={row} />
    </>
  )
}

function GroupRows({ grouping, group }: { grouping: Grouping; group: WorkGroup }) {
  const showWall = grouping === 'spec' || grouping === 'level'
  const id = `work-row-${grouping}-${group.key ?? 'none'}`
  return (
    <Fragment>
      <tr data-testid={id} data-none={group.key === null ? 'true' : undefined}>
        <th scope="row" className="aw-work-name" title={group.path ?? undefined}>
          {group.label}
        </th>
        <WorkRowCells row={group.row} showWall={showWall} />
      </tr>
      {(group.builds ?? []).map((build, index) => (
        <tr key={build.id} className="aw-work-sub" data-testid={`work-build-${build.id}`}>
          <th scope="row" className="aw-work-name">
            Build {index + 1} · {build.level}
          </th>
          <WorkRowCells row={build.row} showWall />
        </tr>
      ))}
      {group.before_builds ? (
        <tr className="aw-work-sub" data-testid={`work-before-${group.key}`}>
          <th scope="row" className="aw-work-name">
            before builds
          </th>
          <WorkRowCells row={group.before_builds} showWall={false} />
        </tr>
      ) : null}
    </Fragment>
  )
}

/** The table, given a tally: `ProjectWork` fetches it, the mock and the tests hand it in. */
export function WorkView({
  tally,
  grouping,
  onGrouping,
  since,
  onSince,
}: {
  tally: WorkTally
  grouping: Grouping
  onGrouping: (grouping: Grouping) => void
  since: string
  onSince: (since: string) => void
}) {
  const showWall = grouping === 'spec' || grouping === 'level'
  const hub = tally.workers
  return (
    <section className="aw-req-section aw-work" data-testid="project-work">
      <div className="aw-work-head">
        <h2 className="aw-req-heading">Work</h2>
        <Segmented<Grouping> label="Group work by" value={grouping} onChange={onGrouping} options={GROUPINGS} />
        <label className="aw-work-since">
          <span>Since</span>
          <input type="date" value={since} onChange={(e) => onSince(e.target.value)} aria-label="Since" />
        </label>
      </div>
      <div className="aw-work-scroll">
        <table className="aw-work-table">
          <thead>
            <tr>
              <th scope="col">{GROUPINGS.find((g) => g.value === grouping)?.label}</th>
              <th scope="col">Cost</th>
              <th scope="col">Building</th>
              <th scope="col">Reviewing</th>
              <th scope="col">Leading</th>
              <th scope="col">Mending</th>
              <th scope="col">Wall time</th>
              <th scope="col">Checks</th>
              <th scope="col">Send-backs</th>
              <th scope="col">Pieces</th>
              <th scope="col">Reviews beside a failing check</th>
            </tr>
          </thead>
          <tbody>
            {tally.groups[grouping].map((group) => (
              <GroupRows key={group.key ?? 'none'} grouping={grouping} group={group} />
            ))}
          </tbody>
          <tfoot>
            <tr data-testid="work-totals">
              <th scope="row" className="aw-work-name">
                All
              </th>
              <WorkRowCells row={tally.total} showWall={showWall} />
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="aw-tl-meta" data-testid="work-hub-line">
        {hub.cost_micros.total !== null || hub.tokens !== null
          ? `The Hub's own calls (titles, summaries): ${money(hub.cost_micros.total, 1)}${credits(hub) ? ` · ${credits(hub)}` : ''}, outside the rows above.`
          : 'The Hub has made no calls of its own.'}
      </p>
    </section>
  )
}

/** The Work section at the top of the Activity tab. */
export function ProjectWork() {
  const [grouping, setGrouping] = useState<Grouping>('spec')
  const [since, setSince] = useState('')
  // A day, as the Hub reckons days (UTC, like the ledger's spend by day): the start of that day.
  const { data, isLoading, isError } = useProjectStats(since ? `${since}T00:00:00Z` : null)
  if (isLoading) return <LoadingThread label="Loading work" />
  if (isError || !data) {
    return (
      <p className="aw-callout tone-red" data-testid="work-error">
        The Hub did not answer for this project’s work. A Hub older than this view has no tally to give; otherwise try again in a moment.
      </p>
    )
  }
  return <WorkView tally={data} grouping={grouping} onGrouping={setGrouping} since={since} onSince={setSince} />
}
