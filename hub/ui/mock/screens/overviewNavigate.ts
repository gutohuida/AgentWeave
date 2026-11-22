import type { OverviewTarget } from '@/components/overview/OverviewDashboard'
import type { MockRoute } from '../routes'

/** Where each drill-down of an Overview variant goes in the mock: the page the app would open. */
export function overviewNavigate(go: (route: MockRoute) => void) {
  return (target: OverviewTarget) => {
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
}