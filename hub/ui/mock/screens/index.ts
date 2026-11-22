import * as React from 'react'
import type { MockRoute, ScreenProps } from '../routes'

type ScreenComponent = React.ComponentType<ScreenProps>

const Gallery = React.lazy(() => import('./Gallery'))
const TaskRedesign = React.lazy(() => import('./TaskRedesign'))
const Overview = React.lazy(() => import('./Overview'))
const Tasks = React.lazy(() => import('./Tasks'))
const Spec = React.lazy(() => import('./Spec'))
const Vault = React.lazy(() => import('./Vault'))
const Dashboards = React.lazy(() => import('./Dashboards'))
const Jobs = React.lazy(() => import('./Jobs'))
const Activity = React.lazy(() => import('./Activity'))
const Conversation = React.lazy(() => import('./Conversation'))
const Settings = React.lazy(() => import('./Settings'))
const AgentSettings = React.lazy(() => import('./AgentSettings'))
const AppSettings = React.lazy(() => import('./AppSettings'))
const Thread = React.lazy(() => import('./Thread'))
const Traces = React.lazy(() => import('./Traces'))
const Checkpoints = React.lazy(() => import('./Checkpoints'))
const ConversationTrace = React.lazy(() => import('./ConversationTrace'))
const TaskThreads = React.lazy(() => import('./TaskThreads'))
const Roadmap = React.lazy(() => import('./Roadmap'))
const SpecHome = React.lazy(() => import('./SpecHome'))
const SpecThreadUi = React.lazy(() => import('./SpecThreadUi'))
const FirstRunPolish = React.lazy(() => import('./FirstRunPolish'))
const BuildView = React.lazy(() => import('./BuildView'))
const BuildSummaries = React.lazy(() => import('./BuildSummaries'))
const ProfilePools = React.lazy(() => import('./ProfilePools'))
const Profiles = React.lazy(() => import('./Profiles'))

export function screenFor(route: MockRoute): ScreenComponent {
  switch (route.kind) {
    case 'gallery':
      return Gallery
    case 'task-redesign':
      return TaskRedesign
    case 'task-threads':
      return TaskThreads
    case 'roadmap':
      return Roadmap
    case 'spec-home':
      return SpecHome
    case 'spec-thread-ui':
      return SpecThreadUi
    case 'first-run-polish':
      return FirstRunPolish
    case 'thread':
      return Thread
    case 'traces':
      return Traces
    case 'conversation-trace':
      return ConversationTrace
    case 'build':
      return BuildView
    case 'build-summaries':
      return BuildSummaries
    case 'profile-pools':
      return ProfilePools
    case 'conversation':
      return Conversation
    case 'settings':
      return Settings
    case 'agent-settings':
      return AgentSettings
    case 'app-settings':
      return AppSettings
    case 'tab':
      return { overview: Overview, tasks: Tasks, spec: Spec, vault: Vault, jobs: Jobs, activity: Activity, dashboards: Dashboards, thread: Thread, checkpoints: Checkpoints, profiles: Profiles }[route.tab]
  }
}

