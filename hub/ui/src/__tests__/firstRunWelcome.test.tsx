import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProjectSetupItem } from '@/api/projects'
import { FirstRunPath } from '@/components/overview/FirstRunPath'
import { ProjectSetupList } from '@/components/overview/ProjectSetupList'
import { QUICKSTART_URL } from '@/components/overview/setupItems'
import { useConfigStore } from '@/store/configStore'

// AW-128, merged: a new project's set-up card carries the first-run path, and once nothing is left
// to set up only a quiet quickstart link stays (one card, no second welcome).
let agents: Array<{ name: string }> = []
let agentsLoading = false
let hasNoWork: boolean | null = true
let items: ProjectSetupItem[] = []
let dismissed: ProjectSetupItem[] = []

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: agentsLoading ? undefined : agents, isLoading: agentsLoading, error: null }) }))
vi.mock('@/api/firstRun', () => ({ useProjectHasNoWork: () => hasNoWork }))
vi.mock('@/api/projects', () => ({
  useProjects: () => ({ data: [{ id: 'proj-1', setup: { items, dismissed } }] }),
  useSetupDismissal: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/components/overview/SetupProfilesDialog', () => ({ SetupProfilesDialog: () => null }))

const item = (key: ProjectSetupItem['key']): ProjectSetupItem => ({
  id: key,
  key,
  dismissable: true,
  agent: null,
  provider: null,
  reason: null,
  detail: null,
})

beforeEach(() => {
  agents = []
  agentsLoading = false
  hasNoWork = true
  items = [item('profiles'), item('specification')]
  dismissed = []
  useConfigStore.setState({ selectedProjectId: 'proj-1' })
})
afterEach(cleanup)

const current = () => within(screen.getByTestId('first-run-path')).getByRole('listitem', { current: 'step' })

describe('the first-run path', () => {
  it('marks the step the project is at', () => {
    render(<FirstRunPath current={1} />)
    expect(current()).toHaveTextContent('Ask for a change')
    expect(screen.getAllByRole('listitem')).toHaveLength(5)
  })
})

describe('the set-up card on Overview', () => {
  it('with no profile lists both items and the path at its first step, in one card', () => {
    render(<ProjectSetupList place="overview" />)
    expect(screen.getAllByTestId('setup-list')).toHaveLength(1)
    expect(screen.getByTestId('setup-item-profiles')).toBeInTheDocument()
    expect(screen.getByTestId('setup-item-specification')).toBeInTheDocument()
    expect(current()).toHaveTextContent('Add a profile')
    expect(screen.queryByTestId('first-run-panel')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /quickstart/i })).not.toBeInTheDocument()
  })

  it('with profiles added lists the one item left and the path at its second step', () => {
    agents = [{ name: 'planner' }]
    items = [item('specification')]
    render(<ProjectSetupList place="overview" />)
    expect(screen.queryByTestId('setup-item-profiles')).not.toBeInTheDocument()
    expect(current()).toHaveTextContent('Ask for a change')
  })

  it('once every item is done or dismissed leaves only the quickstart link', () => {
    items = []
    dismissed = [item('profiles')]
    render(<ProjectSetupList place="overview" />)
    expect(screen.queryByTestId('setup-list')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /quickstart/i })).toHaveAttribute('href', QUICKSTART_URL)
  })

  it('shows nothing once the project has a profile and work, and has nothing to set up', () => {
    agents = [{ name: 'planner' }]
    hasNoWork = false
    items = []
    render(<ProjectSetupList place="overview" />)
    expect(screen.queryByRole('link', { name: /quickstart/i })).not.toBeInTheDocument()
  })

  it('has no path once there is work, though an item is left', () => {
    agents = [{ name: 'planner' }]
    hasNoWork = false
    items = [item('repository')]
    render(<ProjectSetupList place="overview" />)
    expect(screen.getByTestId('setup-item-repository')).toBeInTheDocument()
    expect(screen.queryByTestId('first-run-path')).not.toBeInTheDocument()
  })

  it('waits for the roster and the work to be read before it draws the path', () => {
    agentsLoading = true
    render(<ProjectSetupList place="overview" />)
    expect(screen.queryByTestId('first-run-path')).not.toBeInTheDocument()
    cleanup()
    agentsLoading = false
    agents = [{ name: 'planner' }]
    hasNoWork = null
    render(<ProjectSetupList place="overview" />)
    expect(screen.queryByTestId('first-run-path')).not.toBeInTheDocument()
  })

  it('does not carry the path into Project settings', () => {
    render(<ProjectSetupList place="settings" />)
    expect(screen.getByTestId('setup-list')).toBeInTheDocument()
    expect(screen.queryByTestId('first-run-path')).not.toBeInTheDocument()
  })
})
