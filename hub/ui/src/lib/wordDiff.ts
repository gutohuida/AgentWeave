/** One run of a word diff: text kept, added or removed, whitespace included so it joins back. */
export interface WordPart {
  kind: 'same' | 'added' | 'removed'
  text: string
}

/** Words and the whitespace after them, so joining the tokens gives the text back exactly. */
function tokens(text: string): string[] {
  return text.match(/\S+\s*|\s+/g) ?? []
}

/**
 * A word-level diff of two wordings (slice requirement-story): the longest common subsequence of
 * words, adjacent runs of one kind merged. Requirement statements are a sentence or two, so the
 * quadratic table is a few hundred cells.
 */
export function wordDiff(before: string, after: string): WordPart[] {
  const a = tokens(before)
  const b = tokens(after)
  const same = (x: string, y: string) => x.trimEnd() === y.trimEnd()
  const table: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] = same(a[i], b[j]) ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  const parts: WordPart[] = []
  const push = (kind: WordPart['kind'], text: string) => {
    const last = parts[parts.length - 1]
    if (last && last.kind === kind) last.text += text
    else parts.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (same(a[i], b[j])) {
      push('same', b[j])
      i++
      j++
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      push('removed', a[i++])
    } else {
      push('added', b[j++])
    }
  }
  while (i < a.length) push('removed', a[i++])
  while (j < b.length) push('added', b[j++])
  return parts
}
