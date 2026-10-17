import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { StatePill, type Tone } from '@/components/common/StatePill'
import { Expander } from '@/components/common/Expander'
import { useSpecResolvedProposals } from '@/api/spec'
import { hubDate } from '@/lib/hubTime'

const TONE: Record<string, Tone> = {
  accepted: 'green',
  rejected: 'red',
  withdrawn: 'neutral',
  stale: 'amber',
  superseded: 'neutral',
}

/**
 * Proposals already decided on this document, with who decided, when and why (slice
 * remaining-hidden-data). The Hub kept every resolution and its reason; only the pending ones were
 * ever shown, so why a proposed wording did not land could not be read anywhere.
 */
export function SpecResolvedProposals({ path }: { path: string }) {
  const { data, error } = useSpecResolvedProposals(path)
  const [open, setOpen] = useState(false)
  if (error) {
    return (
      <p className="px-3 text-[11px]" style={{ color: 'var(--text-3)' }}>
        This document’s decided proposals could not be read.
      </p>
    )
  }
  const proposals = data?.proposals ?? []
  if (proposals.length === 0) return null
  return (
    <div className="flex shrink-0 flex-col gap-1.5 px-3 py-1 text-xs" data-testid="spec-proposals-resolved">
      <button
        type="button"
        className="aw-link"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        data-testid="spec-proposals-resolved-toggle"
      >
        <Icon name="chevron_right" size={12} />
        {proposals.length} decided {proposals.length === 1 ? 'proposal' : 'proposals'}
      </button>
      <Expander open={open}>
        <ul className="flex flex-col gap-1.5">
          {proposals.map((proposal) => (
            <li
              key={proposal.id}
              className="flex flex-col gap-1 rounded-[var(--radius-sm)] p-2"
              style={{ background: 'var(--surface-2)' }}
              data-testid={`spec-proposal-resolved-${proposal.id}`}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <StatePill tone={TONE[proposal.status] ?? 'neutral'}>{proposal.status}</StatePill>
                <span style={{ color: 'var(--text-2)' }}>
                  {proposal.change_kind}{' '}
                  {proposal.unit_kind === 'metadata' ? 'summary / problem / scope' : proposal.unit_key}
                </span>
                <span style={{ color: 'var(--text-3)' }}>
                  {proposal.proposer_actor_name ? `proposed by ${proposal.proposer_actor_name}` : ''}
                  {proposal.resolved_by_actor_name ? ` · decided by ${proposal.resolved_by_actor_name}` : ''}
                  {proposal.resolved_at ? ` · ${hubDate(proposal.resolved_at).toLocaleString()}` : ''}
                </span>
              </div>
              {typeof proposal.proposed_payload?.statement === 'string' ? (
                <p style={{ color: 'var(--text-2)' }}>“{proposal.proposed_payload.statement}”</p>
              ) : null}
              {proposal.resolution_reason ? (
                <p style={{ color: 'var(--text)' }}>
                  <span style={{ color: 'var(--text-3)' }}>Why: </span>
                  {proposal.resolution_reason}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </Expander>
    </div>
  )
}
