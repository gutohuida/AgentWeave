import { Icon } from '@/components/common/Icon'
import { SpecDefectsReport } from './SpecDefectsReport'
import { SpecTidyPanel } from './SpecTidyPanel'

/** Pinned under the spec list: the Evidence entry and the defects report, which starts folded to
 *  one line with its count so it does not push the list of specs off the screen (FR-8). */
export function SpecListFooter({
  onOpenEvidence,
  evidenceOpen,
  evidenceCount,
  evidenceError,
  currentPath,
  onSelect,
}: {
  onOpenEvidence?: () => void
  evidenceOpen: boolean
  evidenceCount: number | null
  evidenceError: boolean
  currentPath: string | null
  onSelect: (path: string) => void
}) {
  return (
    <>
      {onOpenEvidence ? (
        <button
          type="button"
          data-slot="spec-row"
          className="aw-sp-list-row"
          data-testid="spec-list-evidence"
          data-active={evidenceOpen ? 'true' : 'false'}
          aria-current={evidenceOpen ? 'page' : undefined}
          onClick={onOpenEvidence}
        >
          <Icon name="fact_check" size={13} className="aw-sp-list-icon" />
          <span className="aw-sp-list-name">Evidence</span>
          <span className="aw-sp-list-meta" title={evidenceError ? 'The evidence count could not be read' : undefined}>
            {evidenceError ? '—' : (evidenceCount ?? '')}
          </span>
        </button>
      ) : null}
      <SpecTidyPanel onSelect={onSelect} />
      <SpecDefectsReport currentPath={currentPath} onSelect={onSelect} />
    </>
  )
}
