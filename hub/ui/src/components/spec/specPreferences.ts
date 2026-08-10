// Bounded presentation preferences for the Spec workspace.
//
// FR-10 allows presentation values here and nothing else: no messages, no
// bridge payloads, no document content, no credentials. Anything unreadable,
// unparseable, or out of range resets to the default rather than propagating
// a corrupt value into layout state.
//
// The two pane widths joined the two original values when the workspace's fixed 260/520/360
// layout was replaced by the shared `PaneResizer`: a width the operator chose that does not
// survive a reload is a control that does not work. They are clamped on read as well as on
// write, so a stored value from a wider screen — or a hand-edited one — cannot produce a pane
// too narrow to use or wide enough to crush the document.

const STORAGE_KEY = 'aw.spec.presentation.v1'

export type LibraryMode = 'library' | 'history'

export interface SpecPreferences {
  chatCollapsed: boolean
  libraryMode: LibraryMode
  navWidth: number
  chatWidth: number
}

export const SPEC_NAV_MIN_WIDTH = 180
export const SPEC_NAV_MAX_WIDTH = 420
export const SPEC_CHAT_MIN_WIDTH = 300
export const SPEC_CHAT_MAX_WIDTH = 640

export const DEFAULT_SPEC_PREFERENCES: SpecPreferences = {
  chatCollapsed: false,
  libraryMode: 'library',
  navWidth: 260,
  chatWidth: 360,
}

const LIBRARY_MODES: readonly LibraryMode[] = ['library', 'history']

export function clampNavWidth(value: number): number {
  return Math.min(SPEC_NAV_MAX_WIDTH, Math.max(SPEC_NAV_MIN_WIDTH, Math.round(value)))
}

export function clampChatWidth(value: number): number {
  return Math.min(SPEC_CHAT_MAX_WIDTH, Math.max(SPEC_CHAT_MIN_WIDTH, Math.round(value)))
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
    chatCollapsed:
      typeof value.chatCollapsed === 'boolean'
        ? value.chatCollapsed
        : DEFAULT_SPEC_PREFERENCES.chatCollapsed,
    libraryMode: LIBRARY_MODES.includes(value.libraryMode as LibraryMode)
      ? (value.libraryMode as LibraryMode)
      : DEFAULT_SPEC_PREFERENCES.libraryMode,
    navWidth: readWidth(value.navWidth, clampNavWidth, DEFAULT_SPEC_PREFERENCES.navWidth),
    chatWidth: readWidth(value.chatWidth, clampChatWidth, DEFAULT_SPEC_PREFERENCES.chatWidth),
  }
}

/** Writes only the allowed keys, so extra fields can never be persisted. */
export function saveSpecPreferences(prefs: SpecPreferences): void {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        chatCollapsed: prefs.chatCollapsed,
        libraryMode: prefs.libraryMode,
        navWidth: clampNavWidth(prefs.navWidth),
        chatWidth: clampChatWidth(prefs.chatWidth),
      })
    )
  } catch {
    // Persisting preferences is best-effort; layout must still work without it.
  }
}

export const SPEC_PREFERENCES_KEY = STORAGE_KEY
