import type { ReachGrants } from '@/api/projects'

export const EMPTY_GRANTS: ReachGrants = { roots: [], hosts: [] }

/** Grants as they are saved (reach-1019): a root left blank is dropped, and nothing granted is
 *  null, which for a project means "nothing beyond the workspace". */
export function cleanGrants(grants: ReachGrants | null): ReachGrants | null {
  if (!grants) return null
  const roots = grants.roots
    .map((root) => ({ ...root, path: root.path.trim() }))
    .filter((root) => root.path)
  return roots.length || grants.hosts.length ? { roots, hosts: grants.hosts } : null
}

/** One line naming what is granted, for a select's inherited option. */
export function describeGrants(grants: ReachGrants | null | undefined): string {
  if (!grants || !(grants.roots.length || grants.hosts.length)) return 'nothing beyond the workspace'
  return [
    ...grants.roots.map((root) => `${root.path} (${root.access === 'read' ? 'read' : 'read and write'})`),
    ...grants.hosts,
  ].join(', ')
}
