import type { ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'
import { useConfigStore } from '@/store/configStore'
import { evidenceDestination, goTo } from '@/lib/navigation'

/**
 * Opens the evidence browser focused on what a mention of evidence means: a task id (`task-…`) or
 * a requirement's durable id (`spreq-…`; `FR-n` repeats in every document), or the whole project when `focus` is null (slice
 * evidence-browser's cross-links). Every place that says "evidence" can then show the pieces.
 */
export function EvidenceLink({
  focus,
  children = 'Open in Evidence',
  testId,
  inline = false,
}: {
  focus: string | null
  children?: ReactNode
  testId?: string
  /** Inside a sentence of links: take the sentence's size and the link colour. */
  inline?: boolean
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  if (!projectId) return null
  return (
    <button
      type="button"
      className={inline ? 'aw-link aw-link-inline' : 'aw-link'}
      data-testid={testId}
      onClick={(event) => {
        // Inside a row that toggles or a drawer that closes on outside clicks, the link is the
        // whole action.
        event.stopPropagation()
        goTo(evidenceDestination(projectId, focus))
      }}
    >
      {children}
      <Icon name="arrow_forward" size={11} />
    </button>
  )
}
