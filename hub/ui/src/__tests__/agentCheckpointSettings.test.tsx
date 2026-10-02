import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const thresholdMutate = vi.fn()
const modeMutate = vi.fn()
const grantMutate = vi.fn()
let roster: AgentSummary[] = []

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useUpdateAgentWaiting: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  MIN_WAITING_SECONDS: 10,
  MAX_WAITING_SECONDS: 600,
}))

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/workspace', () => ({
  useAgentWorkspace: () => ({ data: undefined, isLoading: false }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

/** The project's saved threshold, which an agent with no override of its own inherits (D10). */
/** `null` stands for a project settings read that failed. */
let projectThreshold: { checkpoint_threshold_mode: 'percent' | 'tokens' | null; checkpoint_threshold_value: number | null } | null = {
  checkpoint_threshold_mode: null,
  checkpoint_threshold_value: null,
}

vi.mock('@/api/projects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/projects')>()
  return {
    ...actual,
    useProjectSettings: () =>
      projectThreshold === null
        ? { data: undefined, isLoading: false, isError: true }
        : { data: projectThreshold, isLoading: false, isError: false },
  }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgentLaunchability: () => ({ data: undefined }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useArchiveAgent: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useUpdateAgentDescription: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentCheckpointOverride: () => ({
      mutate: thresholdMutate, isPending: false, isError: false,
    }),
    useUpdateAgentCheckpointMode: () => ({ mutate: modeMutate, isPending: false, isError: false }),
    useUpdateAgentGrant: () => ({ mutate: grantMutate, isPending: false, isError: false }),
  }
})

/** `checkpoint_compaction_percent` lands at task 3.4 (design D10) -- not yet a field on
 *  `AgentSummary`. Widened locally so fixtures can carry it ahead of that task without weakening
 *  the real type signature everywhere else in this file. */
type AgentWithCompaction = AgentSummary & { checkpoint_compaction_percent?: number | null }

function agent(overrides: Partial<AgentWithCompaction> = {}): AgentSummary {
  return {
    name: 'claude-1',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    runner: 'claude',
    ...overrides,
  } as unknown as AgentSummary
}

describe('per-agent checkpoint policy', () => {
  beforeEach(() => {
    thresholdMutate.mockReset()
    modeMutate.mockReset()
    grantMutate.mockReset()
    roster = [agent()]
  })

  it('inherits the project by default rather than showing a value nobody set', () => {
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.getByLabelText('Automatic checkpointing for claude-1')).toHaveValue('')
    expect(screen.getByLabelText('Checkpoint threshold for claude-1')).toHaveValue(null)
  })

  it('submits a token threshold in canonical units, entered in thousands', () => {
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    fireEvent.change(screen.getByLabelText('Threshold unit for claude-1'), {
      target: { value: 'tokens' },
    })
    const input = screen.getByLabelText('Checkpoint threshold for claude-1')
    fireEvent.change(input, { target: { value: '120' } })
    fireEvent.blur(input)

    expect(thresholdMutate).toHaveBeenCalledWith({
      agent: 'claude-1', mode: 'tokens', value: 120_000, notes: null,
    })
  })

  it('clears the whole override when the value is emptied, never half of it', () => {
    // An override that kept its mode while losing its value would be a number in a unit nobody
    // chose — the Hub refuses it, and the control must not be able to ask.
    roster = [agent({ checkpoint_threshold_mode: 'percent', checkpoint_threshold_value: 60 })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    const input = screen.getByLabelText('Checkpoint threshold for claude-1')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.blur(input)

    expect(thresholdMutate).toHaveBeenCalledWith(
      expect.objectContaining({ value: null, notes: null }),
    )
  })

  it('lets an agent opt out while still inheriting the threshold', () => {
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    fireEvent.change(screen.getByLabelText('Automatic checkpointing for claude-1'), {
      target: { value: 'off' },
    })
    expect(modeMutate).toHaveBeenCalledWith({ agent: 'claude-1', mode: 'off' })
    // Turning it off says nothing about the threshold, so nothing was submitted for it.
    expect(thresholdMutate).not.toHaveBeenCalled()
  })
})

describe('per-agent access grants', () => {
  beforeEach(() => {
    grantMutate.mockReset()
    roster = [agent()]
  })

  it('shows both grants closed by default', () => {
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByLabelText(/Read other agents’ checkpoints for claude-1/)).not.toBeChecked()
    expect(screen.getByLabelText(/Recall the observations behind them for claude-1/)).not.toBeChecked()
  })

  it('grants each one separately', () => {
    // The whole reason there are two: a peer allowed to see what was concluded is not thereby
    // allowed to read everything that agent's tools ever printed.
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    fireEvent.click(screen.getByLabelText(/Read other agents’ checkpoints for claude-1/))

    expect(grantMutate).toHaveBeenCalledWith({
      agent: 'claude-1', grant: 'can_read_checkpoints', enabled: true,
    })
    expect(grantMutate).toHaveBeenCalledTimes(1)
  })

  it('reflects a grant that is already open', () => {
    roster = [agent({ can_read_checkpoints: true })]
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByLabelText(/Read other agents’ checkpoints for claude-1/)).toBeChecked()
    expect(screen.getByLabelText(/Recall the observations behind them for claude-1/)).not.toBeChecked()
  })

  it('states the read grant reaches every conversation, and does not claim a bound nothing sets', () => {
    // F235: the grant is all-or-nothing across the project. Nothing can restrict a checkpoint's
    // own visibility, so the hint must not suggest one exists.
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByText(/every conversation in this project/)).toBeInTheDocument()
    expect(screen.queryByText(/visibility/)).not.toBeInTheDocument()
  })
})

