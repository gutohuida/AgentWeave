import { OverviewDashboard, type OverviewTarget } from '@/components/overview/OverviewDashboard'
import { toast } from '@/lib/toast'
import { NEXT_FIXTURES } from '../overviewNextMock'
import type { ScreenProps } from '../routes'

const minutesAgo = (now: Date, m: number) => new Date(now.getTime() - m * 60_000).toISOString()

/** The dashboard Overview, fed hand-written fixtures. The state rides in the route (`?state=quiet`). */
export default function OverviewNext({ route, go, now }: ScreenProps) {
  const state = route.kind === 'overview-next' ? route.state : 'busy'
  const f = NEXT_FIXTURES[state]
  const say = (where: string) => () => toast({ title: `Would open ${where}` })

  const navigate = (target: OverviewTarget) => {
    switch (target) {
      case 'needs':
      case 'builds':
        return go({ kind: 'tab', tab: 'tasks' })
      case 'running':
      case 'finished':
      case 'spend':
        return go({ kind: 'tab', tab: 'activity' })
      case 'main':
        return go({ kind: 'settings', section: 'checks' })
      case 'chapters':
        return go({ kind: 'thread' })
      case 'profiles':
        return go({ kind: 'tab', tab: 'profiles' })
      case 'dashboards':
        return go({ kind: 'tab', tab: 'dashboards' })
    }
  }

  return (
    <OverviewDashboard
      projectName="Terra"
      needs={f.needs.map(({ ago, to, ...n }) => ({ ...n, at: minutesAgo(now, ago), onOpen: say(to) }))}
      running={f.running.map(({ ago, to, ...a }) => ({ ...a, at: minutesAgo(now, ago), onOpen: say(to) }))}
      finished={f.finished.map(({ ago, to, ...a }) => ({ ...a, at: minutesAgo(now, ago), onOpen: say(to) }))}
      finishedToday={f.finishedToday}
      spend={f.spend}
      main={f.main}
      builds={f.builds.map(({ to, ...b }) => ({ ...b, onOpen: say(to) }))}
      onNavigate={navigate}
      now={now}
    />
  )
}