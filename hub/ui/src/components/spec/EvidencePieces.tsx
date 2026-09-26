import { useState } from 'react'
import { readableApiError } from '@/api/client'
import { useDecideEvidence, useSpecEvidence, type EvidencePiece } from '@/api/spec'

/**
 * The evidence recorded for one requirement, with the operator's decision on each awaiting piece.
 *
 * The coverage bar says "N awaiting review"; this is where the sentence is answered. Pieces are in
 * the route's order, oldest first, and the last is labelled *latest* — most recently recorded, which
 * is all that order says (a merge groups by task and branch, not by requirement).
 */
interface EvidencePiecesProps {
  path: string
  identifier: string
}

const button = {
  background: 'none',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '0 6px',
  color: 'var(--text-2)',
  cursor: 'pointer',
} as const

function Piece({
  piece,
  latest,
  path,
  identifier,
}: {
  piece: EvidencePiece
  latest: boolean
  path: string
  identifier: string
}) {
  const decide = useDecideEvidence(path, identifier)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')

  const awaiting = piece.review_state === 'awaiting'
  const held = piece.recording_run_live === true
  const commit = piece.footprint?.kind === 'git' ? piece.footprint.commit_sha : null
  const outside = (piece.footprint?.outside_workspace_writes ?? []).length > 0

  return (
    <li data-testid={`evidence-piece-${piece.id}`} className="flex flex-col gap-0.5">
      <div>
        {latest && <strong data-testid={`evidence-latest-${piece.id}`}>latest · </strong>}
        {piece.summary || 'no summary'} — {piece.actor}
        {piece.locator ? ` · ${piece.locator}` : ''}
        {commit
          ? ` · ${commit.slice(0, 12)} on ${piece.footprint?.branch ?? 'no branch'}`
          : ' · no commit'}
        {piece.task_id ? ` · ${piece.task_id}` : ''} · {piece.review_state}
        {piece.latest_review && !awaiting
          ? ` by ${piece.latest_review.actor}${
              piece.latest_review.reason ? `: ${piece.latest_review.reason}` : ''
            }`
          : ''}
      </div>
      {outside && <div style={{ color: 'var(--amber)' }}>this run also wrote outside this tree</div>}
      {awaiting && held && (
        <div data-testid={`evidence-held-${piece.id}`} style={{ color: 'var(--amber)' }}>
          still being recorded by run {piece.run_id}; decide once it ends
        </div>
      )}
      {awaiting && (
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            style={button}
            disabled={held || decide.isPending}
            onClick={() => decide.mutate({ id: piece.id, decision: 'accepted', reason: '' })}
          >
            Accept
          </button>
          {commit && (
            <span data-testid={`evidence-merge-note-${piece.id}`}>
              Accepting may merge commit {commit.slice(0, 12)} into main for an approved task that
              serves this requirement and is waiting on it.
            </span>
          )}
          {rejecting ? (
            <>
              <input
                aria-label="Reason for rejecting"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="why"
              />
              <button
                type="button"
                style={button}
                disabled={held || decide.isPending || reason.trim() === ''}
                onClick={() =>
                  decide.mutate({ id: piece.id, decision: 'rejected', reason: reason.trim() })
                }
              >
                Reject
              </button>
            </>
          ) : (
            <button type="button" style={button} disabled={held} onClick={() => setRejecting(true)}>
              Reject…
            </button>
          )}
        </div>
      )}
      {decide.isError && (
        <div role="alert" data-testid={`evidence-error-${piece.id}`} style={{ color: 'var(--red)' }}>
          {readableApiError(decide.error, 'The Hub refused this decision.')}
        </div>
      )}
    </li>
  )
}

export function EvidencePieces({ path, identifier }: EvidencePiecesProps) {
  const { data, error } = useSpecEvidence(path, identifier, true)

  if (error) {
    return (
      <div role="alert" style={{ color: 'var(--red)' }}>
        {readableApiError(error, 'Could not read this requirement’s evidence.')}
      </div>
    )
  }
  if (!data) return <div>Loading evidence…</div>
  const pieces = data.evidence
  return (
    <ul className="flex flex-col gap-1" data-testid={`evidence-pieces-${identifier}`}>
      {pieces.map((piece, index) => (
        <Piece
          key={piece.id}
          piece={piece}
          latest={index === pieces.length - 1}
          path={path}
          identifier={identifier}
        />
      ))}
    </ul>
  )
}
