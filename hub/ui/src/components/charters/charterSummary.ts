const SUMMARY_LENGTH = 160

/**
 * A short summary for the collapsed row.
 *
 * `line-clamp` alone clamps only what is painted — the full document stays in the DOM, so a
 * screen reader would read every charter in full and the disclosure would buy its user
 * nothing. Truncating here makes the collapsed state actually be a summary.
 *
 * The leading `# Heading` is dropped because it repeats the charter's name, which is already
 * the line above it.
 */
export function charterSummary(content: string): string {
  const withoutTitle = content.replace(/^\s*#\s+.*(\r?\n|$)/, '')
  const flattened = withoutTitle.replace(/\s+/g, ' ').trim()
  if (flattened.length <= SUMMARY_LENGTH) return flattened
  const cut = flattened.slice(0, SUMMARY_LENGTH)
  const lastSpace = cut.lastIndexOf(' ')
  return `${(lastSpace > SUMMARY_LENGTH / 2 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`
}
