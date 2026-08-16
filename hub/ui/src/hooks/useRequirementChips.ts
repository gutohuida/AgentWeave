import { useMemo } from 'react'
import type { Task } from '@/api/tasks'
import { useSpecDocuments } from '@/api/spec'

/**
 * One resolved requirement chip: identifier, where to navigate, and the rejected-evidence signal
 * that never reached a screen before F4 (`hub/hub/api/v1/tasks.py`'s `_attach_requirements()`).
 *
 * Shared between `TaskCard`'s compact header row (identifier only) and `TaskDetailDrawer`'s full
 * row (identifier plus statement plus, where rejected, the reason) so the resolution logic —
 * looking up a link by identifier, resolving its document id to a path via the already-loaded
 * document list, stripping the anchor's leading `#` — exists in exactly one place.
 */
export interface RequirementChip {
  identifier: string
  statement: string | null
  rejected: boolean
  latestRejectionReason: string | null
  documentPath: string | undefined
  anchor: string
  clickable: boolean
}

export function useRequirementChips(task: Task | null): RequirementChip[] {
  const { data: specDocuments } = useSpecDocuments()

  const linkByIdentifier = useMemo(
    () => new Map((task?.requirement_links ?? []).map((link) => [link.identifier, link])),
    [task?.requirement_links],
  )
  const documentPathById = useMemo(
    () => new Map((specDocuments?.documents ?? []).map((doc) => [doc.id, doc.path])),
    [specDocuments],
  )

  return useMemo(
    () =>
      (task?.requirement_ids ?? []).map((identifier) => {
        const link = linkByIdentifier.get(identifier)
        const rejected = link?.has_rejected_evidence === true
        const documentPath = link ? documentPathById.get(link.document_id) : undefined
        const anchor = link?.anchor ? link.anchor.replace(/^#/, '') : identifier
        return {
          identifier,
          statement: link?.statement ?? null,
          rejected,
          latestRejectionReason: rejected ? link?.latest_rejection_reason ?? null : null,
          documentPath,
          anchor,
          clickable: Boolean(documentPath),
        }
      }),
    [task?.requirement_ids, linkByIdentifier, documentPathById],
  )
}
