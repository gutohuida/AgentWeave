import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import { useSpecRequirement, useSpecRequirements, type SpecRequirementRow } from '@/api/spec'

/** `FR-10` → 10. The route sorts identifiers as strings (`FR-10` before `FR-2`); this list sorts on
 *  the number on purpose, with the identifier itself as the tie-break for anything unnumbered. */
function identifierNumber(identifier: string): number {
  const match = /(\d+)$/.exec(identifier)
  return match ? Number(match[1]) : Number.POSITIVE_INFINITY
}

function byIdentifierNumber(a: SpecRequirementRow, b: SpecRequirementRow): number {
  return (
    identifierNumber(a.identifier) - identifierNumber(b.identifier) ||
    a.identifier.localeCompare(b.identifier)
  )
}

const linkButton = {
  background: 'none',
  border: 'none',
  padding: 0,
  color: 'var(--blue)',
  cursor: 'pointer',
  textDecoration: 'underline',
} as const

interface SpecRetiredRequirementsProps {
  path: string
  /** Switches to the Tasks tab, filtered — the same navigation the coverage bar uses. */
  onOpenTasks?: (taskIds: string[]) => void
}

/**
 * The requirements this document has retired, and the work still pointing at them (F211).
 *
 * A removed requirement is retired rather than deleted so its links and evidence survive, and
 * coverage leaves retired requirements out — so without this list a retired requirement leaves
 * every screen while tasks and evidence still point at it. Mounted after the coverage bar, which
 * covers the active ones; this is only ever about the retired.
 */
export function SpecRetiredRequirements({ path, onOpenTasks }: SpecRetiredRequirementsProps) {
  const { data, isError, error } = useSpecRequirements(path)
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  // A failed read says so, in the Hub's words — never a list that silently is not there (F197).
  if (isError) {
    return (
      <div
        data-testid="spec-retired-error"
        className="flex shrink-0 items-center gap-1.5 px-3 py-2 text-xs"
        style={{ color: 'var(--amber)' }}
      >
        <Icon name="warning" size={13} />
        <span>
          Could not load retired requirements: {readableApiError(error, 'the Hub did not answer.')}
        </span>
      </div>
    )
  }

  const retired = (data?.requirements ?? [])
    .filter((row) => row.state === 'retired')
    .sort(byIdentifierNumber)
  if (retired.length === 0) return null

  return (
    <div
      className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
      data-testid="spec-retired"
      style={{ color: 'var(--text-2)' }}
    >
      <button
        type="button"
        data-testid="spec-retired-toggle"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2"
        aria-expanded={open}
        style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
      >
        <Icon name="archive" size={14} />
        <span>
          {retired.length} retired requirement{retired.length === 1 ? '' : 's'}
        </span>
        <Icon name={open ? 'expand_less' : 'expand_more'} size={14} />
      </button>

      {open && (
        <ul data-testid="spec-retired-list" className="flex flex-col gap-0.5 pl-5" style={{ color: 'var(--text-3)' }}>
          {retired.map((row) => (
            <li key={row.id} data-testid={`spec-retired-row-${row.identifier}`}>
              <button
                type="button"
                data-testid={`spec-retired-expand-${row.identifier}`}
                aria-expanded={expanded === row.id}
                onClick={() => setExpanded((current) => (current === row.id ? null : row.id))}
                className="flex items-center gap-1"
                style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
              >
                <Icon name={expanded === row.id ? 'expand_less' : 'expand_more'} size={13} />
                <span style={{ color: 'var(--text-2)' }}>{row.identifier}</span>
                <span>— {row.key}</span>
              </button>
              {expanded === row.id && (
                <RetiredRequirementDetail
                  identifier={row.identifier}
                  path={path}
                  onOpenTasks={onOpenTasks}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** What still points at one retired requirement. Mounted only when its row is open, so the detail
 *  is read for the requirement the operator asked about and no other. */
function RetiredRequirementDetail({
  identifier,
  path,
  onOpenTasks,
}: {
  identifier: string
  path: string
  onOpenTasks?: (taskIds: string[]) => void
}) {
  const { data, isError, error } = useSpecRequirement(identifier, path)

  return (
    <div data-testid={`spec-retired-detail-${identifier}`} className="flex flex-col gap-1 py-1" style={{ paddingLeft: 18 }}>
      {isError ? (
        <span style={{ color: 'var(--amber)' }}>
          Could not load {identifier}: {readableApiError(error, 'the Hub did not answer.')}
        </span>
      ) : !data ? (
        <span>Loading…</span>
      ) : (
        <>
          <span data-testid={`spec-retired-coverage-${identifier}`}>
            Coverage: {data.coverage ? data.coverage.state.replace(/_/g, ' ') : 'none reported'}
          </span>

          {data.tasks.length === 0 ? (
            <span>No tasks link to it.</span>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {data.tasks.map((task) => (
                <li key={task.id} data-testid={`spec-retired-task-${task.id}`}>
                  {onOpenTasks ? (
                    <button type="button" onClick={() => onOpenTasks([task.id])} style={linkButton}>
                      {task.title}
                    </button>
                  ) : (
                    <span style={{ color: 'var(--text-2)' }}>{task.title}</span>
                  )}
                  {' · '}
                  {task.status}
                  {task.assignee ? ` · @${task.assignee}` : ''}
                </li>
              ))}
            </ul>
          )}

          {/* Read-only, in the route's order (oldest first). Deciding about evidence belongs to the
              coverage bar's list for active requirements; a retired one has nothing left to gate. */}
          {data.evidence.length === 0 ? (
            <span>No evidence recorded for it.</span>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {data.evidence.map((piece) => (
                <li key={piece.id} data-testid={`spec-retired-evidence-${piece.id}`}>
                  {piece.summary || 'no summary'} — {piece.actor} · {piece.review_state}
                  {piece.latest_review?.reason ? `: ${piece.latest_review.reason}` : ''}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
