import { useMemo } from 'react'
import type { Task } from '@/api/tasks'
import { useSpecCoverageMany, useSpecDocuments, type CoverageEntry } from '@/api/spec'

/** The chip's visual state. Driven by the requirement's **coverage** (`useSpecCoverage`, the same
 *  read the document view uses), never by `requirement_links[].state` — that field is the
 *  requirement's lifecycle (`active`/`retired`), not whether anything proves it (design D5, R1:
 *  built the other way, no chip could ever show `verified`). */
export type RequirementChipTone = 'verified' | 'pending' | 'rejected' | 'neutral'

const TONE_BY_COVERAGE_STATE: Partial<Record<CoverageEntry['state'], RequirementChipTone>> = {
  verified: 'verified',
  evidence_awaiting_review: 'pending',
  rejected: 'rejected',
}

/**
 * One resolved requirement chip: identifier, where to navigate, and the coverage tone it stands
 * in today.
 *
 * Shared between `TaskCard`'s compact header row (identifier only) and `TaskDetailDrawer`'s full
 * row (identifier plus statement) so the resolution logic — looking up a link by identifier,
 * resolving its document id to a path via the already-loaded document list, stripping the
 * anchor's leading `#` — exists in exactly one place.
 */
export interface RequirementChip {
  identifier: string
  statement: string | null
  tone: RequirementChipTone
  rejected: boolean
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

  const documentPaths = useMemo(
    () => (task?.requirement_ids ?? []).map((identifier) => {
      const link = linkByIdentifier.get(identifier)
      return link ? documentPathById.get(link.document_id) : undefined
    }),
    [task?.requirement_ids, linkByIdentifier, documentPathById],
  )
  const uniquePaths = useMemo(
    () => Array.from(new Set(documentPaths.filter((path): path is string => Boolean(path)))),
    [documentPaths],
  )
  const coverageResults = useSpecCoverageMany(uniquePaths)
  const coverageByPath = useMemo(
    () => new Map(uniquePaths.map((path, index) => [path, coverageResults[index]?.data])),
    [uniquePaths, coverageResults],
  )

  return useMemo(
    () =>
      (task?.requirement_ids ?? []).map((identifier, index) => {
        const link = linkByIdentifier.get(identifier)
        const documentPath = documentPaths[index]
        const coverageEntry = documentPath
          ? coverageByPath.get(documentPath)?.requirements.find((entry) => entry.identifier === identifier)
          : undefined
        const tone: RequirementChipTone = coverageEntry
          ? TONE_BY_COVERAGE_STATE[coverageEntry.state] ?? 'neutral'
          : 'neutral'
        const anchor = link?.anchor ? link.anchor.replace(/^#/, '') : identifier
        return {
          identifier,
          statement: link?.statement ?? null,
          tone,
          rejected: tone === 'rejected',
          documentPath,
          anchor,
          clickable: Boolean(documentPath),
        }
      }),
    [task?.requirement_ids, linkByIdentifier, documentPaths, coverageByPath],
  )
}
