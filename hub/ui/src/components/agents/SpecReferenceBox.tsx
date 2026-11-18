import { useSpecDocuments } from '@/api/spec'
import { specTabId, usePanelTabsStore } from '@/store/panelTabsStore'
import { useConfigStore } from '@/store/configStore'
import { SPEC_BOX_CLASS } from '@/lib/composerEditor'

/**
 * A spec reference in a sent message, drawn as the composer's box (design D3): the document's
 * current title from the project's document list, the title written at send time as the fallback
 * and, once renamed, the tooltip. Activating it opens the document in the side panel; a document
 * missing from the list is shown muted, marked no longer available, and opens nothing.
 */
export function SpecReferenceBox({ id, sentTitle }: { id: string; sentTitle: string }) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const openTab = usePanelTabsStore((state) => state.openTab)
  const { data } = useSpecDocuments()
  // Until the list has loaded nothing is known to be missing, so the box stays live.
  const loaded = data !== undefined
  const document = data?.documents?.find((candidate) => candidate.id === id)
  const missing = loaded && !document
  const title = document?.title || sentTitle

  if (missing) {
    return (
      <span
        className={`${SPEC_BOX_CLASS} spec-box-missing`}
        data-testid="timeline-spec-box"
        data-id={id}
        data-state="missing"
        title={`${sentTitle} — no longer available`}
      >
        <span className={`${SPEC_BOX_CLASS}-icon`} aria-hidden="true" />
        {sentTitle}
        <span className="ml-1 text-[11px]"> (no longer available)</span>
      </span>
    )
  }
  return (
    <button
      type="button"
      className={`${SPEC_BOX_CLASS} spec-box-link`}
      data-testid="timeline-spec-box"
      data-id={id}
      data-state={document && document.title !== sentTitle ? 'renamed' : 'current'}
      title={sentTitle}
      aria-label={`Open spec ${title}`}
      onClick={() => projectId && openTab(projectId, specTabId(id))}
    >
      <span className={`${SPEC_BOX_CLASS}-icon`} aria-hidden="true" />
      {title}
    </button>
  )
}
