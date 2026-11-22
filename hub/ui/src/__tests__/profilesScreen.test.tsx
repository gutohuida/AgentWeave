import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { Task } from '@/api/tasks'
import { ProfilesScreen } from '@/components/profiles/ProfilesScreen'
import { profileItem, profileStatus } from '@/components/profiles/rosterItems'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// `a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-provider` FR-12 and FR-13: the Profiles
// tab's index fed from the roster the agents route returns, and one profile's page.

const refetch = vi.fn()
let roster: { data?: AgentSummary[]; isLoading: boolean; error: unknown } = { data: [], isLoading: false, error: null }
let tasks: Task[] = []

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ ...roster, refetch, dataUpdatedAt: 1 }),
}))
vi.mock('@/api/charters', () => ({ useCharters: () => ({ data: [{ id: 'ch-1', name: 'Developer' }] }) }))
vi.mock('@/api/ledger', () => ({
  useProjectLedger: () => ({ data: { spend: { by_agent: [{ agent: 'Builder', usd: 1.5, tokens: 1, turns: 1 }, { agent: 'QA', usd: null, tokens: 1, turns: 1 }] } } }),
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE }),
}))
vi.mock('@/api/spec', () => ({ useSpecDocuments: () => ({ data: { documents: [{ id: 'doc-1', title: 'Any model' }] } }) }))
vi.mock('@/api/tasks', () => ({
  useTasks: () => ({ data: { tasks } }),
  useTask: (id: string | null) => ({ data: tasks.find((t) => t.id === id) }),
}))
vi.mock('@/api/agentChat', () => ({ useProjectConversations: () => ({ data: { conversations: [] } }) }))
vi.mock('@/components/overview/SetupProfilesDialog', () => ({ SetupProfilesDialog: () => null }))
vi.mock('@/components/agents/AgentSettingsPage', () => ({
  AgentSettingsPage: ({ agent, section }: { agent: string; section: string }) => <div data-testid="section">{`${agent}:${section}`}</div>,
}))

const entry = (model: string, isDefault: boolean) => ({ id: `p-${model}`, runner_id: `r-${model}`, runner_name: model, cli: 'claude' as const, model, effort: null, default: isDefault })

function agent(name: string, extra: Partial<AgentSummary> = {}): AgentSummary {
  return { name, status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'open', last_seen: '2026-11-21T10:00:00Z', pool: [entry('claude-sonnet-5-5', true)], ...extra } as AgentSummary
}

const task = { id: 'task-1', title: 'Add retries', status: 'in_progress', build_id: 'build-1', spec_document_id: 'doc-1', builder: 'Builder' } as Task

const handlers = () => ({
  onOpenIndex: vi.fn(),
  onOpenProfile: vi.fn(),
  onOpenTask: vi.fn(),
  onOpenBuild: vi.fn(),
  onOpenConversation: vi.fn(),
  onNewThread: vi.fn(),
  onAddProfile: vi.fn(),
})

function show(selected: string | null = null, section: 'agent' | 'running' = 'agent') {
  const h = handlers()
  render(<ProfilesScreen projectId="proj-1" selected={selected} section={section} {...h} />)
  return h
}

beforeEach(() => {
  refetch.mockReset()
  tasks = [task]
  roster = {
    isLoading: false,
    error: null,
    data: [
      agent('Scout', { pool: [], runner_id: null }),
      agent('QA'),
      agent('Builder', { running_runs: [{ run_id: 'run-1', conversation_id: null, task_id: 'task-1', started_at: '2026-11-22T01:00:00Z' }], charter_id: 'ch-1', pool: [entry('claude-haiku-4-5', true), entry('claude-sonnet-5-5', false)] }),
      agent('Old', { lifecycle: 'archived' }),
    ],
  }
})

