/** The commits typed into a field, split on spaces and commas. */
export function parseCommits(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean)
}
