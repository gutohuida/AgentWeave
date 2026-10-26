import type { ProjectTab } from '@/lib/navigation'

/** Where the mock is. Mirrors the app's own destinations (lib/navigation.ts) closely enough that a
 *  screen's navigation calls map one to one when it is wired in. */
export type MockRoute =
  | { kind: 'tab'; tab: ProjectTab }
  | { kind: 'conversation'; agent: string; conversationId: string | null; panel?: 'spec' }
  | { kind: 'settings'; section: SettingsSection }
  | { kind: 'agent-settings'; agent: string; section: AgentSettingsSection }
  | { kind: 'gallery' }
  | { kind: 'thread' }

/** Project settings, one place under one name. Replaces Environment / Configuration / Settings. */
export type SettingsSection = 'general' | 'agents-defaults' | 'manager' | 'runners' | 'charters' | 'instructions' | 'budgets' | 'worktrees' | 'diagnostics'
export type AgentSettingsSection = 'identity' | 'execution' | 'charter' | 'interaction' | 'context' | 'access' | 'workspace'

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
        { general: 'settings', manager: 'manager', charters: 'charters', budgets: 'budgets', runners: 'runners' } as Record<string, string>
      )[route.section] ?? null
    case 'agent-settings':
      return route.section === 'access' ? 'agent-access' : route.section === 'execution' ? 'agent-execution' : null
    default:
      return null
  }
}
