import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { SpecResolvedProposals } from '@/components/spec/SpecResolvedProposals'
import type { SpecEditProposal } from '@/api/spec'

/** Decided proposals (slice remaining-hidden-data), in the route's order: newest decision first. */

function proposal(id: string, status: SpecEditProposal['status'], reason: string): SpecEditProposal {
  return {
    id, unit_kind: 'requirement', unit_key: 'r1', change_kind: 'modify', position_after_key: null,
    proposed_payload: { key: 'r1', statement: 'It MUST be empty.' }, previous_payload: null, status,
    proposer_actor_kind: 'agent', proposer_actor_name: 'builder', created_at: '2026-10-15T09:00:00Z',
    resolved_at: '2026-10-15T10:00:00Z', resolved_by_actor_name: 'operator', resolution_reason: reason,
  }
}

const RESOLVED = [proposal('sp-no', 'rejected', 'too narrow'), proposal('sp-ok', 'accepted', 'matches')]

vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecResolvedProposals: () => ({ data: { proposals: RESOLVED }, error: null }),
}))

describe('SpecResolvedProposals', () => {
  it('lists each decided proposal with its outcome, who decided and why, in the route’s order', () => {
    render(<SpecResolvedProposals path="spec/changes/x/spec.json" />)
    fireEvent.click(screen.getByTestId('spec-proposals-resolved-toggle'))
    const rows = screen.getAllByTestId(/^spec-proposal-resolved-/).map((r) => r.getAttribute('data-testid'))
    expect(rows).toEqual(['spec-proposal-resolved-sp-no', 'spec-proposal-resolved-sp-ok'])
    const rejected = screen.getByTestId('spec-proposal-resolved-sp-no')
    expect(rejected).toHaveTextContent('rejected')
    expect(rejected).toHaveTextContent('decided by operator')
    expect(rejected).toHaveTextContent('Why: too narrow')
    expect(rejected).toHaveTextContent('It MUST be empty.')
  })
})
