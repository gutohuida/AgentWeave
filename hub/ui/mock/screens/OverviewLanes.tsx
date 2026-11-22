import { OverviewLanes } from '@/components/overview/OverviewLanes'
import { toast } from '@/lib/toast'
import { LANE_FIXTURES } from '../overviewVariantsMock'
import { NEXT_FIXTURES } from '../overviewNextMock'
import type { ScreenProps } from '../routes'
import { overviewNavigate } from './overviewNavigate'

const minutesAgo = (now: Date, m: number) => new Date(now.getTime() - m * 60_000).toISOString()

/** The Team-lanes Overview, fed the same project as the dashboard variant. The state rides in the route (`?state=quiet`). */
export default function OverviewLanesScreen({ route, go, now }: ScreenProps) {
  const state = route.kind === 'overview-lanes' ? route.state : 'busy'
  const f = NEXT_FIXTURES[state]
  const say = (where: string) => () => toast({ title: `Would open ${where}` })
  return (
    <OverviewLanes
      projectName="Terra"
      lanes={LANE_FIXTURES[state].map((l) => ({
        id: l.id,
        name: l.name,
        colorIndex: l.colorIndex,
        status: l.status,
        doing: l.doing ? { what: l.doing.what, since: minutesAgo(now, l.doing.ago) } : null,
        last: l.last ? { what: l.last.what, outcome: l.last.outcome, at: minutesAgo(now, l.last.ago) } : null,
        asks: l.asks,
        spendToday: l.spendToday,
        onOpen: say(`${l.name}'s current thread`),
        onOpenAsks: say(`what ${l.name} is waiting on you for`),
      }))}
      needsCount={f.needs.length}
      runningCount={f.running.length}
      finishedToday={f.finishedToday}
      spend={f.spend}
      main={f.main}
      builds={f.builds.map(({ to, ...b }) => ({ ...b, onOpen: say(to) }))}
      onNavigate={overviewNavigate(go)}
      now={now}
    />
  )
}