/**
 * Separate from the checkpoint grants above, deliberately.
 *
 * Those widen what an agent may read; this decides whether work is allowed to merge. The column
 * has existed since migration 0068 with no schema, no route and no control, so
 * `requirement_evidence.may_accept` refused every agent in every project — a capability enforced
 * everywhere and grantable nowhere.
 */
describe('evidence acceptance grant', () => {
  beforeEach(() => {
    grantMutate.mockReset()
    roster = [agent()]
  })

  it('is closed by default, because it is authority over what ships', () => {
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByLabelText(/Accept evidence for claude-1/)).not.toBeChecked()
  })

  it('is granted on its own, without touching the checkpoint grants', () => {
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    fireEvent.click(screen.getByLabelText(/Accept evidence for claude-1/))
    expect(grantMutate).toHaveBeenCalledWith({
      agent: 'claude-1', grant: 'can_accept_evidence', enabled: true,
    })
    expect(grantMutate).toHaveBeenCalledTimes(1)
  })

  it('reflects a grant that is already open', () => {
    roster = [agent({ can_accept_evidence: true })]
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByLabelText(/Accept evidence for claude-1/)).toBeChecked()
  })

  it('says what it does not confer', () => {
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByText(/cannot accept its own/)).toBeInTheDocument()
  })
})

/**
 * Task 1.18(b), design D10 ("Thresholds derived from the compaction point") and review finding 5.
 *
 * `checkpoint_compaction_percent` does not exist on `AgentSummary` yet (lands task 3.4), and none
 * of these notices are built yet (`resolve_policy`'s new fields land earlier in the group; the UI
 * lines themselves are this task's own work, not yet written in `CheckpointOverrideSetting`). Every
 * assertion below is expected to fail today -- confirming the gap, not a crash -- through
 * `queryByText`, so a missing node reads as "expected null to be in the document" rather than an
 * uncaught `getByText` throw.
 */
describe('checkpoint ceiling notices (task 1.18(b), design D10)', () => {
  beforeEach(() => {
    thresholdMutate.mockReset()
    modeMutate.mockReset()
    grantMutate.mockReset()
    projectThreshold = { checkpoint_threshold_mode: null, checkpoint_threshold_value: null }
  })

  it('says so when the inherited project threshold could not be read', () => {
    projectThreshold = null
    roster = [agent({ checkpoint_compaction_percent: 95 })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/project's threshold could not be read/)).toBeInTheDocument()
  })

  it('an agent with no override is judged against the project threshold it inherits (task 6.3)', () => {
    projectThreshold = { checkpoint_threshold_mode: 'percent', checkpoint_threshold_value: 96 }
    roster = [agent({ checkpoint_compaction_percent: 95 })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/threshold of 96% is lowered to 92%/)).toBeInTheDocument()
  })

  it('names the runner\'s own compaction point for a Copilot-bound agent with no configured threshold', () => {
    roster = [agent({ checkpoint_compaction_percent: 80 })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/compacts at about 80%/)).toBeInTheDocument()
    expect(screen.queryByText(/fires by 77% at the latest/)).toBeInTheDocument()
  })

  it('shows no compaction-point line for an agent at the C=95 default', () => {
    roster = [agent({ checkpoint_compaction_percent: 95 })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/compacts at about/)).not.toBeInTheDocument()
  })

  it('shows no compaction-point line for an agent with no bound runner (null compaction percent)', () => {
    roster = [agent({ checkpoint_compaction_percent: null })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/compacts at about/)).not.toBeInTheDocument()
  })

  it('review finding 5: a 96% override past the C=95 final warning says it is lowered to 92%', () => {
    roster = [agent({
      checkpoint_compaction_percent: 95,
      checkpoint_threshold_mode: 'percent',
      checkpoint_threshold_value: 96,
    })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/lowered to 92%/)).toBeInTheDocument()
    expect(screen.queryByText(/Claude compacts at about 95%/)).toBeInTheDocument()
  })

  it('a 92% override at the final warning itself is not reported as lowered', () => {
    roster = [agent({
      checkpoint_compaction_percent: 95,
      checkpoint_threshold_mode: 'percent',
      checkpoint_threshold_value: 92,
    })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/lowered to 92%/)).not.toBeInTheDocument()
  })

  it('Q7 decided (b): a 95% override past the ceiling is also reported as lowered to 92%', () => {
    roster = [agent({
      checkpoint_compaction_percent: 95,
      checkpoint_threshold_mode: 'percent',
      checkpoint_threshold_value: 95,
    })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/lowered to 92%/)).toBeInTheDocument()
  })

  it('a token override on a Copilot-bound agent reports the token-or-percent ceiling', () => {
    roster = [agent({
      checkpoint_compaction_percent: 80,
      checkpoint_threshold_mode: 'tokens',
      checkpoint_threshold_value: 150_000,
    })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(
      screen.queryByText(/fires at 150000 tokens or at 77% of its window/),
    ).toBeInTheDocument()
  })

  it('a Claude token override is not given a ceiling line -- its token threshold is not lowered', () => {
    roster = [agent({
      checkpoint_compaction_percent: 95,
      checkpoint_threshold_mode: 'tokens',
      checkpoint_threshold_value: 150_000,
    })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.queryByText(/fires at 150000 tokens/)).not.toBeInTheDocument()
  })
})
