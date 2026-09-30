import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentLaunchabilityResponse } from '@/api/agents'
import { RunnerPicker } from '@/components/agents/AgentSettingsControls'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// F178: `collaboration_ready`/`collaboration_reason` reached no screen once `AgentCard` stopped being
// mounted. The picker already reads the verdict (F179), so it says this too. The reason below is
// the start of `get_agents_launchability`'s Codex opt-out sentence, as the route returns it.
const OPT_OUT =
  "This Codex agent's runner opted out of the app-server transport (flags: [\"--no-app-server\"]) " +
  'and the agent does not have Full access, so it falls back to classic exec.'
const NO_RUNNER = 'No runner is bound to this agent. Bind one in the Hub UI before it can run.'

let launchability: AgentLaunchabilityResponse | undefined

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgentLaunchability: () => ({ data: launchability, error: null }) }
})

vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [{ id: 'runner-codex', name: 'Codex', cli: 'codex', model: null }],
    isLoading: false,
  }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/modelCatalog', () => ({
  useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE }),
}))

const agent = { name: 'q1', status: 'idle', message_count: 0, active_task_count: 0, runner_id: 'runner-codex' }
const runnable = { runner: 'codex', present: true, authorized: true, runnable: true, reason: null }

function verdict(fields: Record<string, unknown>) {
  launchability = { agents: { q1: fields as never } }
  render(<RunnerPicker agent={agent as never} />)
}

describe('the runner picker says when an agent will run but cannot collaborate (F178)', () => {
  it("shows the Hub's reason for a runnable agent that is not collaboration-ready", () => {
    verdict({ ...runnable, collaboration_ready: false, collaboration_reason: OPT_OUT })

    const line = screen.getByText(/cannot collaborate/)
    expect(line).toHaveAttribute('role', 'status')
    expect(line).toHaveTextContent(`This agent will run, but cannot collaborate: ${OPT_OUT}`)
  })

  it('says nothing for a collaboration-ready agent', () => {
    verdict({ ...runnable, collaboration_ready: true, collaboration_reason: null })

    expect(screen.queryByText(/cannot collaborate/)).not.toBeInTheDocument()
  })

  it('says nothing when collaboration does not apply', () => {
    verdict({ ...runnable, collaboration_ready: null, collaboration_reason: null })

    expect(screen.queryByText(/cannot collaborate/)).not.toBeInTheDocument()
  })

  it('an agent that cannot run is told only that', () => {
    verdict({ present: false, authorized: false, runnable: false, reason: NO_RUNNER, collaboration_ready: null })

    expect(screen.getByText(/^This agent cannot run/)).toHaveTextContent(`This agent cannot run: ${NO_RUNNER}`)
    expect(screen.queryByText(/cannot collaborate/)).not.toBeInTheDocument()
  })

  it('keeps the two lines apart even for a verdict the Hub never sends (design D3)', () => {
    // The Hub computes collaboration only for a runnable agent, so this pair cannot arrive. If the
    // picker's `runnable === true` clause were dropped, it would show both lines here.
    verdict({
      present: false,
      authorized: false,
      runnable: false,
      reason: NO_RUNNER,
      collaboration_ready: false,
      collaboration_reason: OPT_OUT,
    })

    expect(screen.getByText(/^This agent cannot run/)).toBeInTheDocument()
    expect(screen.queryByText(/cannot collaborate/)).not.toBeInTheDocument()
  })

  it('falls back to a sentence of its own when the Hub gives no reason', () => {
    verdict({ ...runnable, collaboration_ready: false, collaboration_reason: null })

    expect(screen.getByText(/cannot collaborate/)).toHaveTextContent(
      'This agent will run, but cannot collaborate: the Hub reports its tool calls would be refused.',
    )
  })
})
