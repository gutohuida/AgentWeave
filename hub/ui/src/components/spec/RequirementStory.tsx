import type { CSSProperties } from 'react'
import { Icon } from '@/components/common/Icon'
import { StatePill, type Tone } from '@/components/common/StatePill'
import { Timeline, TimelineItem } from '@/components/common/Timeline'
import { EvidenceLink } from '@/components/evidence/EvidenceLink'
import {
  forEarlierWording,
  useSpecRequirement,
  type RequirementRevision,
  type RequirementDriftRow,
} from '@/api/spec'
import { evidenceTone, statusTone } from '@/lib/storyTones'
import { hubDate } from '@/lib/hubTime'
import { wordDiff } from '@/lib/wordDiff'

/**
 * One requirement's story (slice requirement-story): its wording now, every revision with who
 * made it and what the words became, the tasks that served it, its evidence and its drift.
 *
 * Revisions render in the order the detail route returns them (oldest first). A revision recorded
 * before the Hub kept wordings (migration 0131) says so rather than guessing what it said.
 */

const CHANGE: Record<RequirementRevision['classification'], { verb: string; icon: string; tone: Tone }> = {
  created: { verb: 'wrote it', icon: 'add', tone: 'blue' },
  reworded: { verb: 'reworded it', icon: 'edit', tone: 'amber' },
  retired: { verb: 'retired it', icon: 'archive', tone: 'red' },
  restored: { verb: 'restored it', icon: 'restart_alt', tone: 'green' },
}

const DRIFT_TONE: Record<RequirementDriftRow['state'], Tone> = {
  candidate: 'amber',
  resolved: 'green',
  superseded: 'neutral',
}

function relative(value: string | null): { label: string; exact: string } | null {
  if (!value) return null
  const date = hubDate(value)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  let label: string
  if (seconds < 45) label = 'just now'
  else if (seconds < 3600) label = `${Math.round(seconds / 60)}m ago`
  else if (seconds < 86400) label = `${Math.round(seconds / 3600)}h ago`
  else label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return { label, exact: date.toLocaleString() }
}

function Time({ value }: { value: string | null }) {
  const at = relative(value)
  return at ? <time title={at.exact}>{at.label}</time> : null
}

function who(revision: RequirementRevision): string {
  if (revision.actor_kind === 'operator') return 'You'
  if (revision.source === 'external') return 'An edit outside the app'
  return revision.actor || 'The Hub'
}

function Wording({ before, after }: { before: string | null; after: string }) {
  if (before == null) return <p className="aw-req-wording">{after}</p>
  return (
    <p className="aw-req-wording">
      {wordDiff(before, after).map((part, index) => {
        if (part.kind === 'same') return <span key={index}>{part.text}</span>
        // The mark covers the words, not the space after them.
        const words = part.text.trimEnd()
        const space = part.text.slice(words.length)
        return (
          <span key={index}>
            {part.kind === 'added' ? (
              <ins className="aw-word-added">{words}</ins>
            ) : (
              <del className="aw-word-removed">{words}</del>
            )}
            {space}
          </span>
        )
      })}
    </p>
  )
}

function Revision({
  revision,
  previous,
  index,
  onOpenDocument,
}: {
  revision: RequirementRevision
  /** The wording before this revision, when it was recorded; undefined for the first revision. */
  previous: string | null | undefined
  index: number
  onOpenDocument: (path: string) => void
}) {
  const folded = revision.folded_from
  const change = CHANGE[revision.classification] ?? CHANGE.reworded
  const recorded = revision.statement != null
  return (
    <TimelineItem
      index={index}
      tone={change.tone}
      icon={change.icon}
      testId={`requirement-revision-${revision.id}`}
      head={
        folded ? (
          <span data-testid={`requirement-revision-folded-${revision.id}`}>
            <strong>{who(revision)}</strong> folded it in from{' '}
            <button type="button" className="aw-inline-link" onClick={() => onOpenDocument(folded.path)}>
              {folded.title || folded.path}
            </button>
          </span>
        ) : (
          <span>
            <strong>{who(revision)}</strong> {change.verb}
          </span>
        )
      }
      meta={
        <>
          <Time value={revision.created_at} />
          {revision.classification !== 'retired' && !recorded ? (
            <span data-testid={`requirement-revision-unrecorded-${revision.id}`}> · wording not recorded</span>
          ) : null}
        </>
      }
    >
      {revision.classification !== 'retired' && recorded ? (
        <>
          <Wording before={previous ?? null} after={revision.statement as string} />
          {previous === null ? (
            <p className="aw-tl-meta">The wording before this was not recorded, so this is shown whole.</p>
          ) : null}
        </>
      ) : null}
    </TimelineItem>
  )
}

