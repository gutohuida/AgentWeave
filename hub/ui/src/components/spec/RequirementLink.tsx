import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { goTo, requirementDestination } from '@/lib/navigation'

/** Opens one requirement's story (slice requirement-story): how its wording changed and what
 *  proved it. Named by document and `FR-n`, the pair the requirement's detail route resolves. */
export function RequirementLink({
  document,
  identifier,
  children = 'history',
  testId,
}: {
  document: string
  identifier: string
  children?: ReactNode
  testId?: string
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  if (!projectId) return null
  return (
    <button
      type="button"
      className="aw-link aw-link-inline"
      data-testid={testId}
      onClick={(event) => {
        event.stopPropagation()
        goTo(requirementDestination(projectId, document, identifier))
      }}
    >
      {children}
    </button>
  )
}