describe('a roster entry as a Profiles row', () => {
  it('reads a run on a task as Working on it, a review of another profile’s work as Reviewing, and no pool as No model', () => {
    const taskOf = (id: string) => tasks.find((t) => t.id === id)
    expect(profileStatus(roster.data![2]!, taskOf)).toEqual({ kind: 'working', detail: 'Add retries' })
    tasks = [{ ...task, status: 'under_review' }]
    expect(profileStatus(agent('QA', { running_runs: [{ run_id: 'r', conversation_id: null, task_id: 'task-1', started_at: null }] }), taskOf).kind).toBe('reviewing')
    expect(profileStatus(roster.data![0]!, taskOf)).toEqual({ kind: 'no-model' })
    expect(profileStatus(roster.data![1]!, taskOf)).toEqual({ kind: 'idle' })
  })

  it('names the default model and counts the rest of the pool; unknown spend stays unknown', () => {
    const item = profileItem(roster.data![2]!, { catalog: MODEL_CATALOG_FIXTURE, charterName: 'Developer', spend: null, taskOf: () => task })
    expect(item.provider).toBe('claude')
    expect(item.moreModels).toBe(1)
    expect(item.spendUsd).toBeNull()
  })
})

describe('the Profiles index (FR-12)', () => {
  it('lists the working profile first, then A to Z, with the archived one in a collapsed group of 1', () => {
    show()
    const rows = screen.getAllByRole('button').filter((b) => b.getAttribute('data-slot') === 'profile-row')
    expect(rows.map((r) => r.getAttribute('data-profile'))).toEqual(['Builder', 'QA', 'Scout'])
    expect(within(rows[0]!).getByText('Working')).toBeInTheDocument()
    expect(within(rows[2]!).getByText('No model')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('$1.50')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('unpriced')).toBeInTheDocument()
    const archived = screen.getByRole('button', { name: /Archived/ })
    expect(archived).toHaveAttribute('aria-expanded', 'false')
    expect(archived).toHaveTextContent('1')
  })

  it('opens a profile’s page from its row', async () => {
    const h = show()
    await userEvent.click(screen.getAllByRole('button').find((b) => b.getAttribute('data-profile') === 'QA')!)
    expect(h.onOpenProfile).toHaveBeenCalledWith('QA')
  })

  it('offers Retry when the agents route fails, and the pair when there are no profiles (FR-12)', async () => {
    roster = { isLoading: false, error: new Error('500'), data: undefined }
    show()
    await userEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('says there are no profiles, offering a builder and a checker or one profile', () => {
    roster = { isLoading: false, error: null, data: [] }
    show()
    const empty = screen.getByTestId('profiles-empty')
    expect(within(empty).getByRole('button', { name: 'Add a builder and a checker' })).toBeInTheDocument()
    expect(within(empty).getByRole('button', { name: /Add profile/ })).toBeInTheDocument()
  })
})

describe('a profile’s page (FR-13)', () => {
  it('shows one row of section tabs labelled as the sections are headed, over the open section', async () => {
    const h = show('Builder', 'running')
    const tabs = screen.getByRole('radiogroup', { name: 'Builder sections' })
    expect(within(tabs).getAllByRole('radio').map((r) => r.textContent?.replace(/\d+$/, ''))).toEqual([
      'Profile', 'Models', 'Permissions', 'Checkpoints', 'Workspace', 'Runs',
    ])
    expect(within(tabs).getByRole('radio', { name: /^Models/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('section')).toHaveTextContent('Builder:running')
    expect(screen.getAllByRole('radiogroup')).toHaveLength(1)
    await userEvent.click(within(tabs).getByRole('radio', { name: /^Permissions/ }))
    expect(h.onOpenProfile).toHaveBeenCalledWith('Builder', 'permissions')
  })

  it('names the task it is on in the Now strip, with Open task and Open build', async () => {
    const h = show('Builder')
    const now = screen.getByRole('region', { name: 'Now' })
    expect(now).toHaveTextContent('Add retries')
    await userEvent.click(within(now).getByRole('button', { name: /Open task/ }))
    expect(h.onOpenTask).toHaveBeenCalledWith('task-1')
    await userEvent.click(within(now).getByRole('button', { name: /Open build/ }))
    expect(h.onOpenBuild).toHaveBeenCalledWith('build-1')
  })

  it('goes back to the index on Escape', async () => {
    const h = show('Builder')
    screen.getByTestId('profile-page').focus()
    await userEvent.keyboard('{Escape}')
    expect(h.onOpenIndex).toHaveBeenCalled()
  })
})
