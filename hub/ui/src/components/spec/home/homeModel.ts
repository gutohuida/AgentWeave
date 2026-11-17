import type { ProjectBuildRow } from '@/api/projectBuilds'
import type { SpecDocumentRecord } from '@/api/spec'

/** What the Spec home draws, adapted from `GET /project/builds` and `GET /project/documents`. */

export interface HomeDocRef {
  path: string
  title: string
}

export interface HomeBuild {
  id: string
  state: 'running' | 'finished'
  document: HomeDocRef
  roadmap: { document: HomeDocRef; slice: { key: string; title: string } } | null
  capabilities: HomeDocRef[]
  tasksDone: number
  tasksTotal: number
  /** Approved tasks whose work has not landed yet. */
  tasksLanding: number
  startedAt: string
  finishedAt: string | null
  /** Null when no run of it was priced. */
  spentUsd: number | null
}

export interface HomeCapability extends HomeDocRef {
  waiting: number
}

/** The builds as the route returns them (newest first); a stopped build, or one whose document the
 *  route could not name, is not drawn. */
export function homeBuilds(rows: ProjectBuildRow[]): HomeBuild[] {
  const out: HomeBuild[] = []
  for (const r of rows) {
    if (r.state === 'stopped' || !r.document_path) continue
    out.push({
      id: r.id,
      state: r.state,
      document: { path: r.document_path, title: r.document_title },
      roadmap: r.roadmap ? { document: { path: r.roadmap.path, title: r.roadmap.title }, slice: r.roadmap.slice } : null,
      capabilities: r.capabilities ?? [],
      tasksDone: r.tasks_done,
      tasksTotal: r.tasks_total,
      tasksLanding: r.tasks_landing,
      startedAt: r.created_at ?? '',
      finishedAt: r.finished_at ?? null,
      spentUsd: r.spent_usd,
    })
  }
  return out
}

/** Every current capability, in the order the route gave them, with the changes waiting on it. */
export function homeCapabilities(documents: SpecDocumentRecord[]): HomeCapability[] {
  return documents
    .filter((d) => d.kind === 'capability' && d.phase === 'current')
    .map((d) => ({ path: d.path, title: d.title, waiting: d.waiting_count ?? d.waiting_changes?.length ?? 0 }))
}

/** The `limit` most recently finished builds, one per document at its latest finish. A stopped
 *  build is not built. */
export function latestFinished(builds: HomeBuild[], limit: number): HomeBuild[] {
  const seen = new Set<string>()
  return builds
    .filter((b) => b.state === 'finished' && b.finishedAt)
    .sort((a, b) => (a.finishedAt! < b.finishedAt! ? 1 : a.finishedAt! > b.finishedAt! ? -1 : 0))
    .filter((b) => (seen.has(b.document.path) ? false : (seen.add(b.document.path), true)))
    .slice(0, limit)
}

/** Every path one focused document connects to through the shown builds, itself included. */
export function litBy(builds: HomeBuild[], focus: string): Set<string> {
  const lit = new Set<string>([focus])
  for (const b of builds) {
    const paths = [b.document.path, ...(b.roadmap ? [b.roadmap.document.path] : []), ...b.capabilities.map((c) => c.path)]
    if (paths.includes(focus)) paths.forEach((p) => lit.add(p))
  }
  return lit
}
