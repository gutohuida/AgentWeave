// Mirrors `hub/hub/file_mentions.py` (F409). The Claude CLI expands an unescaped `@path` in a
// prompt into a file attachment, so operator-derived text that the Hub composes into a prompt
// carries a backslash before each at-sign.

/** Design D8: escape every at-sign in text that will be sent as part of a prompt. */
export function neutraliseFileMentions(text: string): string {
  return text.replace(/@/g, '\\@')
}

/**
 * Design D10: true when every at-sign in `value` is at index 0 or directly after `/`. Such a
 * value survives being typed as `@value` (measured row `picker_quoted_nested`); any other
 * at-sign would start a second, live mention inside the inserted one.
 */
export function isSafeMentionValue(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    if (value[i] === '@' && i !== 0 && value[i - 1] !== '/') return false
  }
  return true
}
