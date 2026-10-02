import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AccountingSnapshot } from '@/api/accounting'
import { AccountingPanel } from '@/components/accounting/AccountingPanel'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'
import { accountingDisplayLabel } from '@/components/accounting/accountingDisplay'
import * as accountingDisplayModule from '@/components/accounting/accountingDisplay'

/** `formatAiCredits` lands in task 2.x (`a-copilot-run-shows-its-credits`, design "One formatter").
 *  Read through the namespace rather than a named import so this file still type-checks and the
 *  rest of its tests still run before that task exists -- a missing named export would fail
 *  module load for the whole file, not just this assertion. */
function readFormatAiCredits(): ((nano: number | null) => string | null) | undefined {
  return (accountingDisplayModule as unknown as Record<string, unknown>).formatAiCredits as
    | ((nano: number | null) => string | null)
    | undefined
}

let snapshot: AccountingSnapshot
const mutate = vi.fn()
/** The mutation's reported outcome. The panel reports success and failure in-section, so the
 *  tests have to be able to put it in each of those states. */
let mutationState: {
  isPending: boolean
  isSuccess: boolean
  isError: boolean
  error: unknown
  variables: number | null | undefined
}

vi.mock('@/api/accounting', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/accounting')>()
  return {
    ...actual,
    useAccounting: () => ({ data: snapshot, isLoading: false }),
    useUpdateTokenBudget: () => ({ mutate, ...mutationState }),
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
      unpriced_turns: 1,
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
        unpriced_turns: 0,
      },
      {
        agent: 'codex',
        input_tokens: null,
        output_tokens: null,
        total_tokens: null,
        measured_turns: 0,
        unavailable_turns: 1,
        api_equivalent_usd_micros: null,
        unpriced_turns: 1,
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
    mutationState = {
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
      variables: undefined,
    }
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
        unpriced_turns: 0,
      },
    }
    render(<AccountingPanel />)
    expect(screen.getByText('$0.0125 API-equivalent estimate')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says an API-equivalent estimate excludes the turns it could not price', () => {
    snapshot = {
      ...baseSnapshot(),
      budget: { limit_tokens: null, used_tokens: 1234, remaining_tokens: null, exhausted: false },
      preferred_display: {
        kind: 'api_equivalent',
        label: 'API-equivalent estimate',
        usd_micros: 12_500,
        unpriced_turns: 10,
      },
    }
    render(<AccountingPanel />)
    expect(
      screen.getByText('$0.0125 API-equivalent estimate — excludes 10 turns with no reported cost'),
    ).toBeInTheDocument()
  })

  it('turns a runner allowance payload into readable operator language instead of raw JSON', () => {
    snapshot.preferred_display = {
      kind: 'allowance',
      label: 'Rate-limit allowance',
      allowance: {
        status: 'rejected',
        rateLimitType: 'seven_day',
        resetsAt: 1_788_000_000,
        overageDisabledReason: 'out_of_credits',
      },
    }
    render(<AccountingPanel />)

    expect(screen.getByText(/Weekly allowance exhausted/)).toBeInTheDocument()
    expect(screen.queryByText(/\{"status"/)).not.toBeInTheDocument()
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

  describe('the budget control reports what happened (contextual-navigation 4.7)', () => {
    it('refuses a value that is not a budget, and says why, without calling the API', () => {
      render(<AccountingPanel />)
      const input = screen.getByLabelText('Project token budget')

      fireEvent.change(input, { target: { value: '-5' } })
      fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

      // The whole defect: this used to do nothing at all, which from the operator's chair is
      // indistinguishable from a save that silently failed.
      expect(mutate).not.toHaveBeenCalled()
      expect(screen.getByText(/whole number of tokens greater than zero/)).toHaveAttribute(
        'role',
        'alert',
      )
      expect(input).toHaveAttribute('aria-invalid', 'true')
    })

    it('points an empty field at Disable rather than refusing silently', () => {
      render(<AccountingPanel />)
      fireEvent.change(screen.getByLabelText('Project token budget'), { target: { value: '' } })
      fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

      expect(mutate).not.toHaveBeenCalled()
      expect(screen.getByText(/press Disable to remove the limit/)).toBeInTheDocument()
    })

    it('clears its objection as soon as the operator answers it', () => {
      render(<AccountingPanel />)
      const input = screen.getByLabelText('Project token budget')
      fireEvent.change(input, { target: { value: '0' } })
      fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
      expect(screen.getByText(/greater than zero/)).toBeInTheDocument()

      fireEvent.change(input, { target: { value: '5000' } })
      expect(screen.queryByText(/greater than zero/)).not.toBeInTheDocument()
      expect(input).not.toHaveAttribute('aria-invalid')
    })

    it('confirms a saved budget', () => {
      mutationState = { ...mutationState, isSuccess: true, variables: 5000 }
      snapshot.budget.exhausted = false
      render(<AccountingPanel />)
      expect(screen.getByRole('status')).toHaveTextContent('Budget saved.')
    })

    it('says a removal was a removal, not a save', () => {
      mutationState = { ...mutationState, isSuccess: true, variables: null }
      snapshot.budget.exhausted = false
      render(<AccountingPanel />)
      expect(screen.getByRole('status')).toHaveTextContent('Budget removed')
    })

    it('reports a server failure in the section', () => {
      mutationState = {
        ...mutationState,
        isError: true,
        error: new Error('nope'),
        variables: 5000,
      }
      snapshot.budget.exhausted = false
      render(<AccountingPanel />)
      expect(screen.getByRole('alert')).toHaveTextContent(/could not be saved|nope/)
    })

    it('does not offer Disable while a save is in flight', () => {
      mutationState = { ...mutationState, isPending: true }
      render(<AccountingPanel />)
      expect(screen.getByRole('button', { name: 'Disable' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()
    })
  })

  it('accountingDisplayLabel notes unpriced turns only when there are any', () => {
    expect(
      accountingDisplayLabel({
        kind: 'api_equivalent',
        label: 'API-equivalent estimate',
        usd_micros: 42_157,
        unpriced_turns: 10,
      }),
    ).toContain('excludes 10 turns')
    expect(
      accountingDisplayLabel({
        kind: 'api_equivalent',
        label: 'API-equivalent estimate',
        usd_micros: 42_157,
        unpriced_turns: 0,
      }),
    ).toBe('$0.0422 API-equivalent estimate')
    expect(
      accountingDisplayLabel({
        kind: 'api_equivalent',
        label: 'API-equivalent estimate',
        usd_micros: 42_157,
        unpriced_turns: 1,
      }),
    ).toBe('$0.0422 API-equivalent estimate — excludes 1 turn with no reported cost')
  })

  it('renders the compact exhausted warning used by the conversation shell', () => {
    render(<BudgetExhaustionNotice exhausted compact />)
    expect(screen.getByRole('status')).toHaveTextContent('budget paused')
    expect(screen.getByRole('status')).toHaveAttribute(
      'title',
      'Autonomous turns are paused; operator messages can still run.',
    )
  })

  describe('AI credits (a-copilot-run-shows-its-credits, task 1.16)', () => {
    it('formatAiCredits renders nano-AIU as AI credits to two decimals', () => {
      expect(readFormatAiCredits()?.(275_856_000)).toBe('0.28 AI credits')
    })

    it('formatAiCredits shows <0.01 AI credits below the display floor', () => {
      expect(readFormatAiCredits()?.(4_000_000)).toBe('<0.01 AI credits')
    })

    it('formatAiCredits is null when there is nothing to show', () => {
      expect(readFormatAiCredits()?.(null)).toBeNull()
    })

    it('accountingDisplayLabel names the provider on a non-Claude allowance reading', () => {
      const label = accountingDisplayLabel({
        kind: 'allowance',
        label: 'Rate-limit allowance',
        allowance: {
          status: 'allowed',
          rateLimitType: 'monthly',
          resetsAt: 1_790_812_800,
          remainingPercentage: 96.5,
        },
        runner: 'copilot',
      } as unknown as Parameters<typeof accountingDisplayLabel>[0])
      expect(label).toMatch(/^Copilot monthly allowance available/)
    })

    it('keeps the existing Claude allowance label unprefixed when the reading names no runner', () => {
      const label = accountingDisplayLabel({
        kind: 'allowance',
        label: 'Rate-limit allowance',
        allowance: { status: 'allowed', rateLimitType: 'seven_day', resetsAt: 1_788_000_000 },
      })
      expect(label).toMatch(/^Weekly allowance available/)
      expect(label).not.toMatch(/^Copilot/)
    })
  })

  describe('AI credits on the Budgets panel (task 1.18)', () => {
    /** `project.ai_nano_aiu`/`premium_requests` land at task 6.1 (design D6's byte-identity test);
     *  the headline caption and per-agent chips land at an unticked UI task. Cast past today's
     *  `UsageSummary`/`AgentUsageSummary` types rather than widening them here. */
    it('adds a second headline line with AI credits and premium requests when the project reports them', () => {
      snapshot = {
        ...baseSnapshot(),
        project: {
          ...baseSnapshot().project,
          ai_nano_aiu: 275_856_000,
          premium_requests: 1.5,
        } as unknown as AccountingSnapshot['project'],
      }
      const { container } = render(<AccountingPanel />)
      expect(container.textContent).toContain(
        '0.28 AI credits · 1.5 premium requests (Copilot) — not counted against the budget',
      )
    })

    it('shows no credits line when the project has nothing to report (control)', () => {
      const { container } = render(<AccountingPanel />)
      expect(container.textContent).not.toContain('AI credits')
    })

    it('adds AI credits to a per-agent chip only for the agent that reports them', () => {
      snapshot = baseSnapshot()
      snapshot.agents = [
        { ...snapshot.agents[0], ai_nano_aiu: 275_856_000 } as unknown as AccountingSnapshot['agents'][number],
        snapshot.agents[1],
      ]
      render(<AccountingPanel />)
      expect(screen.getByText('claude: 1,234 tokens · 0.28 AI credits')).toBeInTheDocument()
      expect(screen.getByText('codex: Unavailable · 1 unavailable')).toBeInTheDocument()
    })
  })
})
