import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AccountingSnapshot } from '@/api/accounting'
import { AccountingPanel } from '@/components/accounting/AccountingPanel'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'

let snapshot: AccountingSnapshot
const mutate = vi.fn()

vi.mock('@/api/accounting', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/accounting')>()
  return {
    ...actual,
    useAccounting: () => ({ data: snapshot, isLoading: false }),
    useUpdateTokenBudget: () => ({ mutate, isPending: false }),
  }
})

function baseSnapshot(): AccountingSnapshot {
  return {
    project: {
      input_tokens: 1000,
      output_tokens: 234,
      total_tokens: 1234,
      measured_turns: 2,
      unavailable_turns: 1,
      api_equivalent_usd_micros: 12_500,
    },
    agents: [
      {
        agent: 'claude',
        input_tokens: 1000,
        output_tokens: 234,
        total_tokens: 1234,
        measured_turns: 2,
        unavailable_turns: 0,
        api_equivalent_usd_micros: 12_500,
      },
      {
        agent: 'codex',
        input_tokens: null,
        output_tokens: null,
        total_tokens: null,
        measured_turns: 0,
        unavailable_turns: 1,
        api_equivalent_usd_micros: null,
      },
    ],
    budget: {
      limit_tokens: 1234,
      used_tokens: 1234,
      remaining_tokens: 0,
      exhausted: true,
    },
    preferred_display: {
      kind: 'allowance',
      label: 'Rate-limit allowance',
      allowance: { five_hour: { remaining_percent: 64 } },
    },
    recent_turns: [],
  }
}

describe('accounting presentation', () => {
  beforeEach(() => {
    snapshot = baseSnapshot()
    mutate.mockReset()
  })

  it('shows totals, unavailable usage, allowance precedence, and exhaustion control', () => {
    render(<AccountingPanel />)

    expect(screen.getByText('1,234 tokens')).toBeInTheDocument()
    expect(screen.getByText('Rate-limit allowance')).toBeInTheDocument()
    expect(screen.queryByText(/API-equivalent estimate/)).not.toBeInTheDocument()
    expect(screen.getByText(/1 usage unavailable/)).toBeInTheDocument()
    expect(screen.getByText('codex: Unavailable · 1 unavailable')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Autonomous turns are paused; operator messages can still run.',
    )
  })

  it('labels runner monetary telemetry as API-equivalent', () => {
    snapshot = {
      ...baseSnapshot(),
      budget: { limit_tokens: null, used_tokens: 1234, remaining_tokens: null, exhausted: false },
      preferred_display: {
        kind: 'api_equivalent',
        label: 'API-equivalent estimate',
        usd_micros: 12_500,
      },
    }
    render(<AccountingPanel />)
    expect(screen.getByText('$0.0125 API-equivalent estimate')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('updates or disables the project token budget', () => {
    render(<AccountingPanel />)
    const input = screen.getByLabelText('Project token budget')
    fireEvent.change(input, { target: { value: '5000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(mutate).toHaveBeenCalledWith(5000)

    fireEvent.click(screen.getByRole('button', { name: 'Disable' }))
    expect(mutate).toHaveBeenCalledWith(null)
  })

  it('renders the compact exhausted warning used by the conversation shell', () => {
    render(<BudgetExhaustionNotice exhausted compact />)
    expect(screen.getByRole('status')).toHaveTextContent('budget paused')
    expect(screen.getByRole('status')).toHaveAttribute(
      'title',
      'Autonomous turns are paused; operator messages can still run.',
    )
  })
})
