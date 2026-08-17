import type { SpecEntry, SpecListResponse } from '@/api/spec'

// Everything under this prefix is history. The Hub already guarantees safe,
// project-relative POSIX paths, so a prefix test is the whole classification
// rule — the UI never re-derives archive status from document metadata.
export const ARCHIVE_PREFIX = 'spec/changes/archive/'

export const OTHER_CHANGES_LABEL = 'Other changes'

export type SpecNodeState = SpecEntry['state'] | 'missing'

export interface SpecNode {
  path: string
  /** Manifest title when filed, otherwise derived from the path for display. */
  title: string
  kind?: SpecEntry['kind']
  status?: string
  state: SpecNodeState
  parent: string | null
  order: number
  archived: boolean
  /** Leading ISO date of the archive directory, or null when it has none. */
  archiveDate: string | null
  /** Archive directory with its leading date stripped — the change's name. */
  changeName: string | null
  /** Declared by the manifest but no file was found: visible, never selectable. */
  missing: boolean
}

export interface LibraryTreeNode {
  node: SpecNode
  children: LibraryTreeNode[]
}

export interface HistoryGroup {
  /** Parent roadmap path, or null for the Other changes group. */
  parentPath: string | null
  label: string
  entries: SpecNode[]
}

export interface SpecInventory {
  nodes: SpecNode[]
  byPath: Map<string, SpecNode>
  /** Current, filed, parent-aware. Never contains archived or missing nodes. */
  library: LibraryTreeNode[]
  /** Current drift: unindexed, unfiled, stale, missing, or parent-orphaned. */
  needsAttention: SpecNode[]
  history: HistoryGroup[]
}

/** One row of the folder tree: a directory heading, or a document under it.
 *
 *  Flattened with an explicit `depth` rather than nested, because the picker renders it as a
 *  single list — a flat array keeps DOM order, keyboard order, and reading order the same thing. */
export interface PathTreeRow {
  kind: 'directory' | 'document'
  /** Full path for a document; the directory prefix (no trailing slash) for a directory. */
  path: string
  /** The segment for a directory, the document's title for a document. */
  label: string
  depth: number
  node?: SpecNode
}

export interface SpecSearchResults {
  current: SpecNode[]
  archived: SpecNode[]
  /** Rendered as disabled entries — matching them must not hide the drift. */
  missing: SpecNode[]
}

const DEFAULT_ORDER = Number.MAX_SAFE_INTEGER
const ARCHIVE_DATE_RE = /^(\d{4}-\d{2}-\d{2})-(.*)$/

/** A document is archived if its path says so (the openspec-style `archive/` convention) or if
 *  the Hub's own record does (a phase transition, which never moves the file). Either is enough:
 *  a document filed under `archive/` is archived even if some future flow left its phase behind,
 *  and one whose phase says `archived` is archived even though the file never moved. */
function isArchived(path: string, phase?: string | null): boolean {
  return path.startsWith(ARCHIVE_PREFIX) || phase === 'archived'
}

/** `spec/changes/archive/2026-07-29-add-x/spec.html` -> date + change name. */
function parseArchiveSegment(path: string): { date: string | null; name: string | null } {
  if (!isArchived(path)) return { date: null, name: null }
  const dir = path.slice(ARCHIVE_PREFIX.length).split('/')[0]
  if (!dir) return { date: null, name: null }
  const match = ARCHIVE_DATE_RE.exec(dir)
  if (!match) return { date: null, name: dir }
  return { date: match[1], name: match[2] || null }
}

/**
 * A readable label for a document the manifest does not describe. A change's
 * directory identifies it better than the repeated `spec.html` basename.
 */
function deriveTitle(path: string): string {
  const segments = path.split('/').filter(Boolean)
  const basename = segments[segments.length - 1] ?? path
  if (basename.toLowerCase() === 'spec.html' && segments.length >= 2) {
    return segments[segments.length - 2]
  }
  return basename
}

function toNode(entry: SpecEntry): SpecNode {
  const archived = isArchived(entry.path, entry.phase)
  const { date, name } = parseArchiveSegment(entry.path)
  return {
    path: entry.path,
    title: entry.title ?? deriveTitle(entry.path),
    kind: entry.kind,
    status: entry.status,
    state: entry.state ?? 'unindexed',
    parent: entry.parent ?? null,
    order: entry.order ?? DEFAULT_ORDER,
    archived,
    archiveDate: date,
    changeName: name,
    missing: false,
  }
}

