import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FoldAgentDialog } from '@/components/agents/FoldAgentDialog'
import { foldedComposerReason } from '@/lib/foldPresentation'
import { Composer } from '@/components/agents/Composer'
import type { AgentSummary, FoldPreview } from '@/api/agents'
import { setComposerText } from './testUtils/composerField'

// FR-2 (render half): the fold dialog lists every difference and the open work before confirming.
// FR-13 (composer half): a folded agent's composer refuses the turn, naming the profile.

const foldMutate = vi.fn()
let previewError: unknown = null
let preview: FoldPreview | undefined
const previewCalls: Array<[string, string | null]> = []

const roster: AgentSummary[] = [
  { name: 'DeveloperOpus2', status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'open' },
  { name: 'DeveloperOpus', status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'open' },
  { name: 'Old', status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'archived', folded_into: 'DeveloperOpus' },
]

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgents: () => ({ data: roster, isLoading: false }),
    useFoldPreview: (agent: string, into: string | null) => {
      previewCalls.push([agent, into])
      return { data: into ? preview : undefined, error: previewError, isLoading: false }
    },
    useFoldAgent: () => ({ mutate: foldMutate, isPending: false, error: null }),
  }
})

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const PREVIEW: FoldPreview = {
  source: 'DeveloperOpus2',
  profile: 'DeveloperOpus',
  can_fold: true,
  refusals: [],
  setting_differences: [
    { setting: 'runner', source: { runner_id: 'r1', name: 'claude-sonnet', cli: 'claude', model: 'sonnet' }, profile: { runner_id: 'r2', name: 'claude-opus', cli: 'claude', model: 'opus' } },
    { setting: 'charter', source: { charter_id: 'c1', name: 'Reviewer' }, profile: { charter_id: 'c2', name: 'Builder' } },
    { setting: 'can_accept_evidence', source: true, profile: false },
    { setting: 'default_permission_mode', source: 'plan', profile: 'acceptEdits' },
  ],
  pool_entries_added: [{ id: 'p1', runner_id: 'r1', runner_name: 'claude-sonnet', cli: 'claude', model: 'sonnet', effort: null, default: false }],
  open_work: [
    { kind: 'task', id: 't1', field: 'assignee', title: 'Write the migration' },
    { kind: 'task', id: 't2', field: 'checker', title: 'Review the routes' },
  ],
}

async function openDialog() {
  const user = userEvent.setup()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <FoldAgentDialog agent="DeveloperOpus2" />
    </QueryClientProvider>,
  )
  await user.click(screen.getByTestId('agent-fold-open'))
  return user
}

async function chooseProfile(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('fold-profile-select'))
  await user.click(await screen.findByRole('menuitemradio', { name: 'DeveloperOpus' }))
}

beforeEach(() => {
  foldMutate.mockReset()
  previewError = null
  preview = PREVIEW
  previewCalls.length = 0
})

describe('the Fold into... dialog (FR-2)', () => {
  it('offers only open agents other than itself as the profile', async () => {
    const user = await openDialog()
    await user.click(screen.getByTestId('fold-profile-select'))
    expect(await screen.findByRole('menuitemradio', { name: 'DeveloperOpus' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitemradio', { name: 'DeveloperOpus2' })).toBeNull()
    expect(screen.queryByRole('menuitemradio', { name: 'Old' })).toBeNull()
  })

  it('lists the setting differences, the runner added and the open work before confirming', async () => {
    const user = await openDialog()
    // Nothing to confirm until a profile is chosen.
    expect(screen.getByTestId('fold-confirm')).toBeDisabled()
    await chooseProfile(user)

    const differences = screen.getByTestId('fold-differences')
    expect(within(differences).getByTestId('fold-difference-runner')).toHaveTextContent('claude-sonnet · sonnet')
    expect(within(differences).getByTestId('fold-difference-runner')).toHaveTextContent('DeveloperOpus keeps claude-opus · opus')
    expect(within(differences).getByTestId('fold-difference-charter')).toHaveTextContent('Reviewer')
    expect(within(differences).getByTestId('fold-difference-can_accept_evidence')).toHaveTextContent(
      'DeveloperOpus2 has granted; DeveloperOpus keeps not granted',
    )
    expect(within(differences).getByTestId('fold-difference-default_permission_mode')).toHaveTextContent('plan')
    expect(screen.getByTestId('fold-pool-entry')).toHaveTextContent('claude-sonnet · sonnet')
    const work = screen.getAllByTestId('fold-open-work')
    expect(work).toHaveLength(2)
    expect(work[0]).toHaveTextContent('Write the migration')
    expect(work[1]).toHaveTextContent('Review the routes')
    expect(previewCalls[previewCalls.length - 1]).toEqual(['DeveloperOpus2', 'DeveloperOpus'])
    // Seen, nothing posted yet.
    expect(foldMutate).not.toHaveBeenCalled()
  })

  it('posts the fold only when confirmed', async () => {
    const user = await openDialog()
    await chooseProfile(user)
    await user.click(screen.getByTestId('fold-confirm'))
    expect(foldMutate).toHaveBeenCalledWith({ agent: 'DeveloperOpus2', into: 'DeveloperOpus' }, expect.anything())
  })

  it('shows every refusal and will not confirm', async () => {
    preview = {
      ...PREVIEW,
      can_fold: false,
      refusals: [{ code: 'fold_live_run', message: 'DeveloperOpus2 has a run in progress (run-1).', ids: ['run-1'] }],
    }
    const user = await openDialog()
    await chooseProfile(user)
    expect(screen.getByTestId('fold-refusals')).toHaveTextContent('has a run in progress (run-1)')
    expect(screen.getByTestId('fold-confirm')).toBeDisabled()
  })

  it('says plainly when nothing is dropped, added or moved', async () => {
    preview = { ...PREVIEW, setting_differences: [], pool_entries_added: [], open_work: [] }
    const user = await openDialog()
    await chooseProfile(user)
    expect(screen.getByTestId('fold-differences')).toHaveTextContent('Nothing is dropped')
    expect(screen.getByTestId('fold-work')).toHaveTextContent('None.')
  })
})

describe("a folded agent's composer (FR-13)", () => {
  it('names the profile and refuses the turn', () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <Composer
        agent="Old"
        projectId="proj-1"
        conversationId="conv-1"
        isRunning={false}
        onSubmit={onSubmit}
        disabledReason={foldedComposerReason({ name: 'Old', folded_into: 'DeveloperOpus' })}
      />,
    )
    expect(screen.getByTestId('composer-disabled-reason')).toHaveTextContent('Old was folded into DeveloperOpus')
    setComposerText(screen.getByRole('textbox'), 'hello?')
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('gives an agent that was not folded no reason', () => {
    expect(foldedComposerReason({ name: 'Open', folded_into: null })).toBeUndefined()
    expect(foldedComposerReason({ name: 'Open' })).toBeUndefined()
  })
})
