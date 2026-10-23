import type { NotifyKind } from './classify'

/** The operator's notification preferences, per window (localStorage persists since the app window
 *  stopped running in private mode, f577b6b). `kinds` decides which kinds notify at all; `sound`
 *  silences every sound and keeps the toasts and the title count. */
export interface NotifyPrefs {
  sound: boolean
  /** 0..1 */
  volume: number
  kinds: Record<NotifyKind, boolean>
}

export const NOTIFY_PREFS_KEY = 'agentweave-notify'

export const DEFAULT_NOTIFY_PREFS: NotifyPrefs = {
  sound: true,
  volume: 0.8,
  kinds: { ask: true, fail: true, done: false },
}

export function loadNotifyPrefs(): NotifyPrefs {
  try {
    const raw = window.localStorage.getItem(NOTIFY_PREFS_KEY)
    if (!raw) return DEFAULT_NOTIFY_PREFS
    const p = JSON.parse(raw) as Partial<NotifyPrefs>
    const volume = typeof p.volume === 'number' ? Math.min(1, Math.max(0, p.volume)) : DEFAULT_NOTIFY_PREFS.volume
    const kinds = { ...DEFAULT_NOTIFY_PREFS.kinds }
    for (const k of Object.keys(kinds) as NotifyKind[]) {
      if (typeof p.kinds?.[k] === 'boolean') kinds[k] = p.kinds[k]
    }
    return { sound: typeof p.sound === 'boolean' ? p.sound : DEFAULT_NOTIFY_PREFS.sound, volume, kinds }
  } catch {
    return DEFAULT_NOTIFY_PREFS
  }
}

export function saveNotifyPrefs(prefs: NotifyPrefs): void {
  try {
    window.localStorage.setItem(NOTIFY_PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // storage unavailable: the choice lasts this session only
  }
}
