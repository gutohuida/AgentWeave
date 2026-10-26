import * as React from 'react'
import type { MockRoute, ScreenProps } from '../routes'

type ScreenComponent = React.ComponentType<ScreenProps>

const Gallery = React.lazy(() => import('./Gallery'))
const Overview = React.lazy(() => import('./Overview'))
const Tasks = React.lazy(() => import('./Tasks'))
const Spec = React.lazy(() => import('./Spec'))
const Vault = React.lazy(() => import('./Vault'))
const Jobs = React.lazy(() => import('./Jobs'))
const Activity = React.lazy(() => import('./Activity'))
const Conversation = React.lazy(() => import('./Conversation'))
const Settings = React.lazy(() => import('./Settings'))
const AgentSettings = React.lazy(() => import('./AgentSettings'))
const Thread = React.lazy(() => import('./Thread'))

export function screenFor(route: MockRoute): ScreenComponent {
  switch (route.kind) {
    case 'gallery':
      return Gallery
    case 'thread':
      return Thread
    case 'conversation':
      return Conversation
    case 'settings':
      return Settings
    case 'agent-settings':
      return AgentSettings
    case 'tab':
      return { overview: Overview, tasks: Tasks, spec: Spec, vault: Vault, jobs: Jobs, activity: Activity, thread: Thread }[route.tab]
  }
}

/** The screens the mock bar lists, in review order. */
export const SCREENS: Array<{ id: string; label: string; route: MockRoute }> = [
  { id: 'gallery', label: 'Primitives & motion', route: { kind: 'gallery' } },
  { id: 'overview', label: 'Overview', route: { kind: 'tab', tab: 'overview' } },
  { id: 'tasks', label: 'Tasks', route: { kind: 'tab', tab: 'tasks' } },
  { id: 'spec', label: 'Spec', route: { kind: 'tab', tab: 'spec' } },
  { id: 'vault', label: 'Vault', route: { kind: 'tab', tab: 'vault' } },
  { id: 'jobs', label: 'Jobs', route: { kind: 'tab', tab: 'jobs' } },
  { id: 'activity', label: 'Activity', route: { kind: 'tab', tab: 'activity' } },
  { id: 'thread', label: 'Thread', route: { kind: 'thread' } },
  { id: 'conversation', label: 'Conversation', route: { kind: 'conversation', agent: 'Builder', conversationId: 'conv-e3aba2c5956a' } },
  { id: 'conversation-spec', label: 'Conversation · Spec panel', route: { kind: 'conversation', agent: 'Architect', conversationId: 'conv-9cdda4865e0b', panel: 'spec' } },
  { id: 'settings', label: 'Settings · General', route: { kind: 'settings', section: 'general' } },
  { id: 'settings-manager', label: 'Settings · Manager', route: { kind: 'settings', section: 'manager' } },
  { id: 'settings-charters', label: 'Settings · Charters', route: { kind: 'settings', section: 'charters' } },
  { id: 'settings-runners', label: 'Settings · Runners', route: { kind: 'settings', section: 'runners' } },
  { id: 'settings-budgets', label: 'Settings · Budgets', route: { kind: 'settings', section: 'budgets' } },
  { id: 'agent-execution', label: 'Agent · Execution', route: { kind: 'agent-settings', agent: 'Builder', section: 'execution' } },
  { id: 'agent-access', label: 'Agent · Access', route: { kind: 'agent-settings', agent: 'Builder', section: 'access' } },
]