export function RequirementStory({
  document,
  identifier,
  onOpenDocument,
  onOpenTask,
}: {
  document: string
  identifier: string
  onOpenDocument: (path: string) => void
  onOpenTask: (taskId: string) => void
}) {
  const { data, isLoading, isError } = useSpecRequirement(identifier, document)

  if (isLoading) {
    return (
      <div className="aw-evidence-page" aria-label="Loading the requirement">
        {[60, 85, 70].map((width, index) => (
          <div key={index} className="aw-skeleton" style={{ width: `${width}%`, height: 14 }} />
        ))}
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="aw-evidence-page">
        <p className="aw-callout tone-red" data-testid="requirement-story-error">
          The Hub did not answer for {identifier} in this document. It may have been removed, or the
          Hub may be restarting.
        </p>
      </div>
    )
  }

  const { requirement, tasks, evidence } = data
  const revisions = data.revisions ?? []
  const drift = data.drift ?? []
  // A piece recorded for an earlier wording is counted apart (F691): its verdict is about words the
  // requirement no longer says, which is why coverage calls the requirement stale.
  const counts = { accepted: 0, awaiting: 0, rejected: 0, earlier: 0 } as Record<string, number>
  for (const piece of evidence) {
    const key = forEarlierWording(piece) ? 'earlier' : piece.review_state
    counts[key] = (counts[key] ?? 0) + 1
  }
  // The wording before each revision: the previous revision's, when it was recorded. A retirement
  // carries no wording, so a restoration compares against the last wording that was recorded.
  let lastWording: string | null | undefined = undefined
  const previousOf: Array<string | null | undefined> = revisions.map((revision) => {
    const before = lastWording
    if (revision.classification !== 'retired') lastWording = revision.statement
    return before
  })

  return (
    <div className="aw-evidence-page aw-req-page" data-testid="requirement-story">
      <header className="grid gap-2">
        <button
          type="button"
          className="aw-link"
          onClick={() => onOpenDocument(document)}
          data-testid="requirement-story-back"
        >
          <Icon name="arrow_left" size={12} aria-hidden="true" />
          {requirement.document?.title || document}
        </button>
        <div className="flex items-center gap-2">
          <span className="aw-evidence-req">{requirement.identifier}</span>
          <StatePill tone={requirement.state === 'retired' ? 'red' : 'green'}>
            {requirement.state === 'retired' ? 'retired' : 'current'}
          </StatePill>
        </div>
        <p className="aw-req-statement" data-testid="requirement-story-statement">
          {requirement.statement ?? (
            <span className="aw-tl-meta">
              {requirement.state === 'retired'
                ? 'Retired: the document no longer states it.'
                : 'The wording could not be read from the document.'}
            </span>
          )}
        </p>
      </header>

      <section className="aw-req-section">
        <h2 className="aw-req-heading">How it changed</h2>
        {revisions.some((r) => r.classification !== 'retired' && r.statement == null) ? (
          <p className="aw-req-note" data-testid="requirement-story-unrecorded-note">
            The Hub keeps each wording from now on. Earlier changes recorded who made them and when,
            not what the words were.
          </p>
        ) : null}
        {revisions.length === 0 ? (
          <p className="aw-tl-meta">No revisions are recorded for it.</p>
        ) : (
          <Timeline testId="requirement-revisions">
            {revisions.map((revision, index) => (
              <Revision
                key={revision.id}
                revision={revision}
                previous={previousOf[index]}
                index={index}
                onOpenDocument={onOpenDocument}
              />
            ))}
          </Timeline>
        )}
      </section>

      <section className="aw-req-section">
        <h2 className="aw-req-heading">
          Evidence
          <span className="aw-counts">
            {counts.accepted ? <span className="tone-green">{counts.accepted} accepted</span> : null}
            {counts.awaiting ? <span className="tone-amber">{counts.awaiting} waiting</span> : null}
            {counts.rejected ? <span className="tone-red">{counts.rejected} rejected</span> : null}
            {counts.earlier ? (
              <span className="tone-neutral" data-testid="requirement-story-evidence-earlier">
                {counts.earlier} for an earlier wording
              </span>
            ) : null}
          </span>
          {evidence.length ? (
            <EvidenceLink focus={requirement.id} testId="requirement-story-evidence">
              See all
            </EvidenceLink>
          ) : null}
        </h2>
        {evidence.length === 0 ? (
          <p className="aw-tl-meta">No evidence recorded yet.</p>
        ) : (
          <ul className="aw-req-list">
            {[...evidence].reverse().slice(0, 5).map((piece, index) => (
              <li key={piece.id} style={{ '--i': index } as CSSProperties}>
                <span className="aw-req-line">{piece.summary || piece.locator || 'No summary'}</span>
                {forEarlierWording(piece) ? (
                  <StatePill tone="neutral" testId={`requirement-story-earlier-${piece.id}`}>
                    {piece.review_state === 'awaiting' ? 'waiting' : piece.review_state} · earlier
                    wording
                  </StatePill>
                ) : (
                  <StatePill tone={evidenceTone(piece.review_state)}>
                    {piece.review_state === 'awaiting' ? 'waiting' : piece.review_state}
                  </StatePill>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="aw-req-section">
        <h2 className="aw-req-heading">Tasks</h2>
        {tasks.length === 0 ? (
          <p className="aw-tl-meta">No task serves it.</p>
        ) : (
          <ul className="aw-req-list">
            {tasks.map((task) => (
              <li key={task.id}>
                <button type="button" className="aw-inline-link aw-req-line" onClick={() => onOpenTask(task.id)}>
                  {task.title}
                </button>
                <StatePill tone={statusTone(task.status)}>{task.status.replace(/_/g, ' ')}</StatePill>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="aw-req-section" data-testid="requirement-story-drift">
        <h2 className="aw-req-heading">Drift</h2>
        {drift.length === 0 ? (
          <p className="aw-tl-meta">The files its evidence is about have not been seen to change.</p>
        ) : (
          <ul className="aw-req-list">
            {drift.map((row) => (
              <li key={row.id}>
                <span className="aw-req-line">
                  Files behind {row.evidence_id} changed · <Time value={row.created_at} />
                  {row.resolution ? (
                    <span className="aw-tl-meta">
                      {' '}
                      · {row.resolution.replace(/_/g, ' ')}
                      {row.resolved_by ? ` by ${row.resolved_by}` : ''}
                    </span>
                  ) : null}
                </span>
                <StatePill tone={DRIFT_TONE[row.state] ?? 'neutral'}>{row.state}</StatePill>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
