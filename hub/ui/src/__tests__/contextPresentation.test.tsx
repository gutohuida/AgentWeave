import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  CONTEXT_CRITICAL_PERCENT,
  CONTEXT_WARNING_PERCENT,
  normalizeContextUsage,
  presentContextUsage,
} from '@/components/context/contextPresentation'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'

const measured = {
  status: 'measured',
  source: 'codex_rollout',
  basis: 'provider_context',
  context_tokens: 250,
  limit_tokens: 1000,
  percent: 25,
  model: 'gpt-test',
  session_id: 'session-1',
  observed_at: 1000,
  breakdown: { input_tokens: 200, reasoning_tokens: 50 },
}

describe('canonical context presentation', () => {
  it('retains canonical fields and derives measured percentage from operands', () => {
    expect(normalizeContextUsage({ ...measured, percent: 99 })).toEqual(measured)
    expect(presentContextUsage(measured)).toMatchObject({
      label: '25%',
      detail: '250 / 1,000 tokens',
      percent: 25,
      severity: 'normal',
      showBar: true,
      isPolicyWarning: false,
    })
  })

  it('applies warning and critical policy only to measured samples', () => {
    const atWarning = presentContextUsage({
      ...measured,
      context_tokens: CONTEXT_WARNING_PERCENT,
      limit_tokens: 100,
    })
    const atCritical = presentContextUsage({
      ...measured,
      context_tokens: CONTEXT_CRITICAL_PERCENT,
      limit_tokens: 100,
    })
    const estimated = presentContextUsage({
      ...measured,
      status: 'estimated',
      context_tokens: 95,
      limit_tokens: 100,
    })

    expect(atWarning).toMatchObject({ severity: 'warning', isPolicyWarning: true })
    expect(atCritical).toMatchObject({ severity: 'critical', isPolicyWarning: true })
    expect(estimated).toMatchObject({
      label: '95% estimated',
      severity: 'neutral',
      isPolicyWarning: false,
    })
  })

  it('shows token-only samples without inventing a percentage', () => {
    expect(presentContextUsage({
      ...measured,
      context_tokens: 42000,
      limit_tokens: null,
      percent: null,
    })).toMatchObject({
      label: '42,000 tokens',
      detail: 'Unknown context limit',
      percent: null,
      severity: 'neutral',
      showBar: false,
    })
  })

  it.each([
    ['unavailable', 'Context unavailable', 'Waiting for a context sample'],
    ['unsupported', 'Context unsupported', 'This runner does not report context usage'],
  ] as const)('renders %s as a distinct neutral state', (status, label, detail) => {
    expect(presentContextUsage({
      status,
      source: 'runner',
      observed_at: 1000,
    })).toMatchObject({
      label,
      detail,
      percent: null,
      severity: 'neutral',
      showBar: false,
    })
  })

  it('normalizes legacy token, limit, ratio, and timestamp aliases', () => {
    expect(normalizeContextUsage({
      tokens_used: 50,
      tokens_limit: 200,
      updated_at: '1970-01-01T00:16:40Z',
      model: 'legacy-model',
    })).toMatchObject({
      status: 'measured',
      source: 'legacy',
      basis: 'provider_context',
      context_tokens: 50,
      limit_tokens: 200,
      percent: 25,
      observed_at: 1000,
      model: 'legacy-model',
    })

    expect(normalizeContextUsage({
      context_usage_ratio: 0.8,
      updated_at: 1001,
    })).toMatchObject({
      status: 'measured',
      basis: 'provider_reported_ratio',
      percent: 80,
    })
  })

  it('degrades contradictory legacy operands to token-only and unusable data to unavailable', () => {
    expect(normalizeContextUsage({
      tokens_used: 50,
      tokens_limit: 100,
      percent: 10,
    })).toMatchObject({
      status: 'measured',
      context_tokens: 50,
      limit_tokens: null,
      percent: null,
    })
    expect(normalizeContextUsage({ surprise: true })).toMatchObject({
      status: 'unavailable',
      percent: null,
      context_tokens: null,
    })
    expect(normalizeContextUsage({ tokens_used: 0 })).toMatchObject({
      status: 'unavailable',
    })
  })

  it('treats a legacy zero percentage as unavailable, not a measured zero', () => {
    // Older CLIs wrote `{"percent": 0}` on every session reset and Kimi
    // compaction. Trusting it paints a green 0% bar for an unmeasured session.
    const legacyReset = {
      agent: 'a',
      percent: 0,
      warning: false,
      critical: false,
      updated_at: '2026-07-29T10:00:00+00:00',
    }
    expect(normalizeContextUsage(legacyReset)).toMatchObject({
      status: 'unavailable',
      percent: null,
      basis: null,
      context_tokens: null,
    })
    expect(presentContextUsage(legacyReset)).toMatchObject({
      label: 'Context unavailable',
      severity: 'neutral',
      showBar: false,
      isPolicyWarning: false,
    })

    // A positive legacy percentage is still a real measurement.
    expect(normalizeContextUsage({ percent: 75 })).toMatchObject({
      status: 'measured',
      basis: 'provider_reported_ratio',
      percent: 75,
    })

    // A canonical sample may legitimately declare a provider-reported zero.
    expect(normalizeContextUsage({
      status: 'measured',
      source: 'provider',
      basis: 'provider_reported_ratio',
      percent: 0,
      observed_at: 1000,
    })).toMatchObject({
      status: 'measured',
      basis: 'provider_reported_ratio',
      percent: 0,
    })
  })

  it('replaces a previous session bar with the new-session unavailable state', () => {
    const { rerender } = render(<ContextUsageIndicator value={measured} compact />)
    expect(screen.getByTestId('context-bar')).toBeInTheDocument()

    rerender(
      <ContextUsageIndicator
        value={{
          status: 'unavailable',
          source: 'new_session',
          session_id: 'session-2',
          observed_at: 1001,
        }}
        compact
      />
    )

    expect(screen.queryByTestId('context-bar')).not.toBeInTheDocument()
    expect(screen.getByText('Context unavailable')).toBeInTheDocument()
    expect(screen.getByTestId('context-usage')).toHaveAttribute(
      'data-context-status',
      'unavailable',
    )
  })
})
