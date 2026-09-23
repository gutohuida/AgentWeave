import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentLaunchabilityResponse } from '@/api/agents'
import { RunnerPicker } from '@/components/agents/AgentSettingsControls'

// F179: an agent with no runner was shown "No runner" as though it were an ordinary choice, while
// the Hub already had the sentence saying it cannot run. The sentence below is
// `launchability.probe_agent`'s, verbatim, as `GET /agents/launchability` returns it.
const NO_RUNNER = 'No runner is bound to this agent. Bind one in the Hub UI before it can run.'

let launchability: AgentLaunchabilityResponse | undefined

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgentLaunchability: () => ({ data: launchability }) }
})

vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [{ id: 'runner-default', name: 'Default Claude', cli: 'claude' }],
    isLoading: false,
  }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

const unbound = { name: 'q1', status: 'idle', message_count: 0, active_task_count: 0, runner_id: null }
const bound = { ...unbound, runner_id: 'runner-default' }

describe('the runner picker says when an agent cannot run (F179)', () => {
  it("shows the Hub's reason for an agent with no runner", () => {
    launchability = {
      agents: { q1: { present: false, authorized: false, runnable: false, reason: NO_RUNNER } },
    }
    render(<RunnerPicker agent={unbound as never} />)

    expect(screen.getByRole('status')).toHaveTextContent(`This agent cannot run: ${NO_RUNNER}`)
    expect(screen.getByRole('option', { name: 'No runner (cannot run)' })).toBeInTheDocument()
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
    render(<RunnerPicker agent={bound as never} />)

    expect(screen.getByRole('status')).toHaveTextContent("Runner CLI 'claude' was not found in PATH.")
  })

  it('says nothing for a runnable agent', () => {
    launchability = {
      agents: { q1: { runner: 'claude', present: true, authorized: true, runnable: true, reason: null } },
    }
    render(<RunnerPicker agent={bound as never} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says nothing before the verdict has loaded', () => {
    launchability = undefined
    render(<RunnerPicker agent={unbound as never} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
