import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AccountingSnapshot } from '@/api/accounting'
import { BudgetsSection } from '@/components/settings/sections/BudgetsSection'
import { useToastStore } from '@/lib/toast'
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
let accountingError: Error | null = null
const refetchAccounting = vi.fn()
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
    useAccounting: () =>
      accountingError
        ? { data: undefined, isLoading: false, error: accountingError, refetch: refetchAccounting }
        : { data: snapshot, isLoading: false, error: null, refetch: refetchAccounting },
    useUpdateTokenBudget: () => ({ mutate, ...mutationState }),
  }
})

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  // The page names each agent's colour from the roster; the roster is not what these test.
  useAgents: () => ({ data: [], isLoading: false }),
}))

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

/** Leaves the limit field with `value` typed in it, which is what saves it. */
function commitLimit(value: string) {
  const field = screen.getByLabelText('After')
  fireEvent.change(field, { target: { value } })
  fireEvent.blur(field)
}

function toastTitles(): string[] {
  return useToastStore.getState().items.map((item) => item.title)
}

describe('accounting presentation', () => {
  beforeEach(() => {
    snapshot = baseSnapshot()
    mutate.mockReset()
    useToastStore.setState({ items: [] })
    mutationState = {
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
      variables: undefined,
    }
  })

  it('shows totals, unavailable usage, allowance precedence, and exhaustion control', () => {
    render(<BudgetsSection />)

    expect(within(screen.getByText('Tokens').closest('.aw-usage-tile') as HTMLElement).getByTitle('1,234 tokens')).toHaveTextContent('1.2K')
    expect(screen.getByTestId('budgets-display')).toHaveTextContent('Rate-limit allowance')
    expect(screen.queryByText(/API-equivalent estimate/)).not.toBeInTheDocument()
    expect(screen.getByTestId('budgets-caption')).toHaveTextContent('2 measured turns · 1 unavailable')
    const codex = screen.getByTestId('budget-agent-codex')
    expect(codex).toHaveTextContent('Unavailable')
    expect(codex).toHaveTextContent('1 unavailable')
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
    render(<BudgetsSection />)
    expect(screen.getByTestId('budgets-display')).toHaveTextContent('$0.0125 API-equivalent estimate')
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
    render(<BudgetsSection />)
    expect(screen.getByTestId('budgets-display')).toHaveTextContent(
      '$0.0125 API-equivalent estimate — excludes 10 turns with no reported cost',
    )
  })

  it('says how many turns the spent figure could not price', () => {
    render(<BudgetsSection />)
    expect(screen.getByText('API-equivalent; 1 turns could not be priced')).toBeInTheDocument()
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
    render(<BudgetsSection />)

    expect(screen.getByText(/Weekly allowance exhausted/)).toBeInTheDocument()
    expect(screen.queryByText(/\{"status"/)).not.toBeInTheDocument()
  })

  it('lists what the Hub spent outside the turns, one line per worker kind, after the agents (F240)', () => {
    snapshot.workers = [
      { kind: 'checkpoint', input_tokens: 400, output_tokens: 100, total_tokens: 500, measured_calls: 2, unmeasured_calls: 0, api_equivalent_usd_micros: null },
      { kind: 'conversation_title', input_tokens: 50, output_tokens: 10, total_tokens: 60, measured_calls: 1, unmeasured_calls: 1, api_equivalent_usd_micros: null },
    ]
    render(<BudgetsSection />)

    // Every worker call that ran: measured, credited or not (F665, D1).
    expect(screen.getByTestId('budgets-caption')).toHaveTextContent('2 measured turns · 4 Hub job calls · 1 unavailable')
    const lines = screen.getByLabelText('Usage by worker').querySelectorAll('li')
    expect([...lines].map((line) => line.getAttribute('data-testid'))).toEqual(['budget-worker-checkpoint', 'budget-worker-conversation_title'])
    expect(screen.getByTestId('budget-worker-checkpoint')).toHaveTextContent('Checkpoints')
    expect(screen.getByTestId('budget-worker-checkpoint')).toHaveTextContent('500 tokens')
    expect(screen.getByTestId('budget-worker-conversation_title')).toHaveTextContent('Conversation titles')
    expect(screen.getByTestId('budget-worker-conversation_title')).toHaveTextContent('1 unavailable')
    // After the agents, never ahead of them.
    const agents = screen.getByLabelText('Usage by agent')
    expect(agents.compareDocumentPosition(screen.getByLabelText('Usage by worker')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows a Copilot worker line in credits, not as unavailable (F665)', () => {
    snapshot.workers = [
      { kind: 'checkpoint', input_tokens: null, output_tokens: null, total_tokens: null, measured_calls: 0, credited_calls: 1, unmeasured_calls: 0, api_equivalent_usd_micros: null, ai_nano_aiu: 1_102_140_000, premium_requests: 1 },
    ]
    render(<BudgetsSection />)
    const line = screen.getByTestId('budget-worker-checkpoint')
    expect(line).toHaveTextContent('1.10 AI credits · 1 premium request')
    expect(line).not.toHaveTextContent('Unavailable')
    expect(screen.getByTestId('budgets-caption')).toHaveTextContent('2 measured turns · 1 Hub job call · 1 unavailable')
  })

  it('names Copilot AI credits as the headline unit when they are the only spend reported (F665)', () => {
    expect(
      accountingDisplayLabel({ kind: 'credits', label: 'AI credits', runner: 'copilot', ai_nano_aiu: 5, premium_requests: 1 }),
    ).toBe('Copilot AI credits · no allowance reported')
  })

  it("shows a stopped turn's interrupted call as an estimate, not counted (F697)", () => {
    snapshot.project = { ...snapshot.project, estimated_input_tokens: 333_102 }
    snapshot.agents = snapshot.agents.map((agent) =>
      agent.agent === 'codex' ? { ...agent, estimated_input_tokens: 333_102 } : agent,
    )
    render(<BudgetsSection />)
    expect(screen.getByTestId('budgets-estimate')).toHaveTextContent(
      '≈333,102 input tokens, not measured, not counted against the limit',
    )
    // The measured total stays as it was; the estimate is never folded into it.
    expect(within(screen.getByText('Tokens').closest('.aw-usage-tile') as HTMLElement).getByTitle('1,234 tokens')).toHaveTextContent('1.2K')
    expect(screen.getByTestId('budget-agent-codex')).toHaveTextContent('1 unavailable · ≈333,102 input tokens, not measured')
  })

  it('shows no estimate line when no turn was estimated', () => {
    render(<BudgetsSection />)
    expect(screen.queryByText(/not measured/)).toBeNull()
  })

  it('keeps the turns-only caption when there are no worker calls', () => {
    render(<BudgetsSection />)
    expect(screen.getByTestId('budgets-caption')).toHaveTextContent(/^2 measured turns · 1 unavailable$/)
    expect(screen.queryByLabelText('Usage by worker')).toBeNull()
  })

  it('updates or turns off the project token limit', () => {
    snapshot.budget = { limit_tokens: 40_000_000, used_tokens: 1234, remaining_tokens: 39_998_766, exhausted: false }
    render(<BudgetsSection />)
    expect(screen.getByLabelText('After')).toHaveValue('40')
    commitLimit('12.5')
    expect(mutate).toHaveBeenCalledWith(12_500_000, expect.anything())

    fireEvent.click(screen.getByRole('switch', { name: 'Pause agents working on their own' }))
    expect(mutate).toHaveBeenLastCalledWith(null, expect.anything())
  })

  it('turns a limit on at a round amount above what is already used', () => {
    snapshot.budget = { limit_tokens: null, used_tokens: 1234, remaining_tokens: null, exhausted: false }
    render(<BudgetsSection />)
    expect(screen.queryByLabelText('After')).toBeNull()
    fireEvent.click(screen.getByRole('switch', { name: 'Pause agents working on their own' }))
    expect(mutate).toHaveBeenCalledWith(1_000_000, expect.anything())
  })

  describe('the limit control reports what happened (contextual-navigation 4.7)', () => {
    beforeEach(() => {
      snapshot.budget = { limit_tokens: 40_000_000, used_tokens: 1234, remaining_tokens: 39_998_766, exhausted: false }
    })

    it('refuses a value that is not a limit, and says why, without calling the API', () => {
      render(<BudgetsSection />)
      commitLimit('-5')
      // The whole defect: this used to do nothing at all, which from the operator's chair is
      // indistinguishable from a save that silently failed.
      expect(mutate).not.toHaveBeenCalled()
      expect(screen.getByRole('alert')).toHaveTextContent('Millions of tokens, like 40 or 12.5.')
      expect(screen.getByLabelText('After')).toHaveAttribute('aria-invalid', 'true')
    })

    it('refuses an empty field rather than saving nothing (the switch turns the limit off)', () => {
      render(<BudgetsSection />)
      commitLimit('')
      expect(mutate).not.toHaveBeenCalled()
      expect(screen.getByRole('alert')).toHaveTextContent('Millions of tokens')
    })

    it('clears its objection as soon as the operator answers it', () => {
      render(<BudgetsSection />)
      const input = screen.getByLabelText('After')
      fireEvent.change(input, { target: { value: '0' } })
      expect(screen.getByRole('alert')).toBeInTheDocument()
      fireEvent.change(input, { target: { value: '50' } })
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(input).not.toHaveAttribute('aria-invalid')
    })

    it('confirms a saved limit', () => {
      render(<BudgetsSection />)
      commitLimit('50')
      mutate.mock.calls[0][1].onSuccess()
      expect(toastTitles()).toContain('Agents pause after 50M tokens')
    })

    it('says a removal was a removal, not a save', () => {
      render(<BudgetsSection />)
      fireEvent.click(screen.getByRole('switch', { name: 'Pause agents working on their own' }))
      mutate.mock.calls[0][1].onSuccess()
      expect(toastTitles()).toContain('Token limit off: agents are no longer paused')
    })

    it('reports a server failure in the section', () => {
      mutationState = {
        ...mutationState,
        isError: true,
        error: new Error('nope'),
        variables: 5000,
      }
      render(<BudgetsSection />)
      expect(screen.getByRole('alert')).toHaveTextContent(/not saved|could not be saved/)
    })

    it('does not offer the controls while a save is in flight', () => {
      mutationState = { ...mutationState, isPending: true }
      render(<BudgetsSection />)
      expect(screen.getByRole('switch', { name: 'Pause agents working on their own' })).toBeDisabled()
      expect(screen.getByLabelText('After')).toBeDisabled()
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

  describe('AI credits on the Budgets page (task 1.18)', () => {
    it('adds a line with AI credits and premium requests when the project reports them', () => {
      snapshot = {
        ...baseSnapshot(),
        project: {
          ...baseSnapshot().project,
          ai_nano_aiu: 275_856_000,
          premium_requests: 1.5,
        } as unknown as AccountingSnapshot['project'],
      }
      render(<BudgetsSection />)
      expect(screen.getByTestId('budgets-credits')).toHaveTextContent(
        '0.28 AI credits · 1.5 premium requests (Copilot), not counted against the limit',
      )
    })

    it('shows no credits line when the project has nothing to report (control)', () => {
      const { container } = render(<BudgetsSection />)
      expect(container.textContent).not.toContain('AI credits')
    })

    it('adds AI credits to an agent’s line only for the agent that reports them', () => {
      snapshot = baseSnapshot()
      snapshot.agents = [
        { ...snapshot.agents[0], ai_nano_aiu: 275_856_000 } as unknown as AccountingSnapshot['agents'][number],
        snapshot.agents[1],
      ]
      render(<BudgetsSection />)
      expect(screen.getByTestId('budget-agent-claude')).toHaveTextContent('0.28 AI credits')
      expect(screen.getByTestId('budget-agent-codex')).not.toHaveTextContent('AI credits')
    })
  })
})

describe('Budgets when the usage cannot be read', () => {
  it('says so with a Retry instead of a skeleton that never resolves', () => {
    accountingError = new Error('the Hub is down')
    try {
      render(<BudgetsSection />)
      expect(screen.queryByLabelText('Loading budgets')).toBeNull()
      expect(screen.getByRole('alert')).toHaveTextContent("This project's usage could not be read.")
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
      expect(refetchAccounting).toHaveBeenCalled()
    } finally {
      accountingError = null
    }
  })
})
