import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { formatCount } from '@/lib/format'
import '@/styles/spec-header.css'

export interface SpecListDocument {
  path: string
  title: string
  kind: string
  phase: string
  /** Archived, by phase or by living under `spec/changes/archive/`. Listed in their own folded
   *  group, never dropped: the old tree included archives so a finished change stays findable. */
  archived?: boolean
  /** Named by the index and absent on disk. Listed, marked, and not openable. */
  missing?: boolean
}

const FOLDS_KEY = 'aw.spec.listFolds'

function loadFolds(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(FOLDS_KEY) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

/** The Spec tab's own document list, a pane inside the tab. Today the whole sidebar swapped to a
 *  document rail ("← Terra", Specification, Evidence, a folder tree, Defects by step), so the
 *  agents disappeared whenever a document was open. The sidebar now stays; documents are listed
 *  here, grouped by kind, each with its phase as a dot and a word.
 *
 *  Everything the rail offered is here: every document the corpus holds (the overview documents,
 *  roadmaps, changes, capabilities; archived and missing ones in groups of their own), the
 *  Evidence view with its count, and whatever the host puts in `footer` (the defects report).
 *  A group folds, and the fold is remembered. */
export function SpecDocumentList({
  documents,
  active,
  evidenceCount,
  evidenceActive = false,
  onOpen,
  onOpenEvidence,
  onNew,
  footer,
}: {
  documents: SpecListDocument[]
  active: string | null
  /** Null while unknown; `'error'` when the count could not be read. */
  evidenceCount: number | null | 'error'
  evidenceActive?: boolean
  onOpen: (path: string) => void
  onOpenEvidence?: () => void
  /** Starting a new change. Absent where the host has no way to start one. */
  onNew?: () => void
  footer?: React.ReactNode
}) {
  const [folds, setFolds] = React.useState<Record<string, boolean>>(loadFolds)
  const toggle = (key: string, folded: boolean) =>
    setFolds((state) => {
      const next = { ...state, [key]: !folded }
      try {
        localStorage.setItem(FOLDS_KEY, JSON.stringify(next))
      } catch {
        // Persistence is optional.
      }
      return next
    })

  const live = documents.filter((d) => !d.archived && !d.missing)
  const known = new Set(['roadmap', 'change-spec', 'capability'])
  const groups: Array<{ key: string; label: string; docs: SpecListDocument[]; foldedByDefault?: boolean }> = [
    { key: 'overview', label: 'Overview', docs: live.filter((d) => !known.has(d.kind)) },
    { key: 'roadmaps', label: 'Roadmaps', docs: live.filter((d) => d.kind === 'roadmap') },
    { key: 'changes', label: 'Changes', docs: live.filter((d) => d.kind === 'change-spec') },
    { key: 'capabilities', label: 'Capabilities', docs: live.filter((d) => d.kind === 'capability') },
    { key: 'archived', label: 'Archived', docs: documents.filter((d) => d.archived && !d.missing), foldedByDefault: true },
    { key: 'missing', label: 'Missing', docs: documents.filter((d) => d.missing) },
  ]
  // The group holding the open document never rests folded: the list has to say where you are.
  const activeGroup = groups.find((g) => g.docs.some((d) => d.path === active))?.key

  return (
    <nav className="aw-spec-list" aria-label="Spec documents" data-testid="spec-document-list">
      <div className="aw-spec-list-head">
        <span>Documents</span>
        {onNew ? (
          <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label="New change" title="New change" onClick={onNew}>
            <Icon name="add" size={14} />
          </button>
        ) : null}
      </div>
      {documents.length === 0 ? <p className="aw-spec-list-empty">No specification documents yet.</p> : null}
      {groups
        .filter((group) => group.docs.length > 0)
        .map((group) => {
          const folded = group.key !== activeGroup && (folds[group.key] ?? group.foldedByDefault ?? false)
          return (
            <div key={group.key} className="aw-spec-list-group" data-group={group.key}>
              <button
                type="button"
                data-slot="spec-list-label"
                className="aw-spec-list-label"
                aria-expanded={!folded}
                onClick={() => toggle(group.key, folded)}
              >
                <span className="aw-spec-list-chevron" data-open={folded ? 'false' : 'true'} aria-hidden="true">
                  <Icon name="chevron_right" size={11} />
                </span>
                {group.label}
                <span className="aw-spec-list-count">{formatCount(group.docs.length)}</span>
              </button>
              {folded
                ? null
                : group.docs.map((doc) => (
                    <button
                      key={doc.path}
                      type="button"
                      data-slot="spec-list-row"
                      className="aw-spec-list-row"
                      data-testid={`spec-list-row-${doc.path}`}
                      data-active={doc.path === active ? 'true' : 'false'}
                      data-missing={doc.missing ? 'true' : undefined}
                      aria-current={doc.path === active ? 'page' : undefined}
                      disabled={doc.missing}
                      onClick={() => onOpen(doc.path)}
                      title={doc.missing ? `${doc.path} — named by the index, not on disk` : doc.path}
                    >
                      <span className="aw-spec-list-dot" data-phase={doc.phase} />
                      <span className="min-w-0 flex-1 truncate">{doc.title}</span>
                      <span className="aw-spec-list-phase">{phaseWord(doc)}</span>
                    </button>
                  ))}
            </div>
          )
        })}
      {onOpenEvidence ? (
        <div className="aw-spec-list-group">
          <button
            type="button"
            data-slot="spec-list-row"
            className="aw-spec-list-row"
            data-testid="spec-list-evidence"
            data-active={evidenceActive ? 'true' : 'false'}
            aria-current={evidenceActive ? 'page' : undefined}
            onClick={onOpenEvidence}
          >
            <Icon name="verified" size={13} className="aw-spec-list-icon" />
            <span className="min-w-0 flex-1 truncate">Evidence</span>
            <span className="aw-spec-list-phase" title={evidenceCount === 'error' ? 'The evidence count could not be read' : undefined}>
              {evidenceCount === 'error' ? '—' : evidenceCount === null ? '' : formatCount(evidenceCount)}
            </span>
          </button>
        </div>
      ) : null}
      {footer}
    </nav>
  )
}

function phaseWord(doc: SpecListDocument): string {
  if (doc.missing) return 'missing'
  if (doc.phase === 'exploring') return 'draft'
  return doc.phase
}