/** The screens the mock bar lists, in review order. */
export const SCREENS: Array<{ id: string; label: string; route: MockRoute }> = [
  { id: 'gallery', label: 'Primitives & motion', route: { kind: 'gallery' } },
  { id: 'overview', label: 'Overview', route: { kind: 'tab', tab: 'overview' } },
  { id: 'tasks', label: 'Tasks', route: { kind: 'tab', tab: 'tasks' } },
  { id: 'task-redesign', label: 'Tasks · Card and story redesign', route: { kind: 'task-redesign' } },
  { id: 'spec', label: 'Spec', route: { kind: 'tab', tab: 'spec' } },
  { id: 'task-threads', label: 'Spec · Task threads, three ways', route: { kind: 'task-threads' } },
  { id: 'spec-thread-ui', label: 'Spec · In a thread: phase badge and the created-document offer', route: { kind: 'spec-thread-ui' } },
  { id: 'first-run-polish', label: 'First run and the Overview read cleanly', route: { kind: 'first-run-polish' } },
  { id: 'roadmap', label: 'Spec · A roadmap’s own page', route: { kind: 'roadmap' } },
  { id: 'spec-home', label: 'Spec · Home, three ways to relate', route: { kind: 'spec-home' } },
  { id: 'profiles', label: 'Profiles · Every profile and its settings', route: { kind: 'tab', tab: 'profiles' } },
  { id: 'checkpoints', label: 'Checkpoints', route: { kind: 'tab', tab: 'checkpoints' } },
  { id: 'vault', label: 'Vault', route: { kind: 'tab', tab: 'vault' } },
  { id: 'jobs', label: 'Jobs', route: { kind: 'tab', tab: 'jobs' } },
  { id: 'activity', label: 'Activity', route: { kind: 'tab', tab: 'activity' } },
  { id: 'dashboards', label: 'Dashboards', route: { kind: 'tab', tab: 'dashboards' } },
  { id: 'thread', label: 'Thread', route: { kind: 'thread' } },
  { id: 'traces', label: 'Traces', route: { kind: 'traces' } },
  { id: 'build', label: 'Build · One build, every task and run', route: { kind: 'build', buildId: null } },
  { id: 'build-summaries', label: 'Build · Its summaries on the spec page and in the panel', route: { kind: 'build-summaries' } },
  { id: 'pool-build', label: 'Pools · Build chooses a model per task', route: { kind: 'profile-pools', view: 'build' } },
  { id: 'pool-chat', label: 'Pools · The chat picker', route: { kind: 'profile-pools', view: 'chat' } },
  { id: 'conversation-trace', label: 'Conversation · Its trace', route: { kind: 'conversation-trace', conversationId: null } },
  { id: 'conversation', label: 'Conversation', route: { kind: 'conversation', agent: 'Builder', conversationId: 'conv-e3aba2c5956a' } },
  { id: 'conversation-spec', label: 'Conversation · Spec panel', route: { kind: 'conversation', agent: 'Architect', conversationId: 'conv-9cdda4865e0b', panel: 'spec' } },
  { id: 'conversation-specs', label: 'Conversation · Open a spec', route: { kind: 'conversation', agent: 'Architect', conversationId: 'conv-9cdda4865e0b', panel: 'specs' } },
  { id: 'settings', label: 'Settings · Project', route: { kind: 'settings', section: 'general' } },
  { id: 'settings-collaboration', label: 'Settings · Collaboration', route: { kind: 'settings', section: 'collaboration' } },
  { id: 'settings-permissions', label: 'Settings · Permissions', route: { kind: 'settings', section: 'permissions' } },
  { id: 'settings-checks', label: 'Settings · Checks', route: { kind: 'settings', section: 'checks' } },
  { id: 'settings-landing', label: 'Settings · Landing', route: { kind: 'settings', section: 'landing' } },
  { id: 'settings-checkpoints', label: 'Settings · Checkpoints', route: { kind: 'settings', section: 'checkpoints' } },
  { id: 'settings-spec-steps', label: 'Settings · Spec steps', route: { kind: 'settings', section: 'spec-steps' } },
  { id: 'settings-traces', label: 'Settings · Traces', route: { kind: 'settings', section: 'traces' } },
  { id: 'settings-instructions', label: 'Settings · Instructions', route: { kind: 'settings', section: 'instructions' } },
  { id: 'settings-jobs', label: 'Settings · Jobs (moved here)', route: { kind: 'settings', section: 'jobs' } },
  { id: 'settings-logs', label: 'Settings · Logs (moved here)', route: { kind: 'settings', section: 'logs' } },
  { id: 'conversation-checkpoints', label: 'Conversation · Checkpoints tab', route: { kind: 'conversation', agent: 'Builder', conversationId: 'conv-e3aba2c5956a', panel: 'checkpoints' } },
  { id: 'conversation-trace-tab', label: 'Conversation · Trace tab', route: { kind: 'conversation', agent: 'Builder', conversationId: 'conv-e3aba2c5956a', panel: 'trace' } },
  { id: 'settings-manager', label: 'Settings · Manager', route: { kind: 'settings', section: 'manager' } },
  { id: 'settings-charters', label: 'Settings · Charters', route: { kind: 'settings', section: 'charters' } },
  { id: 'settings-runners', label: 'Settings · Runners', route: { kind: 'settings', section: 'runners' } },
  { id: 'settings-budgets', label: 'Settings · Budgets', route: { kind: 'settings', section: 'budgets' } },
  { id: 'app-settings', label: 'App settings · Sound and notifications', route: { kind: 'app-settings', section: 'notifications' } },
  { id: 'app-settings-appearance', label: 'App settings · Appearance', route: { kind: 'app-settings', section: 'appearance' } },
  { id: 'agent-agent', label: 'Agent · Agent', route: { kind: 'agent-settings', agent: 'Builder', section: 'agent' } },
  { id: 'agent-running', label: 'Agent · Running', route: { kind: 'agent-settings', agent: 'Builder', section: 'running' } },
  { id: 'agent-permissions', label: 'Agent · Permissions', route: { kind: 'agent-settings', agent: 'Builder', section: 'permissions' } },
  { id: 'agent-checkpoints', label: 'Agent · Checkpoints', route: { kind: 'agent-settings', agent: 'Builder', section: 'checkpoints' } },
  { id: 'agent-workspace', label: 'Agent · Workspace', route: { kind: 'agent-settings', agent: 'Builder', section: 'workspace' } },
]
