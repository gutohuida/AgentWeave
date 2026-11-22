import type { SidePanelTab } from './screens/SidePanel'
import type { AppSettingsSection, ProjectTab } from '@/lib/navigation'
import type { OverviewNextState } from './overviewNextMock'

/** Where the mock is. Mirrors the app's own destinations (lib/navigation.ts) closely enough that a
 *  screen's navigation calls map one to one when it is wired in. */
/** The app's tabs plus the three leaner-navigation retired, which the mock still shows as the
 *  "before" side of its comparison. */
export type MockTab = ProjectTab | 'checkpoints' | 'jobs' | 'activity'

export type MockRoute =
  /** `profile` is the Profiles tab's selected profile (it also rides in the hash's query). */
  | { kind: 'tab'; tab: MockTab; profile?: string }
  | { kind: 'conversation'; agent: string; conversationId: string | null; panel?: 'spec' | 'specs' | SidePanelTab }
  | { kind: 'settings'; section: SettingsSection }
  | { kind: 'agent-settings'; agent: string; section: AgentSettingsSection }
  | { kind: 'app-settings'; section: AppSettingsSection }
  | { kind: 'gallery' }
  /** The task card and story redesign (`task-card-and-story-redesign`). */
  | { kind: 'task-redesign' }
  /** The spec page's task threads, three layouts to choose from (operator, 2026-11-16). */
  | { kind: 'task-threads' }
  /** A roadmap's own page, with the slice-3 choices open (operator, 2026-11-16). */
  | { kind: 'roadmap' }
  /** The Spec home, with three ways of showing how documents relate (operator, 2026-11-17). */
  | { kind: 'spec-home' }
  | { kind: 'thread' }
  /** The Overview redrawn as a dashboard (operator, 2026-11-22); ?state=quiet|trouble shows the other states. */
  | { kind: 'overview-next'; state: OverviewNextState }
  /** The Overview as a morning briefing, and by team lane: two more designs to compare (operator, 2026-11-22). */
  | { kind: 'overview-briefing'; state: OverviewNextState }
  | { kind: 'overview-lanes'; state: OverviewNextState }
  /** How a thread shows the spec it is working on: the header's phase badge with its step, and three
   *  ways to offer a document an agent created in the thread (operator, 2026-11-22). */
  | { kind: 'spec-thread-ui' }
  /** First run and the Overview read cleanly: six small polish items, each today next to proposed
   *  (operator, 2026-11-22). */
  | { kind: 'first-run-polish' }
  /** The traces view: a fourth view inside Activity (operator, 2026-11-02). */
  | { kind: 'traces' }
  /** A whole conversation's trace (spec a-trace-of-a-whole-conversation). */
  | { kind: 'conversation-trace'; conversationId: string | null }
  /** One build's view (spec a-build-view-showing-every-task-and-run-of-a-build). Its task, run,
   *  filter and mock state ride in the hash's query (`?task=…&run=…&filter=…&state=…`). */
  | { kind: 'build'; buildId: string | null }
  /** The build view's two compact summaries in their real containers, side by side. */
  | { kind: 'build-summaries' }
  /** A profile's pool (spec a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool):
   *  the Build dialog's per-task model, and the composer's pool picker. */
  | { kind: 'profile-pools'; view: 'build' | 'chat' }

/** Project settings, one place under one name. Replaces Environment / Configuration / Settings. */
export type SettingsSection =
  | 'general'
  | 'collaboration'
  | 'permissions'
  | 'checks'
  | 'landing'
  | 'checkpoints'
  | 'spec-steps'
  | 'traces'
  | 'jobs'
  | 'logs'
  | 'agents-defaults' | 'runners' | 'manager' | 'charters' | 'instructions' | 'budgets' | 'worktrees' | 'diagnostics'
export type AgentSettingsSection = 'agent' | 'running' | 'permissions' | 'checkpoints' | 'workspace'

export interface ScreenProps {
  route: MockRoute
  go: (route: MockRoute) => void
  /** The fixtures were recorded on Oct 16–17; the mock's clock sits just after them. */
  now: Date
}

/** Which "today" screenshot the Before toggle shows for a route. */
export function beforeKey(route: MockRoute): string | null {
  switch (route.kind) {
    case 'tab':
      return route.tab
    case 'conversation':
      return 'conversation'
    case 'settings':
      return (
        { general: 'settings', manager: 'manager', charters: 'charters', budgets: 'budgets' } as Record<string, string>
      )[route.section] ?? null
    case 'agent-settings':
      return route.section === 'permissions' ? 'agent-access' : route.section === 'running' ? 'agent-execution' : null
    default:
      return null
  }
}
