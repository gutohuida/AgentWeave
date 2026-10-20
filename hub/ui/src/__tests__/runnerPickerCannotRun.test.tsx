import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentLaunchabilityResponse } from '@/api/agents'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'
import { openMenuSelect } from './support/menuSelect'

// F179: an agent with no runner was shown "No runner" as though it were an ordinary choice, while
// the Hub already had the sentence saying it cannot run. The sentence below is
// `launchability.probe_agent`'s, verbatim, as `GET /agents/launchability` returns it.
const NO_RUNNER = 'No runner is bound to this agent. Bind one in the Hub UI before it can run.'

let launchability: AgentLaunchabilityResponse | undefined
let launchabilityError: unknown = null
let runners: Array<{ id: string; name: string; cli: string; model?: string | null }> = [
  { id: 'runner-default', name: 'Default Claude', cli: 'claude', model: null },
]

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: roster, isLoading: false }), useAgentLaunchability: () => ({ data: launchability, error: launchabilityError }) }
})

let runnersError: Error | null = null
vi.mock('@/api/runners', () => ({
  useRunners: () => (runnersError ? { data: undefined, isLoading: false, error: runnersError } : { data: runners, isLoading: false, error: null }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE }),
}))

/** The runner's row lives on the agent's Execution page; the page is rendered for real, with the
 *  roster answering `agent` and a query client for the writes it holds. */
let roster: unknown[] = []
function renderExecution(summary: { name: string; runner_id?: string | null }) {
  roster = [summary]
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AgentSettingsPage agent={summary.name} section="execution" onSelectSection={vi.fn()} onBack={vi.fn()} />
    </QueryClientProvider>,
  )
}

const unbound = { name: 'q1', status: 'idle', message_count: 0, active_task_count: 0, runner_id: null }
const bound = { ...unbound, runner_id: 'runner-default' }

describe('the runner picker says when an agent cannot run (F179)', () => {
  beforeEach(() => {
    runners = [{ id: 'runner-default', name: 'Default Claude', cli: 'claude', model: null }]
    runnersError = null
  })

  it('says the runner list is incomplete when the runners cannot be read, rather than offering none', () => {
    runnersError = new Error('500')
    launchability = undefined
    renderExecution(bound)
    expect(screen.getByTestId('agent-runners-error')).toHaveTextContent("Could not load this project's runners")
  })

  it("shows the Hub's reason for an agent with no runner", () => {
    launchability = {
      agents: { q1: { present: false, authorized: false, runnable: false, reason: NO_RUNNER } },
    }
    renderExecution(unbound)

    expect(screen.getByRole('status')).toHaveTextContent(`This agent cannot run: ${NO_RUNNER}`)
    expect(screen.getByRole('button', { name: 'Runner for q1' })).toHaveTextContent('No runner')
  })

  it('offers no runner as the choice that cannot run, said on its own line', async () => {
    const user = userEvent.setup()
    launchability = { agents: { q1: { present: false, authorized: false, runnable: false, reason: NO_RUNNER } } }
    renderExecution(unbound)
    const [first] = await openMenuSelect(user, 'Runner for q1')
    expect(first).toHaveTextContent('No runner')
    expect(first).toHaveTextContent('The agent cannot run until it has one')
  })

  it('shows any other reason the Hub gives, not only the unbound one', () => {
    launchability = {
      agents: {
        q1: {
          runner: 'claude',
          present: false,
          authorized: true,
          runnable: false,
          reason: "Runner CLI 'claude' was not found in PATH.",
        },
      },
    }
    renderExecution(bound)

    expect(screen.getByRole('status')).toHaveTextContent("Runner CLI 'claude' was not found in PATH.")
  })

  it('says nothing for a runnable agent', () => {
    launchability = {
      agents: { q1: { runner: 'claude', present: true, authorized: true, runnable: true, reason: null } },
    }
    renderExecution(bound)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says only what it knows before the verdict has loaded', () => {
    // Unbound is known without the Hub: it cannot run. Anything else waits for the verdict.
    launchability = undefined
    renderExecution(unbound)
    expect(screen.getByRole('status')).toHaveTextContent('This agent cannot run until it has a runner.')
  })

  it('says nothing for a bound agent before the verdict has loaded', () => {
    launchability = undefined
    renderExecution(bound)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says when the check itself failed', () => {
    launchability = undefined
    launchabilityError = new Error('boom')
    renderExecution(bound)

    expect(screen.getByRole('status')).toHaveTextContent('Could not check whether this agent can run.')
    launchabilityError = null
  })

  it('names each same-named runner apart by its model (F268)', async () => {
    const user = userEvent.setup()
    // Served in `created_at` order, the order `list_runners` returns (`runners.py:82`).
    runners = [
      { id: 'runner-opus', name: 'Twin', cli: 'claude', model: 'claude-opus-5' },
      { id: 'runner-haiku', name: 'Twin', cli: 'claude', model: 'claude-haiku-4-5-20251001' },
    ]
    launchability = {
      agents: { q1: { runner: 'claude', present: true, authorized: true, runnable: true, reason: null } },
    }
    renderExecution({ ...bound, runner_id: 'runner-opus' })

    const twins = (await openMenuSelect(user, 'Runner for q1')).filter((o) => o.textContent?.startsWith('Twin'))
    expect(twins.map((o) => o.textContent)).toEqual([
      expect.stringContaining('Opus 5 · claude'),
      expect.stringContaining('Haiku 4.5 · claude'),
    ])
  })
})
