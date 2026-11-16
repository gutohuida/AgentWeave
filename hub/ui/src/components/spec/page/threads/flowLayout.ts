import type { GraphNode } from './threadModel'

/** Columns by depth, left to right; within a column, tasks sit near the average height of what they
 *  wait on, so threads run mostly level. */
export function flowLayout(nodes: GraphNode[], late: Set<string> = new Set()) {
  const byKey = new Map(nodes.map((n) => [n.key, n]))
  const depth = new Map<string, number>()
  const visit = (key: string, seen: Set<string>): number => {
    const known = depth.get(key)
    if (known !== undefined) return known
    if (seen.has(key)) return 0
    seen.add(key)
    const d = Math.max(-1, ...(byKey.get(key)?.dependsOn ?? []).filter((k) => byKey.has(k)).map((k) => visit(k, seen))) + 1
    depth.set(key, d)
    return d
  }
  nodes.forEach((n) => visit(n.key, new Set()))
  // A node drawn only as a thread's start sits just left of the first task that needs it, so its
  // thread is short instead of crossing the map from the far edge.
  for (const key of late) {
    const needs = nodes.filter((n) => n.dependsOn.includes(key)).map((n) => depth.get(n.key) ?? 1)
    if (needs.length) depth.set(key, Math.max(0, Math.min(...needs) - 1))
  }
  const last = Math.max(0, ...depth.values())
  const pos = new Map<string, { col: number; slot: number }>()
  const cols: GraphNode[][] = Array.from({ length: last + 1 }, () => [])
  nodes.forEach((n) => cols[depth.get(n.key) ?? 0]!.push(n))
  cols.forEach((col, c) => {
    const centre = (n: GraphNode) => {
      const ps = n.dependsOn.map((d) => pos.get(d)?.slot).filter((s): s is number => s !== undefined)
      return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : Number.POSITIVE_INFINITY
    }
    const sorted = c === 0 ? col : [...col].sort((a, b) => centre(a) - centre(b))
    let next = 0
    sorted.forEach((n) => {
      const want = Number.isFinite(centre(n)) ? Math.round(centre(n)) : next
      const slot = Math.max(next, want)
      pos.set(n.key, { col: c, slot })
      next = slot + 1
    })
  })
  const rows = Math.max(1, ...[...pos.values()].map((p) => p.slot + 1))
  return { pos, cols: last + 1, rows }
}
