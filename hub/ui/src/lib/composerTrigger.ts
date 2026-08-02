// Composer trigger detection and range replacement. Own implementation of the behaviour
// described in openspec/changes/2026-07-30-hub-native-experience/design.md section B
// ("Composer trigger detection") — not a port of that file, per its own instruction
// ("Adopt the behaviour and the boundary rules; write our own implementation").

export type ComposerTriggerKind = 'path' | 'skill' | 'slash-command'

export interface ComposerTriggerMatch {
  kind: ComposerTriggerKind
  query: string
  rangeStart: number
  rangeEnd: number
}

const WHITESPACE_RE = /\s/

const MENTION_PREFIX: Record<'path' | 'skill', string> = {
  path: '@',
  skill: '$',
}

/**
 * Detect an open trigger at `cursor` in `text`, or return null.
 *
 * Slash commands only match at line start (`/^\/(\S*)$/` against the current line's
 * prefix up to the cursor) so a URL mid-sentence never opens a menu. `@path`/`$skill`
 * match by walking backward from the cursor to the nearest whitespace boundary and
 * inspecting that token's first character — so they can open anywhere in a line, not
 * only at its start.
 */
export function detectComposerTrigger(text: string, cursor: number): ComposerTriggerMatch | null {
  const lineStart = text.lastIndexOf('\n', cursor - 1) + 1
  const linePrefix = text.slice(lineStart, cursor)

  const slashMatch = /^\/(\S*)$/.exec(linePrefix)
  if (slashMatch) {
    return { kind: 'slash-command', query: slashMatch[1], rangeStart: lineStart, rangeEnd: cursor }
  }

  let tokenStart = cursor
  while (tokenStart > 0 && !WHITESPACE_RE.test(text[tokenStart - 1])) {
    tokenStart -= 1
  }
  if (tokenStart === cursor) return null

  const triggerChar = text[tokenStart]
  const kind = (Object.keys(MENTION_PREFIX) as Array<'path' | 'skill'>).find(
    (candidate) => MENTION_PREFIX[candidate] === triggerChar,
  )
  if (!kind) return null

  return { kind, query: text.slice(tokenStart + 1, cursor), rangeStart: tokenStart, rangeEnd: cursor }
}

/** Replace `[start, end)` with `replacement`, returning the new text and new cursor position. */
export function replaceTextRange(
  text: string,
  start: number,
  end: number,
  replacement: string,
): { text: string; cursor: number } {
  return {
    text: text.slice(0, start) + replacement + text.slice(end),
    cursor: start + replacement.length,
  }
}

/** Quote-escape a mention value if it contains whitespace; otherwise return it unchanged. */
export function quoteMentionValue(value: string): string {
  if (!WHITESPACE_RE.test(value)) return value
  return `"${value.replace(/"/g, '\\"')}"`
}

/**
 * Accept a menu result for an open `trigger`: builds the trigger-char-prefixed,
 * quote-escaped insertion text and replaces the trigger's own matched range with it
 * (the trigger character itself is part of that range, so it must be part of the
 * replacement too).
 */
export function acceptTriggerResult(
  text: string,
  trigger: ComposerTriggerMatch,
  value: string,
): { text: string; cursor: number } {
  const prefix = trigger.kind === 'slash-command' ? '/' : MENTION_PREFIX[trigger.kind]
  const insertion = prefix + quoteMentionValue(value)
  return replaceTextRange(text, trigger.rangeStart, trigger.rangeEnd, insertion)
}
