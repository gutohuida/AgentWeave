import * as React from 'react'
import type { AgentConversation } from '@/api/agentChat'
import type { ProjectAgentSummary, ProjectSummary } from '@/api/projects'
import { ThreadsAndBuilds } from '@/components/layout/ThreadsAndBuilds'
import type { ListState, SidebarBuild } from '@/components/layout/threadsAndBuildsModel'
import { PROJECT_ID } from './fixtures'

/** The sidebar's threads and builds (spec profiles-threads-and-builds-everywhere).
 *
 *  No recording has `operator_threads` or `needs_operator` yet: neither route exists. So the list
 *  is mock state throughout, modelled on this repository's own roster, threads and builds, and
 *  shaped exactly as `AgentConversation` and the D2 build row, so the app's data plugs in. */

export type SidebarMockState = 'mixed' | 'quiet' | 'empty' | 'many40' | 'many300' | 'loading' | 'error'

export const SIDEBAR_MOCK_STATES: Array<{ value: SidebarMockState; label: string }> = [
  { value: 'mixed', label: 'Sidebar: builds running and needing you' },
  { value: 'quiet', label: 'Sidebar: no builds, threads only' },
  { value: 'empty', label: 'Sidebar: new project, nothing yet' },
  { value: 'many40', label: 'Sidebar: 40 threads' },
  { value: 'many300', label: 'Sidebar: 300 threads' },
  { value: 'loading', label: 'Sidebar: loading' },
  { value: 'error', label: 'Sidebar: could not load' },
]

const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
let state: SidebarMockState = (SIDEBAR_MOCK_STATES.some((s) => s.value === query.get('sidebar')) ? query.get('sidebar') : 'mixed') as SidebarMockState
let dismissed = new Set<string>()
let showArchived = false
const listeners = new Set<() => void>()
let snapshot = { state, dismissed, showArchived }
function emit() {
  snapshot = { state, dismissed, showArchived }
  listeners.forEach((l) => l())
}

export function setSidebarMockState(next: SidebarMockState) {
  state = next
  dismissed = new Set()
  emit()
}

export function useSidebarMock() {
  return React.useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => snapshot,
  )
}

// mock state: this repository's profiles, coloured as the Hub assigns them.
const PROFILES: ProjectAgentSummary[] = [
  { id: 'agent-arch', name: 'Architect', color_index: 0, status: 'running', last_seen: null },
  { id: 'agent-dev', name: 'Developer', color_index: 1, status: 'idle', last_seen: null },
  { id: 'agent-qa', name: 'QA', color_index: 2, status: 'idle', last_seen: null },
  { id: 'agent-codex', name: 'CodexSol', color_index: 3, status: 'idle', last_seen: null },
  { id: 'agent-mender', name: 'mender', color_index: 4, status: 'idle', last_seen: null },
]

// Relative to the real clock, not MOCK_NOW: the rail's ages are read against Date.now().
function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString()
}

function thread(
  id: string,
  agent: string,
  title: string,
  minutes: number,
  extra: Partial<AgentConversation> = {},
): AgentConversation {
  return {
    id,
    agent,
    provider_session_id: null,
    lifecycle: 'open',
    title,
    title_set_by_operator: false,
    origin: 'operator',
    loop: null,
    context_usage: null,
    attention: 'idle',
    checkpoint_warning: null,
    created_at: minutesAgo(minutes + 90),
    updated_at: minutesAgo(minutes),
    ...extra,
  } as AgentConversation
}

// mock state: the operator's threads, newest activity first, as `operator_threads=true` returns
// them. One is running, one waits on the operator, one is a job firing the operator replied in
// (FR-2), and one is a cut-over successor with no operator message of its own yet (FR-1).
const THREADS: AgentConversation[] = [
  thread('conv-8a8be703ebe6', 'Architect', 'Spec: profiles, threads and builds', 1, { attention: 'running', origin: 'spec' }),
  thread('conv-1f0c22aa9b10', 'QA', 'Why did the landing hold ESEPL-6?', 14, { attention: 'waiting' }),
  thread('conv-3be71c0e4d55', 'Developer', 'Fix the lag probe on Windows', 52),
  thread('conv-90d1aa7e2c01', 'Architect', 'Spec: the build dialog redesigned (continued)', 130, { origin: 'spec' }),
  thread('conv-6c4e0f81b7a2', 'mender', 'Morning stall sweep', 185, { origin: 'job', loop: { id: 'loop-mend', label: 'Stall sweep' } as AgentConversation['loop'] }),
  thread('conv-a7b2d3e9f004', 'CodexSol', 'Try gpt-6.1-sol on the vault importer', 60 * 5),
  thread('conv-55e1c0d2aa31', 'Architect', 'Roadmap: role profiles', 60 * 21, { origin: 'spec' }),
  thread('conv-2d9f7c41e6b8', 'Developer', 'Black formatting drift in hub/tests', 60 * 26),
  thread('conv-c18e0a6b7f22', 'QA', 'Drive the knowledge vault end to end', 60 * 48),
  thread('conv-4a0e5f3c9d17', 'Architect', 'Explore: dashboards an agent builds', 60 * 72, { origin: 'spec' }),
]

