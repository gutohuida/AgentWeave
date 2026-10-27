import { useState } from 'react'
import { readableApiError } from '@/api/client'
import {
  useDecideEvidence,
  useOverturnEvidence,
  useSpecEvidence,
  type EvidenceDecisionResult,
  type EvidencePiece,
} from '@/api/spec'

/**
 * The evidence recorded for one requirement, with the operator's decision on each awaiting piece
 * and an Overturn control on each decided one (F692: only the operator reverses a decision, and
 * only with a reason).
 *
 * The coverage bar says "N awaiting review"; this is where the sentence is answered. Pieces are in
 * the route's order, oldest first, and the last is labelled *latest* — most recently recorded, which
 * is all that order says (a merge groups by task and branch, not by requirement).
 */
interface EvidencePiecesProps {
  path: string
  identifier: string
}

/** Each outcome its own colour, so a held piece (K: sent back without being named as failing) never
 *  reads as a rejected one. */
const OUTCOME_TONE: Record<string, string> = {
  accepted: 'var(--green)',
  rejected: 'var(--red)',
  held: 'var(--text-3)',
  awaiting: 'var(--amber)',
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
  const overturn = useOverturnEvidence(path, identifier)
  const [overturning, setOverturning] = useState(false)
  const [overturnReason, setOverturnReason] = useState('')

  const awaiting = piece.review_state === 'awaiting'
  const decided = piece.review_state === 'accepted' || piece.review_state === 'rejected'
  const reverse = piece.review_state === 'accepted' ? 'Reject' : 'Accept'
  // What the last decision here did to an approved task (F730 item 8), said rather than implied.
  const answered: EvidenceDecisionResult | undefined = overturn.data ?? decide.data
  const reopen = answered?.task_reopen
  // Still being recorded: its run is live, so a decision waits (not K's `held` outcome).
  const recording = piece.recording_run_live === true
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
        {piece.task_id ? ` · ${piece.task_id}` : ''} ·{' '}
        <span
          data-testid={`evidence-outcome-${piece.id}`}
          data-state={piece.review_state}
          style={{ color: OUTCOME_TONE[piece.review_state] ?? 'inherit' }}
        >
          {piece.review_state}
        </span>
        {piece.latest_review && !awaiting
          ? ` by ${piece.latest_review.actor}${
              piece.latest_review.reason ? `: ${piece.latest_review.reason}` : ''
            }`
          : ''}
      </div>
      {outside && <div style={{ color: 'var(--amber)' }}>this run also wrote outside this tree</div>}
      {piece.review_state === 'held' && (
        <div data-testid={`evidence-held-at-commit-${piece.id}`} style={{ color: 'var(--text-3)' }}>
          not rejected: its task was sent back without naming this piece as failing, so it counts
          for nothing until its author records it again at the next commit
        </div>
      )}
      {awaiting && recording && (
        <div data-testid={`evidence-held-${piece.id}`} style={{ color: 'var(--amber)' }}>
          still being recorded by run {piece.run_id}; decide once it ends
        </div>
      )}
      {awaiting && (
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            style={button}
            disabled={recording || decide.isPending}
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
                disabled={recording || decide.isPending || reason.trim() === ''}
                onClick={() =>
                  decide.mutate({ id: piece.id, decision: 'rejected', reason: reason.trim() })
                }
              >
                Reject
              </button>
            </>
          ) : (
            <button type="button" style={button} disabled={recording} onClick={() => setRejecting(true)}>
              Reject…
            </button>
          )}
        </div>
      )}
      {decided && (
        <div className="flex flex-wrap items-center gap-1.5">
          {overturning ? (
            <>
              <input
                aria-label="Reason for overturning"
                value={overturnReason}
                onChange={(event) => setOverturnReason(event.target.value)}
                placeholder="why the decision was wrong"
              />
              <button
                type="button"
                style={button}
                disabled={overturn.isPending || overturnReason.trim() === ''}
                onClick={() =>
                  overturn.mutate(
                    { id: piece.id, reason: overturnReason.trim() },
                    {
                      onSuccess: () => {
                        setOverturning(false)
                        setOverturnReason('')
                      },
                    },
                  )
                }
              >
                {reverse} instead
              </button>
            </>
          ) : (
            <button type="button" style={button} onClick={() => setOverturning(true)}>
              Overturn…
            </button>
          )}
        </div>
      )}
      {reopen && (
        <div data-testid={`evidence-reopen-${piece.id}`} style={{ color: 'var(--text-3)' }}>
          {reopen.reopened ? `${reopen.task} reopened for revision` : reopen.reason}
        </div>
      )}
      {overturn.isError && (
        <div
          role="alert"
          data-testid={`evidence-overturn-error-${piece.id}`}
          style={{ color: 'var(--red)' }}
        >
          {readableApiError(overturn.error, 'The Hub refused to overturn this decision.')}
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
