import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FirstRunPanel, QUICKSTART_URL } from '@/components/overview/FirstRunPanel'
import { ProjectFirstRun } from '@/components/overview/ProjectFirstRun'
import { useConfigStore } from '@/store/configStore'

// AW-128: a new project opens on a welcome that says what to do first.
let agents: Array<{ name: string }> = []
let agentsLoading = false
let hasNoWork: boolean | null = true
const goTo = vi.fn()

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: agentsLoading ? undefined : agents, isLoading: agentsLoading, error: null }) }))
vi.mock('@/api/firstRun', () => ({ useProjectHasNoWork: () => hasNoWork }))
vi.mock('@/lib/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/navigation')>()),
  goTo: (destination: unknown) => goTo(destination),
}))

beforeEach(() => {
  agents = []
  agentsLoading = false
  hasNoWork = true
  goTo.mockReset()
  useConfigStore.setState({ selectedProjectId: 'proj-1' })
})
afterEach(cleanup)

describe('the first-run panel', () => {
  it('with no agent offers Add an agent and the quickstart', () => {
    const onAddAgent = vi.fn()
    render(<FirstRunPanel agent={null} onAddAgent={onAddAgent} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add an agent' }))
    expect(onAddAgent).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('link', { name: /quickstart/i })).toHaveAttribute('href', QUICKSTART_URL)
  })

  it('with an agent offers to ask that agent for a change', () => {
    const onAskForChange = vi.fn()
    render(<FirstRunPanel agent="planner" onAskForChange={onAskForChange} />)
    expect(screen.queryByRole('button', { name: 'Add an agent' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ask planner for a change' }))
    expect(onAskForChange).toHaveBeenCalledWith('planner')
  })
})

describe('the first-run panel in a project', () => {
  it('shows for a project with no agent', () => {
    hasNoWork = true
    render(<ProjectFirstRun />)
    expect(screen.getByTestId('first-run-panel')).toBeInTheDocument()
  })

  it('shows for a project with an agent and no work, and opens a new conversation with it', () => {
    agents = [{ name: 'planner' }]
    render(<ProjectFirstRun />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask planner for a change' }))
    expect(goTo).toHaveBeenCalledWith(expect.objectContaining({ kind: 'conversation', agent: 'planner', projectId: 'proj-1' }))
  })

  it('is gone once the project has work', () => {
    agents = [{ name: 'planner' }]
    hasNoWork = false
    render(<ProjectFirstRun />)
    expect(screen.queryByTestId('first-run-panel')).not.toBeInTheDocument()
  })

  it('shows nothing while the roster is still loading', () => {
    agentsLoading = true
    render(<ProjectFirstRun />)
    expect(screen.queryByTestId('first-run-panel')).not.toBeInTheDocument()
  })

  it('waits for the work to be read before it says an agent has nothing to do', () => {
    agents = [{ name: 'planner' }]
    hasNoWork = null
    render(<ProjectFirstRun />)
    expect(screen.queryByTestId('first-run-panel')).not.toBeInTheDocument()
  })
})
