import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { loadAllScreens } from '@/lib/lazyScreens'
import { NOTIFY_PREFS_KEY } from '@/lib/notify/prefs'
import { useConfigStore } from '@/store/configStore'

/** App settings: the operator's own settings (sound and notifications, appearance, the Hub
 *  connection), reachable from the rail on every screen, even with no project open (slice I,
 *  `app-settings-have-a-home`). The whole app is mounted, as `App-mount.test.tsx` does. */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))
vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response))

const PROJECT = {
  id: 'proj-test', name: 'AgentWeave', working_directory: 'C:/work/AgentWeave',
  path_display: 'C:/work/AgentWeave', directory_state: 'available', last_opened_at: null,
  last_seen_at: null, hop_budget: 20, turn_delivery_cap: 20, agent_budget: 10,
  token_budget: null, allow_agent_jobs: true,
  agents: [{ id: 'agent-claude', name: 'claude', color_index: 2, status: 'idle', last_seen: null }],
}
let projects: Array<typeof PROJECT> = [PROJECT]

vi.mock('@/api/projects', () => ({
  useProjects: () => ({ data: projects, isLoading: false }),
  fetchProjectSummaries: vi.fn(async () => projects),
  useOpenProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useCreateProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useUpdateProjectSettings: () => ({ mutate: vi.fn(), error: null, isPending: false }),
  useRelocateProject: () => ({ mutate: vi.fn(), error: null, isPending: false }),
}))
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({
    data: [{ name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2 }],
    isLoading: false,
  }),
}))
vi.mock('@/components/overview/OverviewScreen', () => ({ OverviewScreen: () => <div data-testid="page-overview" /> }))
vi.mock('@/components/tasks/TasksScreen', () => ({ TasksScreen: () => <div data-testid="page-tasks" /> }))
vi.mock('@/components/layout/SetupModal', () => ({
  SetupModal: ({ open }: { open: boolean }) => (open ? <div role="dialog" aria-label="Hub connection setup" /> : null),
}))
// The sections of Project settings and agent settings read many project hooks; only their frame
// (the section list and its links) is under test here.
vi.mock('@/components/settings/sections/GeneralSection', () => ({ GeneralSection: () => <div data-testid="general-section" /> }))
vi.mock('@/components/environment/SpecStepsSection', () => ({ SpecStepsSection: () => null }))
vi.mock('@/components/environment/TracesSection', () => ({ TracesSection: () => null }))
vi.mock('@/components/agents/settings/AgentSettingsSections', () => ({
  AgentIdentitySettings: () => <div data-testid="identity-section" />,
  AgentExecutionSettings: () => null,
  AgentAccessSettings: () => null,
}))

import App from '@/App'

function mount(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeAll(() => loadAllScreens(), 90000)

beforeEach(() => {
  cleanup()
  projects = [PROJECT]
  window.localStorage.clear()
  window.history.pushState(null, '', '/')
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
    mode: 'light',
  })
})

/** The rail's own control: Project and agent settings carry a link of the same name. */
const railSettings = () => within(screen.getByTestId('sidebar')).getByRole('button', { name: 'App settings' })

function expectAppSettingsOpen() {
  const nav = screen.getByRole('navigation', { name: 'App settings' })
  for (const label of ['Sound and notifications', 'Appearance', 'Hub connection']) {
    expect(within(nav).getByRole('button', { name: new RegExp(label) })).toBeInTheDocument()
  }
  // It opens on the section the operator most often wants.
  expect(screen.getByTestId('notify-sound')).toBeInTheDocument()
}

describe('App settings are reached from the rail', () => {
  it('opens with no project open', () => {
    projects = []
    useConfigStore.setState({ selectedProjectId: null })
    mount(<App />)
    fireEvent.click(railSettings())
    expectAppSettingsOpen()
  })

  it.each(['overview', 'tasks', 'environment'])('opens from the %s tab of a project and keeps the project', (tab) => {
    window.history.pushState(null, '', `/?project=proj-test&tab=${tab}`)
    mount(<App />)
    fireEvent.click(railSettings())
    expectAppSettingsOpen()
    expect(window.location.search).toContain('project=proj-test')
    expect(screen.getByRole('button', { name: /Back to AgentWeave/ })).toBeInTheDocument()
  })

  it('opens from the compact rail too', () => {
    window.localStorage.setItem('aw.sidebarCollapsed', 'true')
    mount(<App />)
    fireEvent.click(railSettings())
    expectAppSettingsOpen()
  })

  it('survives a reload: the address names it', () => {
    window.history.pushState(null, '', '/?project=proj-test&appSettings=appearance')
    mount(<App />)
    expect(screen.getByRole('navigation', { name: 'App settings' })).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: 'Appearance' })).toBeInTheDocument()
  })
})

describe('sound and notifications are app settings', () => {
  it('render and save without any project, and write the window’s own preference', () => {
    projects = []
    useConfigStore.setState({ selectedProjectId: null })
    mount(<App />)
    fireEvent.click(railSettings())

    for (const kind of ['ask', 'fail', 'reply', 'done']) expect(screen.getByTestId(`notify-kind-${kind}`)).toBeInTheDocument()
    expect(screen.getByTestId('notify-volume')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('switch', { name: 'Work finished' }))
    const stored = JSON.parse(window.localStorage.getItem(NOTIFY_PREFS_KEY) ?? '{}')
    expect(stored.kinds.done).toBe(true)
  })
})

describe('appearance and the Hub connection', () => {
  it('switches light and dark from Appearance', () => {
    window.history.pushState(null, '', '/?project=proj-test&appSettings=appearance')
    mount(<App />)
    fireEvent.click(screen.getByRole('radio', { name: 'Dark' }))
    expect(useConfigStore.getState().mode).toBe('dark')
    expect(document.documentElement.dataset.mode).toBe('dark')
  })

  it('shows the Hub address and opens the connection dialog from Change', () => {
    window.history.pushState(null, '', '/?project=proj-test&appSettings=connection')
    mount(<App />)
    expect(screen.getByText('http://hub.test')).toBeInTheDocument()
    expect(screen.queryByText(/aw_live_TESTKEY/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))
    expect(screen.getByRole('dialog', { name: 'Hub connection setup' })).toBeInTheDocument()
  })
})

describe('each settings page names whose settings it holds, and links to App settings', () => {
  it('App settings says they are the operator’s, for every project', () => {
    window.history.pushState(null, '', '/?project=proj-test&appSettings=notifications')
    mount(<App />)
    const nav = screen.getByRole('navigation', { name: 'App settings' })
    expect(nav).toHaveTextContent(/every project|your/i)
  })

  it('Project settings is this project’s, and its section list ends with a link that goes there', () => {
    window.history.pushState(null, '', '/?project=proj-test&tab=environment&section=settings')
    mount(<App />)
    const nav = screen.getByRole('navigation', { name: 'Project settings' })
    expect(nav).toHaveTextContent('Project settings')
    expect(nav).toHaveTextContent('AgentWeave')
    const link = within(nav).getByRole('button', { name: /App settings/ })
    fireEvent.click(link)
    expectAppSettingsOpen()
  })

  it('an agent’s settings is that agent’s, and its section list ends with a link that goes there', () => {
    window.history.pushState(null, '', '/?project=proj-test&agent=claude&settings=identity')
    mount(<App />)
    const nav = screen.getByRole('navigation', { name: 'claude settings' })
    const link = within(nav).getByRole('button', { name: /App settings/ })
    fireEvent.click(link)
    expectAppSettingsOpen()
  })
})
