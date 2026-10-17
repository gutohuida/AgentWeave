/** Reading a unified diff line by line, for `DiffView`. */

export type DiffLineKind = 'add' | 'del' | 'hunk' | 'ctx' | 'meta'

export function classifyDiffLine(line: string): DiffLineKind {
  if (line.startsWith('@@')) return 'hunk'
  if (
    line.startsWith('+++') ||
    line.startsWith('---') ||
    line.startsWith('diff --git') ||
    line.startsWith('index ') ||
    line.startsWith('new file') ||
    line.startsWith('deleted file')
  ) {
    return 'meta'
  }
  if (line.startsWith('+')) return 'add'
  if (line.startsWith('-')) return 'del'
  return 'ctx'
}

/** `[added, removed]` line counts of one file's patch. */
export function diffStat(patch: string): [number, number] {
  let added = 0
  let removed = 0
  for (const line of patch.split('\n')) {
    const kind = classifyDiffLine(line)
    if (kind === 'add') added += 1
    if (kind === 'del') removed += 1
  }
  return [added, removed]
}
