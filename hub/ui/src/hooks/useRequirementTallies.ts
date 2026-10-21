import * as React from 'react'
import { useSpecCoverageMany } from '@/api/spec'
import type { Task } from '@/api/tasks'
import type { RequirementTally } from '@/components/tasks/TaskCardCompact'

/** Each task's requirements, as document coverage states them (never `requirement_links[].state`,
 *  which is the requirement's lifecycle, not whether anything proves it), read once for the board:
 *  one coverage query per document the tasks name. */
export function useRequirementTallies(
  tasks: Task[],
  documents: Array<{ id: string; path: string }>,
): Record<string, RequirementTally> {
  const pathById = React.useMemo(() => new Map(documents.map((d) => [d.id, d.path])), [documents])
  const paths = React.useMemo(() => {
    const set = new Set<string>()
    for (const task of tasks)
      for (const link of task.requirement_links ?? []) {
        const path = pathById.get(link.document_id)
        if (path) set.add(path)
      }
    return [...set].sort()
  }, [tasks, pathById])
  const coverage = useSpecCoverageMany(paths)
  return React.useMemo(() => {
    const state = new Map<string, string>()
    paths.forEach((path, index) => {
      for (const entry of coverage[index]?.data?.requirements ?? []) state.set(`${path}#${entry.identifier}`, entry.state)
    })
    const out: Record<string, RequirementTally> = {}
    for (const task of tasks) {
      const ids = task.requirement_ids ?? []
      if (ids.length === 0) continue
      const links = new Map((task.requirement_links ?? []).map((l) => [l.identifier, l]))
      let verified = 0
      let rejected = 0
      for (const id of ids) {
        const link = links.get(id)
        const path = link ? pathById.get(link.document_id) : undefined
        const s = path ? state.get(`${path}#${id}`) : undefined
        if (s === 'verified') verified += 1
        if (s === 'rejected' || link?.has_rejected_evidence) rejected += 1
      }
      out[task.id] = { verified, rejected, total: ids.length }
    }
    return out
    // `coverage` is a new array each render; its data is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, paths, pathById, coverage.map((c) => c.dataUpdatedAt).join(',')])
}
