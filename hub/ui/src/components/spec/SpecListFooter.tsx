import { Icon } from '@/components/common/Icon'
import { SpecDefectsReport } from './SpecDefectsReport'

/** Pinned under the spec list: the Evidence entry and the defects report. With `tidy` (being
 *  mocked, spec `the-spec-header-redesigned`) the report starts folded to one line with its count,
 *  so it no longer pushes the list of specs off the screen. */
export function SpecListFooter({
  onOpenEvidence,
  evidenceOpen,
  evidenceCount,
  evidenceError,
  currentPath,
  onSelect,
  tidy = false,
}: {
  onOpenEvidence?: () => void
  evidenceOpen: boolean
  evidenceCount: number | null
  evidenceError: boolean
  currentPath: string | null
  onSelect: (path: string) => void
  tidy?: boolean
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
      <SpecDefectsReport currentPath={currentPath} onSelect={onSelect} defaultOpen={!tidy} showCount={tidy} />
    </>
  )
}
