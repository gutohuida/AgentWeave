import { useState } from 'react'

import { readableApiError } from '@/api/client'
import { useDecideEvidencePiece, useLinkTaskRequirements, useTaskChecks } from '@/api/tasks'
import { checksWait, waitsOnChecks, type GateBody } from '@/components/tasks/gateRefusal'
import { useElapsedSeconds } from '@/hooks/useElapsedSeconds'

/**
 * What a refused approval or landing says it waits on, and the action that clears each cause beside
 * it (`every-task-can-always-be-moved-on`, FR-11, FR-12): Accept or Reject on evidence awaiting a
 * decision, a link for a requirement the task does not serve, and a wait with no override while the
 * project's checks are still running.
 */

const short = (sha?: string) => (sha ? sha.slice(0, 7) : 'an unnamed commit')

/** Evidence the landing waits on a decision for, each with Accept and Reject beside it. */
function AwaitingEvidence({ taskId, body }: { taskId: string; body: GateBody }) {
  const decide = useDecideEvidencePiece()
  const [decided, setDecided] = useState<Record<string, string>>({})
  const [failure, setFailure] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const pieces = body.unaccepted ?? []
  if (pieces.length === 0) return null

  const act = (id: string, decision: 'accepted' | 'rejected') => {
    setFailure(null)
    decide.mutate(
      {
        id,
        decision,
        reason: reason.trim() || (decision === 'accepted' ? 'accepted from the landing refusal' : ''),
      },
      {
        onSuccess: () => setDecided((current) => ({ ...current, [id]: decision })),
        onError: (error: unknown) =>
          setFailure(readableApiError(error, 'The Hub could not record that decision.')),
      },
    )
  }

  return (
    <div data-testid={`task-landing-awaiting-${taskId}`} className="space-y-1 text-[11px]">
      <p style={{ color: 'var(--text-2)' }}>
        Landing waits on evidence nobody has judged. Decide it here, then press Land again.
      </p>
      <ul className="space-y-1">
        {pieces.map((piece) => {
          const id = piece.evidence_id ?? ''
          const done = decided[id]
          return (
            <li key={id} className="flex flex-wrap items-center gap-2">
              <span data-testid={`task-landing-awaiting-piece-${id}`}>
                {piece.identifier ?? 'A requirement'} at {short(piece.commit_sha)}
                {piece.recorded_by_another_task ? `, recorded by ${piece.recorded_by_task}` : ''}
              </span>
              {done ? (
                <span style={{ color: done === 'accepted' ? 'var(--green)' : 'var(--amber)' }}>
                  {done === 'accepted' ? 'Accepted' : 'Rejected'}
                </span>
              ) : (
                <>
                  <button
                    type="button"
                    data-testid={`task-landing-accept-${id}`}
                    disabled={decide.isPending}
                    className="px-2 py-0.5 rounded"
                    style={{ color: 'var(--green)', border: '1px solid var(--border)' }}
                    onClick={() => act(id, 'accepted')}
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    data-testid={`task-landing-reject-${id}`}
                    disabled={decide.isPending || !reason.trim()}
                    title={reason.trim() ? undefined : 'Say why below to reject it'}
                    className="px-2 py-0.5 rounded"
                    style={{
                      color: 'var(--red)',
                      border: '1px solid var(--border)',
                      opacity: decide.isPending || !reason.trim() ? 0.45 : 1,
                      cursor: decide.isPending || !reason.trim() ? 'not-allowed' : undefined,
                    }}
                    onClick={() => act(id, 'rejected')}
                  >
                    Reject
                  </button>
                </>
              )}
            </li>
          )
        })}
      </ul>
      <input
        aria-label="Why reject this evidence"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Reason (required to reject)"
        className="control-field w-full px-2 py-1"
      />
      {failure && (
        <p role="alert" style={{ color: 'var(--red)' }}>
          {failure}
        </p>
      )}
    </div>
  )
}

/** Accepted evidence the task does not serve the requirement of: the remedy is the link. */
function UnlinkedRequirements({ taskId, body }: { taskId: string; body: GateBody }) {
  const link = useLinkTaskRequirements()
  const [linked, setLinked] = useState<string[]>([])
  const [failure, setFailure] = useState<string | null>(null)
  const entries = body.unlinked ?? []
  if (entries.length === 0) return null
  const identifiers = [...new Set(entries.map((entry) => entry.identifier ?? '').filter(Boolean))]
  return (
    <div data-testid={`task-landing-unlinked-${taskId}`} className="space-y-1 text-[11px]">
      <p style={{ color: 'var(--text-2)' }}>
        This task recorded accepted evidence for requirements it does not serve, so landing does not
        merge it. Link them, then press Land again.
      </p>
      {identifiers.map((identifier) => (
        <div key={identifier} className="flex items-center gap-2">
          <span>{identifier}</span>
          {linked.includes(identifier) ? (
            <span style={{ color: 'var(--green)' }}>Linked</span>
          ) : (
            <button
              type="button"
              data-testid={`task-landing-link-${identifier}`}
              disabled={link.isPending}
              className="px-2 py-0.5 rounded"
              style={{ border: '1px solid var(--border)' }}
              onClick={() => {
                setFailure(null)
                link.mutate(
                  { id: taskId, requirement_ids: [identifier] },
                  {
                    onSuccess: () => setLinked((current) => [...current, identifier]),
                    onError: (error: unknown) =>
                      setFailure(readableApiError(error, 'The Hub could not link it.')),
                  },
                )
              }}
            >
              Link {identifier}
            </button>
          )}
        </div>
      ))}
      {failure && (
        <p role="alert" style={{ color: 'var(--red)' }}>
          {failure}
        </p>
      )}
    </div>
  )
}

/** The fix beside a landing refusal; renders nothing for a cause that has no action. */
export function LandingRemedies({ taskId, body }: { taskId: string; body: GateBody }) {
  return (
    <>
      <AwaitingEvidence taskId={taskId} body={body} />
      <UnlinkedRequirements taskId={taskId} body={body} />
      {waitsOnChecks(body) && (
        <p data-testid={`task-landing-waits-${taskId}`} className="text-[11px]" style={{ color: 'var(--text-2)' }}>
          Landing waits for the checks. It can be pressed again when they finish; nothing needs
          overriding while they run.
        </p>
      )}
    </>
  )
}

const minutes = (seconds: number) => Math.max(1, Math.round(seconds / 60))

/**
 * Beside Land: the landing is waiting on the checks, for how long they have run and how long the
 * previous run took. Reads the same query the checks row does, which polls while a run is going, so
 * it clears by itself when the run ends.
 */
export function LandWait({ taskId }: { taskId: string }) {
  const { data } = useTaskChecks(taskId, true)
  const wait = data ? checksWait(data.runs, data.running) : null
  const elapsed = useElapsedSeconds(wait !== null, wait?.run.started_at)
  if (!wait) return null
  const running = elapsed ?? 0
  const unit = (seconds: number) => `${minutes(seconds)} ${minutes(seconds) === 1 ? 'minute' : 'minutes'}`
  const previous = wait.previousSeconds
  return (
    <span
      data-testid={`task-land-wait-${taskId}`}
      role="status"
      className="text-[11px]"
      style={{ color: 'var(--text-2)' }}
    >
      Waiting for checks · running {unit(running)}
      {previous != null ? ` of about ${minutes(previous)}` : ''}
    </span>
  )
}