/** Manifest order, then title, then path — the FR-1 sibling contract. */
function compareNodes(a: SpecNode, b: SpecNode): number {
  if (a.order !== b.order) return a.order - b.order
  const byTitle = a.title.localeCompare(b.title)
  if (byTitle !== 0) return byTitle
  return a.path.localeCompare(b.path)
}

/** Newest archive date first; undated archives sort after every dated one. */
function compareHistory(a: SpecNode, b: SpecNode): number {
  if (a.archiveDate !== b.archiveDate) {
    if (a.archiveDate === null) return 1
    if (b.archiveDate === null) return -1
    return b.archiveDate.localeCompare(a.archiveDate)
  }
  const byTitle = a.title.localeCompare(b.title)
  if (byTitle !== 0) return byTitle
  return a.path.localeCompare(b.path)
}

export function buildInventory(list: SpecListResponse | undefined): SpecInventory {
  const nodes: SpecNode[] = (list?.specs ?? []).map(toNode)

  // Missing entries come from the manifest, not the filesystem. They are
  // surfaced so drift stays visible, but they are never readable targets.
  for (const entry of list?.missing ?? []) {
    const { date, name } = parseArchiveSegment(entry.path)
    nodes.push({
      path: entry.path,
      title: entry.title || deriveTitle(entry.path),
      kind: entry.kind as SpecEntry['kind'],
      status: entry.status,
      state: 'missing',
      parent: entry.parent ?? null,
      order: entry.order ?? DEFAULT_ORDER,
      archived: isArchived(entry.path),
      archiveDate: date,
      changeName: name,
      missing: true,
    })
  }

  const byPath = new Map<string, SpecNode>()
  for (const node of nodes) byPath.set(node.path, node)

  const readableCurrent = nodes.filter((n) => !n.archived && !n.missing)
  const filed = readableCurrent.filter((n) => n.state === 'filed')
  const filedPaths = new Set(filed.map((n) => n.path))

  // A filed node whose declared parent is not itself a filed current document
  // is orphaned: showing it as a root would silently invent a relationship.
  const isOrphan = (n: SpecNode) => n.parent !== null && !filedPaths.has(n.parent)

  const needsAttention = nodes
    .filter((n) => !n.archived && (n.missing || n.state !== 'filed' || isOrphan(n)))
    .sort(compareNodes)

  const inLibrary = filed.filter((n) => !isOrphan(n))
  const childrenOf = new Map<string | null, SpecNode[]>()
  for (const node of inLibrary) {
    const key = node.parent
    const bucket = childrenOf.get(key)
    if (bucket) bucket.push(node)
    else childrenOf.set(key, [node])
  }

  const buildBranch = (parent: string | null, seen: Set<string>): LibraryTreeNode[] =>
    (childrenOf.get(parent) ?? [])
      .slice()
      .sort(compareNodes)
      .filter((node) => !seen.has(node.path))
      .map((node) => {
        // A manifest cycle would otherwise recurse forever; visiting each path
        // once degrades a cycle to a flat listing instead of hanging the UI.
        seen.add(node.path)
        return { node, children: buildBranch(node.path, seen) }
      })

  const library = buildBranch(null, new Set<string>())

  // History covers readable archives only; a missing archived entry is drift
  // and is already reported under Needs attention.
  const archivedNodes = nodes.filter((n) => n.archived && !n.missing)
  const groups = new Map<string | null, SpecNode[]>()
  for (const node of archivedNodes) {
    const parent = node.parent && byPath.has(node.parent) ? node.parent : null
    const bucket = groups.get(parent)
    if (bucket) bucket.push(node)
    else groups.set(parent, [node])
  }

  const history: HistoryGroup[] = Array.from(groups.entries())
    .map(([parentPath, entries]) => ({
      parentPath,
      label: parentPath ? (byPath.get(parentPath)?.title ?? parentPath) : OTHER_CHANGES_LABEL,
      entries: entries.slice().sort(compareHistory),
    }))
    .sort((a, b) => {
      // Other changes always sorts last so named roadmaps lead the browser.
      if (a.parentPath === null) return 1
      if (b.parentPath === null) return -1
      const pa = byPath.get(a.parentPath)
      const pb = byPath.get(b.parentPath)
      if (pa && pb) return compareNodes(pa, pb)
      return a.label.localeCompare(b.label)
    })

  return { nodes, byPath, library, needsAttention, history }
}