// mock state: a long-running project, for the 40 and 300 rows the vault note asks to be shown.
const TOPICS = ['Fix', 'Spec:', 'Explore:', 'Drive', 'Why did', 'Review', 'Try', 'Roadmap:']
const SUBJECTS = ['the landing queue', 'vault import', 'build retrospectives', 'the composer', 'pool pricing', 'trace drawer', 'checkpoint cutover', 'the Jobs screen', 'dashboards', 'GitLab landing']
function manyThreads(n: number): AgentConversation[] {
  const extra = Array.from({ length: Math.max(0, n - THREADS.length) }, (_, i) =>
    thread(
      `conv-many${String(i).padStart(7, '0')}`,
      PROFILES[i % PROFILES.length]!.name,
      `${TOPICS[i % TOPICS.length]} ${SUBJECTS[(i * 7) % SUBJECTS.length]} (${i + 1})`,
      60 * 80 + i * 97,
    ),
  )
  return [...THREADS, ...extra]
}

const ARCHIVED: AgentConversation[] = [
  thread('conv-0aa1b2c3d4e5', 'Developer', 'Old CLI session cleanup', 60 * 24 * 9, { lifecycle: 'archived' }),
  thread('conv-0bb1b2c3d4e6', 'QA', 'Trial Hub smoke test', 60 * 24 * 12, { lifecycle: 'archived' }),
]

// mock state: what `GET /builds` with D2's `needs_operator` would list for the sidebar: running,
// or needing the operator and not dismissed. A finished build with nothing open is not here.
export const BUILDS: SidebarBuild[] = [
  { id: 'build-pf01', document_title: 'Profiles, threads and builds everywhere', state: 'running', tasks_total: 9, tasks_done: 3, needs_operator: null },
  {
    id: 'build-rt02',
    document_title: 'Pull the thread: project history page',
    state: 'running',
    tasks_total: 5,
    tasks_done: 2,
    needs_operator: { kind: 'stalled', text: 'RTPH-4 stalled: its landing conflicts with master in hub/ui/src/App.tsx.' },
  },
  {
    id: 'build-bd03',
    document_title: 'The build dialog redesigned',
    state: 'stopped',
    tasks_total: 6,
    tasks_done: 4,
    needs_operator: { kind: 'stopped', text: 'Stopped by you with 2 tasks not approved.' },
  },
  {
    id: 'build-gl04',
    document_title: 'Builds land on GitLab merge requests',
    state: 'finished',
    tasks_total: 4,
    tasks_done: 3,
    needs_operator: { kind: 'question', text: 'DeveloperOpus asks: which GitLab token scope should the landing use?' },
  },
]

/** The project body the mock's sidebar renders under each project. */
export function useSidebarProjectBody(go: {
  openThread: (profile: string, conversationId: string) => void
  newThread: () => void
  openBuild: (buildId: string) => void
  activeConversation: string | null
  activeBuild: string | null
}): (project: ProjectSummary, activeProject: boolean) => React.ReactNode {
  const mock = useSidebarMock()
  return (project, activeProject) => {
    const main = project.id === PROJECT_ID
    const listState: ListState = main && mock.state === 'loading' ? 'loading' : main && mock.state === 'error' ? 'error' : 'ready'
    const threads =
      !main || mock.state === 'empty' || listState !== 'ready'
        ? []
        : mock.state === 'many40'
          ? manyThreads(40)
          : mock.state === 'many300'
            ? manyThreads(300)
            : THREADS
    const withBuilds = mock.state === 'mixed' || mock.state === 'many40' || mock.state === 'many300'
    const builds = !main || !withBuilds ? [] : BUILDS.filter((b) => !mock.dismissed.has(b.id))
    return (
      <ThreadsAndBuilds
        projectId={project.id}
        profiles={main ? PROFILES : project.agents}
        threads={threads}
        threadsState={listState}
        buildsState={listState}
        archivedCount={main && mock.state !== 'empty' && listState === 'ready' ? ARCHIVED.length : 0}
        archivedThreads={main && mock.showArchived ? ARCHIVED : null}
        builds={builds}
        activeProject={activeProject}
        activeConversation={go.activeConversation}
        activeBuild={go.activeBuild}
        onOpenThread={(_, profile, id) => go.openThread(profile, id)}
        onNewThread={() => go.newThread()}
        onOpenBuild={(_, id) => go.openBuild(id)}
        onDismissBuild={(_, id) => {
          dismissed = new Set([...dismissed, id])
          emit()
        }}
        onShowArchived={(_, show) => {
          showArchived = show
          emit()
        }}
        onRetry={() => setSidebarMockState('mixed')}
      />
    )
  }
}

/** The collapsed rail's mark: the titles of the builds that need the operator, per project. */
export function useBuildsNeedingYou(): (projectId: string) => string[] {
  const mock = useSidebarMock()
  return (projectId) =>
    projectId === PROJECT_ID && (mock.state === 'mixed' || mock.state === 'many40' || mock.state === 'many300')
      ? BUILDS.filter((b) => b.needs_operator && !mock.dismissed.has(b.id)).map((b) => b.document_title)
      : []
}
