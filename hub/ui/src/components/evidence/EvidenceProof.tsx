import { Icon } from '@/components/common/Icon'
import { StatePill } from '@/components/common/StatePill'
import { DiffView } from '@/components/common/DiffView'
import type { StoryReview } from '@/api/tasks'
import { useEvidenceDiff, type EvidencePiece } from '@/api/spec'

/**
 * What it takes to judge a piece of evidence (slices task-story and evidence-browser): its reviews,
 * quiet when accepted and called out when rejected, and its proof, the requirement's wording beside
 * the command, output and coverage, with the diff of the work fetched only once it is opened.
 */

function short(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 8) : ''
}

export function EvidenceReviews({ reviews }: { reviews: StoryReview[] }) {
  if (reviews.length === 0) return null
  return (
    <ul className="grid gap-1.5" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {reviews.map((review, index) => {
        const who = review.actor_kind === 'operator' ? 'you' : review.actor
        // An acceptance is the expected end and reads quietly; a rejection is what someone has to
        // act on, so it is the one that gets a callout.
        return review.decision === 'accepted' ? (
          <li key={index} className="aw-review-line tone-green">
            <Icon name="check" size={12} aria-hidden="true" />
            <span>
              Accepted by <strong>{who}</strong>
              {review.reason ? <> — {review.reason}</> : null}
            </span>
          </li>
        ) : (
          <li key={index} className="aw-callout tone-red">
            <strong>Rejected by {who}</strong>
            {review.reason ? <> — {review.reason}</> : null}
          </li>
        )
      })}
    </ul>
  )
}

export function EvidenceProof({ piece, open }: { piece: EvidencePiece; open: boolean }) {
  const diff = useEvidenceDiff(piece.id, open && !!piece.footprint?.commit_sha)
  const requirement = piece.requirement
  return (
    <div className="grid gap-2" data-testid={`evidence-proof-${piece.id}`}>
      <div className="aw-proof">
        <section>
          <span className="aw-proof-label">
            Requirement {requirement?.identifier ? <code>{requirement.identifier}</code> : null}
          </span>
          <p className="aw-proof-statement">
            {requirement?.statement ?? 'The requirement’s wording could not be read.'}
          </p>
          {piece.covers === 'partial' ? (
            <span>
              <StatePill tone="amber">covers part of it</StatePill>
            </span>
          ) : piece.covers === 'full' ? (
            <span>
              <StatePill tone="green">covers all of it</StatePill>
            </span>
          ) : null}
        </section>
        <section>
          <span className="aw-proof-label">Proof · {piece.kind.replace(/_/g, ' ')}</span>
          {piece.command ? <div className="aw-command">{piece.command}</div> : null}
          {piece.output ? (
            <pre className="aw-output" data-testid={`evidence-output-${piece.id}`}>
              {piece.output}
            </pre>
          ) : (
            <p className="aw-tl-meta">No output was recorded with this piece.</p>
          )}
          {piece.locator ? <div className="aw-tl-meta">at {piece.locator}</div> : null}
          {piece.footprint?.commit_sha ? (
            <div className="aw-tl-meta">
              {short(piece.footprint.commit_sha)}
              {piece.footprint.branch ? ` on ${piece.footprint.branch}` : ''}
            </div>
          ) : null}
        </section>
      </div>
      {piece.footprint?.commit_sha ? (
        diff.isLoading ? (
          <div className="grid gap-2" aria-label="Loading the diff">
            <div className="aw-skeleton" style={{ width: '60%' }} />
            <div className="aw-skeleton" style={{ width: '85%' }} />
          </div>
        ) : diff.data && diff.data.files.length > 0 ? (
          <>
            <DiffView files={diff.data.files} testId={`evidence-diff-${piece.id}`} />
            {diff.data.truncated ? (
              <p className="aw-tl-meta">The diff is larger than shown; the rest was cut.</p>
            ) : null}
          </>
        ) : diff.data?.reason ? (
          <p className="aw-tl-meta">{diff.data.reason}</p>
        ) : null
      ) : null}
    </div>
  )
}