function isReadable(inv: SpecInventory, path: string | null | undefined): boolean {
  if (!path) return false
  const node = inv.byPath.get(path)
  return !!node && !node.missing
}

/**
 * FR-4: keep what the user is reading; otherwise manifest home, then
 * `spec/spec.html`, then the first readable current document. An archive is
 * only ever shown because the user asked for it, never as a fallback.
 */
export function resolveSelection(
  inv: SpecInventory,
  current: string | null,
  home: string | null | undefined
): string | null {
  if (isReadable(inv, current)) return current

  const homeNode = home ? inv.byPath.get(home) : undefined
  if (homeNode && !homeNode.missing && !homeNode.archived) return homeNode.path

  const baseline = inv.byPath.get('spec/spec.html')
  if (baseline && !baseline.missing && !baseline.archived) return baseline.path

  const firstCurrent = inv.nodes
    .filter((n) => !n.archived && !n.missing)
    .sort(compareNodes)[0]
  return firstCurrent?.path ?? null
}

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

/**
 * Title matches outrank path matches, and a change name is treated as title-
 * strength vocabulary so an archived change is findable by its topic without
 * a separate tag taxonomy.
 */
function score(node: SpecNode, query: string): number {
  const title = normalize(node.title)
  const path = node.path.toLowerCase()
  const name = node.changeName?.toLowerCase() ?? ''

  if (title.startsWith(query)) return 4
  if (title.includes(query)) return 3
  if (name.includes(query)) return 2
  if (path.includes(query)) return 1
  return 0
}

export function searchDocuments(inv: SpecInventory, rawQuery: string): SpecSearchResults {
  const query = normalize(rawQuery)

  const rank = (nodes: SpecNode[]): SpecNode[] => {
    if (!query) return nodes.slice().sort(compareNodes)
    return nodes
      .map((node) => ({ node, s: score(node, query) }))
      .filter((entry) => entry.s > 0)
      .sort((a, b) => (b.s !== a.s ? b.s - a.s : compareNodes(a.node, b.node)))
      .map((entry) => entry.node)
  }

  return {
    current: rank(inv.nodes.filter((n) => !n.archived && !n.missing)),
    archived: rank(inv.nodes.filter((n) => n.archived && !n.missing)),
    missing: rank(inv.nodes.filter((n) => n.missing)),
  }
}

/**
 * The inventory as its folder hierarchy.
 *
 * The manifest's `parent` tree (`inventory.library`) answers "which document belongs under which"
 * — a roadmap and its change specs. This answers a different question the operator asked for
 * directly: where the files actually live. The two disagree often enough that showing one as the
 * other would mislead: an archived change sits under `spec/changes/archive/<date>-<name>/`
 * whatever its manifest parent says.
 *
 * Every node is included, archived and missing alike. A folder view that hides drift is a folder
 * view that lies about the folder.
 *
 * The leading `spec/` segment is dropped: every path starts with it, so a root everything hangs
 * from carries no information and costs a level of indentation.
 */
export function buildPathTree(nodes: SpecNode[]): PathTreeRow[] {
  const sorted = [...nodes].sort((a, b) => a.path.localeCompare(b.path))
  const rows: PathTreeRow[] = []
  let previous: string[] = []

  for (const node of sorted) {
    const segments = node.path.split('/')
    const file = segments.pop() as string
    // `spec` itself is dropped; everything is beneath it by the path contract.
    const directories = segments[0] === 'spec' ? segments.slice(1) : segments

    // Emit only the directory segments that differ from the previous document's, so a shared
    // parent is named once rather than repeated above every child.
    let shared = 0
    while (
      shared < directories.length &&
      shared < previous.length &&
      directories[shared] === previous[shared]
    ) {
      shared += 1
    }
    for (let depth = shared; depth < directories.length; depth += 1) {
      rows.push({
        kind: 'directory',
        path: ['spec', ...directories.slice(0, depth + 1)].join('/'),
        label: directories[depth],
        depth,
      })
    }
    previous = directories

    rows.push({
      kind: 'document',
      path: node.path,
      // The title, with the filename beside it at the call site: `spec.html` repeated down a
      // column of change directories says nothing, and the title is what the operator is looking
      // for.
      label: node.title || file,
      depth: directories.length,
      node,
    })
  }

  return rows
}
