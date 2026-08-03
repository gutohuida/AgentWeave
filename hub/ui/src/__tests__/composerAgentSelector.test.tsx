import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import { ComposerAgentSelector } from '@/components/agents/ComposerAgentSelector'

const agents: AgentSummary[] = [
  { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' },
  { name: 'codex', status: 'idle', message_count: 0, active_task_count: 0, runner: 'codex' },
  { name: 'minimax', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude_proxy' },
]

const launchability = {
  claude: { present: true, authorized: true, runnable: true },
  codex: { present: true, authorized: true, runnable: true },
  minimax: {
    present: true,
    authorized: false,
    runnable: false,
    reason: 'Missing MINIMAX_API_KEY',
  },
}

describe('ComposerAgentSelector', () => {
  it('lists every configured agent and visibly distinguishes launchability', async () => {
    const user = userEvent.setup()
    render(
      <ComposerAgentSelector
        agents={agents}
        launchability={launchability}
        selectedAgent="claude"
        onSelect={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Target agent: claude' }))

    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByRole('option', { name: /claude.*runnable/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /minimax.*not authorized/i })).toBeInTheDocument()
    expect(screen.getByText('Missing MINIMAX_API_KEY')).toBeInTheDocument()
  })

  it('filters the configured-agent list by search and selects the match', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <ComposerAgentSelector
        agents={agents}
        launchability={launchability}
        selectedAgent="claude"
        onSelect={onSelect}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Target agent: claude' }))
    await user.type(screen.getByRole('searchbox', { name: 'Search agents' }), 'cod')

    expect(screen.getAllByRole('option')).toHaveLength(1)
    await user.click(screen.getByRole('option', { name: /codex/i }))
    expect(onSelect).toHaveBeenCalledWith('codex')
  })
})
