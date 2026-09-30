import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { providerForRunner } from '@/api/modelCatalog'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { ProviderMark } from '@/components/common/Icon'

// `a-copilot-agent-runs-over-acp` task 1.19 (design D19).

const agent = { name: 'cop-1' } as AgentSummary

function toolUse(tool: string, input: Record<string, unknown>): TimelineEntry {
  return {
    id: `tool_${tool}`,
    kind: 'agent_output',
    output_kind: 'tool_use',
    content: `Called ${tool}`,
    timestamp: '2026-09-30T00:00:00Z',
    delivery_state: 'delivered',
    run_id: 'run-cop',
    payload: { call_id: 'c1', tool, input: JSON.stringify(input) },
  } as TimelineEntry
}

describe('Copilot in the UI', () => {
  it('maps a copilot runner to the copilot catalog provider', () => {
    // Without it the composer's model controls resolve no provider for a Copilot agent.
    expect(providerForRunner('copilot')).toBe('copilot')
  })

  it('renders the Copilot brand mark as an SVG, not initials', () => {
    const { container } = render(<ProviderMark provider="copilot" label="GitHub Copilot" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.queryByText('GC')).not.toBeInTheDocument()
  })

  it.each(['edit', 'delete', 'move'])('counts a Copilot %s row as a write, named from its locations', (tool) => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[toolUse(tool, { title: 'Change it', rawInput: {}, locations: [{ path: 'C:/work/src/app.py' }] })]}
        roster={[agent]}
        runs={{}}
        isRunning={false}
      />,
    )
    expect(screen.getByTitle('Wrote to app.py')).toBeInTheDocument()
  })

  it('does not count a Copilot shell row as a write', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[toolUse('shell', { title: 'Run tests', rawInput: { command: 'pytest' }, locations: [] })]}
        roster={[agent]}
        runs={{}}
        isRunning={false}
      />,
    )
    expect(screen.queryByTitle(/^Wrote to/)).not.toBeInTheDocument()
  })
})
