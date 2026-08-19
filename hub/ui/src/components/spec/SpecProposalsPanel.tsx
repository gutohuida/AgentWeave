import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import {
  useAcceptSpecProposal,
  useRejectSpecProposal,
  useSpecProposals,
  type SpecEditProposal,
} from '@/api/spec'

/**
 * Pending proposals against the open document (design F1-F3,
 * `openspec/changes/2026-08-17-authoring-rigor-and-scope`). At `contract`/`gate` rigor an agent's
 * submission no longer writes the document directly — it lands here instead, one row per changed
 * requirement plus one for everything else, until the operator accepts or rejects it.
 *
 * Grouped by requirement rather than interleaved into `SpecCoverageBar`'s own rows: a proposal is
 * not yet real, and a reader must not mistake a proposed statement for the document's actual one.
 * Shown on the same document view as the coverage bar it sits beneath, so a pending change is still
 * discoverable without leaving the document — not a separate screen or a cross-document inbox.
 */
export function SpecProposalsPanel({ path }: { path: string }) {
  const { data } = useSpecProposals(path)
  const accept = useAcceptSpecProposal()
  const reject = useRejectSpecProposal()
  const [error, setError] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  const proposals = data?.proposals ?? []
  if (proposals.length === 0) return null

  async function onAccept(proposal: SpecEditProposal) {
    setError(null)
    try {
      await accept.mutateAsync({ path, proposalId: proposal.id })
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function onReject(proposal: SpecEditProposal) {
    setError(null)
    try {
      await reject.mutateAsync({ path, proposalId: proposal.id, reason })
      setRejecting(null)
      setReason('')
    } catch (err) {
      setError(describeError(err))
    }
  }

  const busy = accept.isPending || reject.isPending

  return (
    <div
      className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
      data-testid="spec-proposals-panel"
    >
      <div className="flex items-center gap-1.5" style={{ color: 'var(--text-3)' }}>
        <Icon name="edit" size={13} />
        <span>
          {proposals.length} pending {proposals.length === 1 ? 'proposal' : 'proposals'} — this
          document does not change until you accept one
        </span>
      </div>

      <ul className="flex flex-col gap-1.5">
        {proposals.map((proposal) => (
          <li
            key={proposal.id}
            className="flex flex-col gap-1 rounded-[var(--radius-sm)] p-2"
            style={{ background: 'var(--surface-2)' }}
            data-testid={`proposal-row-${proposal.unit_key}`}
          >
            <div className="flex items-center gap-1.5">
              <span
                className="rounded-full px-1.5 py-0.5"
                style={{ background: 'var(--surface-1)', color: 'var(--text-3)', fontSize: 10 }}
              >
                {proposal.change_kind}
              </span>
              <span style={{ color: 'var(--text-2)' }}>
                {proposal.unit_kind === 'metadata' ? 'Summary / problem / scope' : proposal.unit_key}
              </span>
              {proposal.change_kind === 'add' && (
                <span style={{ color: 'var(--text-3)' }}>
                  — will appear{' '}
                  {proposal.position_after_key
                    ? `after ${proposal.position_after_key}`
                    : 'at the top'}
                </span>
              )}
              {proposal.proposer_actor_name && (
                <span style={{ color: 'var(--text-3)' }}>
                  proposed by {proposal.proposer_actor_name}
                </span>
              )}
              <div className="flex-1" />
              <button
                type="button"
                disabled={busy}
                onClick={() => onAccept(proposal)}
                className="rounded-[var(--radius-sm)] px-2 py-0.5 hover:bg-[var(--row-hover)]"
                style={{ color: 'var(--green)' }}
              >
                Accept
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setRejecting(rejecting === proposal.id ? null : proposal.id)}
                className="rounded-[var(--radius-sm)] px-2 py-0.5 hover:bg-[var(--row-hover)]"
                style={{ color: 'var(--red)' }}
              >
                Reject
              </button>
            </div>

            {proposal.unit_kind === 'requirement' && proposal.change_kind !== 'remove' && (
              <div style={{ color: 'var(--text-2)' }}>
                {String((proposal.proposed_payload as { statement?: string }).statement ?? '')}
              </div>
            )}

            {rejecting === proposal.id && (
              <div className="flex items-center gap-1.5">
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Reason (optional)"
                  className="flex-1 rounded-[var(--radius-sm)] px-1.5 py-0.5"
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-2)',
                  }}
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onReject(proposal)}
                  className="rounded-[var(--radius-sm)] px-2 py-0.5"
                  style={{ color: 'var(--red)' }}
                >
                  Confirm reject
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {error && (
        <div className="flex items-start gap-1.5" style={{ color: 'var(--amber)' }}>
          <Icon name="warning" size={13} />
          <span>{error}</span>
        </div>
      )}
    </div>
  )
}

/** `ApiError.message` is the response body verbatim — the same parse-back-out pattern
 *  `SpecPhaseBar`'s rigor-refusal handling already uses. */
function describeError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err)
  try {
    const detail = (JSON.parse(raw) as { detail?: { message?: string } | string }).detail
    if (typeof detail === 'string') return detail
    return detail?.message ?? 'That change was refused.'
  } catch {
    return raw || 'That change was refused.'
  }
}
