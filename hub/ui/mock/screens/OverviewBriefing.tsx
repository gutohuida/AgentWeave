import { OverviewBriefing } from '@/components/overview/OverviewBriefing'
import { toast } from '@/lib/toast'
import { LAST_SEEN_AGO } from '../overviewVariantsMock'
import { NEXT_FIXTURES } from '../overviewNextMock'
import type { ScreenProps } from '../routes'
import { overviewNavigate } from './overviewNavigate'

const minutesAgo = (now: Date, m: number) => new Date(now.getTime() - m * 60_000).toISOString()

/** The Briefing Overview, fed the same project as the dashboard variant. The state rides in the route (`?state=quiet`). */
export default function OverviewBriefingScreen({ route, go, now }: ScreenProps) {
  const state = route.kind === 'overview-briefing' ? route.state : 'busy'
  const f = NEXT_FIXTURES[state]
  const seen = LAST_SEEN_AGO[state]
  const say = (where: string) => () => toast({ title: `Would open ${where}` })
  return (
    <OverviewBriefing
      projectName="Terra"
      lastSeenAt={seen == null ? null : minutesAgo(now, seen)}
      needs={f.needs.map(({ ago, to, ...n }) => ({ ...n, at: minutesAgo(now, ago), onOpen: say(to) }))}
      running={f.running.map(({ ago, to, ...a }) => ({ ...a, at: minutesAgo(now, ago), onOpen: say(to) }))}
      finished={f.finished.map(({ ago, to, ...a }) => ({ ...a, at: minutesAgo(now, ago), onOpen: say(to) }))}
      finishedToday={f.finishedToday}
      spend={f.spend}
      main={f.main}
      builds={f.builds.map(({ to, ...b }) => ({ ...b, onOpen: say(to) }))}
      onNavigate={overviewNavigate(go)}
      now={now}
    />
  )
}