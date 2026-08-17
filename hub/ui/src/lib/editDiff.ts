import { diffLines } from 'diff'

/**
 * Parsing an edit tool call into diff lines, and summarising its size.
 *
 * Lives outside `ToolEditDiff.tsx` because that file exports a component, and a module that
 * exports both a component and a plain function breaks Fast Refresh — `react-refresh/only-export-
 * components`, which CI runs at `--max-warnings 0`. Both the diff view and the collapsed work row
 * read from here, so the counts shown before expanding cannot disagree with the lines shown after.
 */

export interface DiffLine {
  added: boolean
  removed: boolean
  text: string
}

/**
 * design.md D2 — a structural check on the parsed JSON, not a tool-name allow-list. `Edit`'s
 * payload has `old_string`/`new_string` at the top level and matches; `MultiEdit`'s pair lives
 * one level down inside `edits[]` and never matches — declines by design, not oversight.
 */
export function diffLinesForPayload(
  payload: Record<string, unknown> | null | undefined,
): DiffLine[] | null {
  const input = payload?.input
  if (typeof input !== 'string' || payload?.truncated === true) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(input)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null) return null

  const { old_string, new_string } = parsed as Record<string, unknown>
  if (typeof old_string !== 'string' || typeof new_string !== 'string') return null

  const changes = diffLines(old_string, new_string)
  const out: DiffLine[] = []
  for (const change of changes) {
    const changeLines = change.value.split('\n')
    // diffLines keeps a trailing '' from the final newline — drop it so we don't render an
    // empty extra row per hunk.
    if (changeLines[changeLines.length - 1] === '') changeLines.pop()
    for (const text of changeLines) {
      out.push({ added: Boolean(change.added), removed: Boolean(change.removed), text })
    }
  }
  return out
}

/**
 * How many lines an edit adds and removes, or null when this payload is not a single-pair edit.
 *
 * Shown on the collapsed row so the size of a change is legible before opening it: "+12 −3" is the
 * difference between a rename and a rewrite, and deciding whether to expand is exactly the decision
 * the collapsed row exists to support.
 */
export function editDiffStat(
  payload: Record<string, unknown> | null | undefined,
): { added: number; removed: number } | null {
  const lines = diffLinesForPayload(payload)
  if (lines === null) return null
  let added = 0
  let removed = 0
  for (const line of lines) {
    if (line.added) added += 1
    else if (line.removed) removed += 1
  }
  return added === 0 && removed === 0 ? null : { added, removed }
}
