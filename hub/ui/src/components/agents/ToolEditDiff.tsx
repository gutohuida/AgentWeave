import { diffLines } from 'diff'
import { tint } from '@/lib/colorTint'

/**
 * design.md D2 — a structural check on the parsed JSON, not a tool-name allow-list. `Edit`'s
 * payload has `old_string`/`new_string` at the top level and matches; `MultiEdit`'s pair lives
 * one level down inside `edits[]` and never matches — declines by design, not oversight.
 */
export function ToolEditDiff({ payload }: { payload: Record<string, unknown> | null | undefined }) {
  const lines = diffLinesForPayload(payload)
  if (lines === null) return null

  return (
    <div className="mt-0.5 font-mono text-[12.5px]">
      {lines.map((line, i) => (
        <div
          key={i}
          className="whitespace-pre-wrap px-1"
          style={{
            background: line.added ? tint('var(--green)') : line.removed ? tint('var(--red)') : undefined,
            color: line.added ? 'var(--green)' : line.removed ? 'var(--red)' : 'var(--text-3)',
          }}
        >
          {line.added ? '+ ' : line.removed ? '- ' : '  '}
          {line.text}
        </div>
      ))}
    </div>
  )
}

function diffLinesForPayload(
  payload: Record<string, unknown> | null | undefined,
): Array<{ added: boolean; removed: boolean; text: string }> | null {
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
  const out: Array<{ added: boolean; removed: boolean; text: string }> = []
  for (const change of changes) {
    const changeLines = change.value.split('\n')
    // diffLines keeps a trailing '' from the final newline — drop it so we don't render an
    // empty extra row per hunk.
    if (changeLines[changeLines.length - 1] === '') changeLines.pop()
    for (const text of changeLines) {
      out.push({ added: change.added, removed: change.removed, text })
    }
  }
  return out
}
