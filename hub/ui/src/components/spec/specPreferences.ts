// Bounded presentation preferences for the Spec workspace.
//
// FR-10 allows exactly two values here and nothing else: no messages, no
// bridge payloads, no document content, no credentials. Anything unreadable,
// unparseable, or out of range resets to the default rather than propagating
// a corrupt value into layout state.

const STORAGE_KEY = 'aw.spec.presentation.v1'

export type LibraryMode = 'library' | 'history'

export interface SpecPreferences {
  chatCollapsed: boolean
  libraryMode: LibraryMode
}

export const DEFAULT_SPEC_PREFERENCES: SpecPreferences = {
  chatCollapsed: false,
  libraryMode: 'library',
}

const LIBRARY_MODES: readonly LibraryMode[] = ['library', 'history']

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
  }
}

/** Writes only the two allowed keys, so extra fields can never be persisted. */
export function saveSpecPreferences(prefs: SpecPreferences): void {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ chatCollapsed: prefs.chatCollapsed, libraryMode: prefs.libraryMode })
    )
  } catch {
    // Persisting preferences is best-effort; layout must still work without it.
  }
}

export const SPEC_PREFERENCES_KEY = STORAGE_KEY
