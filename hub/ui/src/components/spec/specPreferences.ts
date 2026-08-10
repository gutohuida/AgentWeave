// Bounded presentation preferences for the conversation workspace.
//
// FR-10 allows presentation values here and nothing else: no messages, no bridge payloads, no
// document content, no credentials. Anything unreadable, unparseable, or out of range resets to
// the default rather than propagating a corrupt value into layout state.
//
// One value survives from the three-column workspace: the width of the conversation column when a
// document is open beside it. `chatCollapsed` and `libraryMode` are gone with the surfaces that
// read them — whether a document is open is now part of the destination, and the Library/History
// control was deleted along with the navigator column.

const STORAGE_KEY = 'aw.spec.presentation.v1'

export interface SpecPreferences {
  conversationWidth: number
}

/**
 * The conversation column's range while a document is open beside it.
 *
 * There is no design cap. The first version bounded the conversation at 560 on the reasoning that
 * "a specification is a document to read", which made the document panel impossible to shrink —
 * the operator could not give the conversation more than 560 however much room there was
 * (operator, 2026-08-10: "the screen on the right is too big and we can't make it shorter"). The
 * boundary is now the operator's, floored on each side only where a pane stops being usable.
 *
 * The default is where the composer's control row stops wrapping — measured, not chosen.
 */
export const CONVERSATION_MIN_WIDTH = 380
export const CONVERSATION_DEFAULT_WIDTH = 480

/** What the document panel needs before it stops being worth showing as a column. Below
 *  `CONVERSATION_MIN_WIDTH + SPEC_DOC_MIN_WIDTH` the panel becomes an overlay instead. */
export const SPEC_DOC_MIN_WIDTH = 360

/** A sanity bound on the *stored* value, not a design decision: the real ceiling is whatever the
 *  measurement leaves once the document has its minimum, and it is applied at render time. This
 *  exists so a hand-edited or stale value cannot produce a nonsense width. */
export const CONVERSATION_STORAGE_MAX = 4000

export const DEFAULT_SPEC_PREFERENCES: SpecPreferences = {
  conversationWidth: CONVERSATION_DEFAULT_WIDTH,
}

export function clampConversationWidth(value: number): number {
  return Math.min(CONVERSATION_STORAGE_MAX, Math.max(CONVERSATION_MIN_WIDTH, Math.round(value)))
}

/** A finite number, or the default. `NaN` and `Infinity` are numbers to `typeof`, and both
 *  survive a clamp as themselves — so they are rejected here rather than clamped. */
function readWidth(value: unknown, clamp: (n: number) => number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? clamp(value) : fallback
}

export function loadSpecPreferences(): SpecPreferences {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable (privacy mode, disabled cookies).
    return { ...DEFAULT_SPEC_PREFERENCES }
  }
  if (!raw) return { ...DEFAULT_SPEC_PREFERENCES }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ...DEFAULT_SPEC_PREFERENCES }
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { ...DEFAULT_SPEC_PREFERENCES }
  }

  const value = parsed as Record<string, unknown>
  return {
    conversationWidth: readWidth(
      value.conversationWidth,
      clampConversationWidth,
      DEFAULT_SPEC_PREFERENCES.conversationWidth,
    ),
  }
}

/** Writes only the allowed keys, so extra fields can never be persisted. */
export function saveSpecPreferences(prefs: SpecPreferences): void {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ conversationWidth: clampConversationWidth(prefs.conversationWidth) }),
    )
  } catch {
    // Persisting preferences is best-effort; layout must still work without it.
  }
}

export const SPEC_PREFERENCES_KEY = STORAGE_KEY
