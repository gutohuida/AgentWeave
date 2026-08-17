import { diffLinesForPayload } from '@/lib/editDiff'
import { tint } from '@/lib/colorTint'

/**
 * An edit tool call, rendered as its diff. The parsing — and the `+N −N` summary the collapsed
 * work row shows — lives in `@/lib/editDiff`, so this file exports a component and nothing else.
 */
export function ToolEditDiff({ payload }: { payload: Record<string, unknown> | null | undefined }) {
  const lines = diffLinesForPayload(payload)
  if (lines === null) return null

  return (
    <div data-testid="tool-edit-diff" className="mt-0.5 font-mono text-[12.5px]">
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
