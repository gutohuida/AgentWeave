import { create } from 'zustand'
import { fetchSetupToken } from '@/api/setup'

const SESSION_STORAGE_KEY = 'agentweave-session'
const PREFS_STORAGE_KEY = 'agentweave-prefs'

export type ThemeId = 'ocean' | 'cosmic' | 'solar' | 'forest' | 'rose'
export type ModeId  = 'light' | 'dark'
export type BootstrapState = 'pending' | 'ready' | 'failed'

interface StoredSession {
  apiKey: string
  hubUrl: string
  projectId: string
}

interface StoredPrefs {
  theme: ThemeId
  mode: ModeId
}

type StoredConfig = StoredSession & StoredPrefs

function readJSON<T>(storage: Storage, key: string): Partial<T> {
  try {
    const raw = storage.getItem(key)
    if (!raw) return {}
    return JSON.parse(raw) as Partial<T>
  } catch {
    return {}
  }
}

function loadConfig(): StoredConfig {
  const session = readJSON<StoredSession>(
    typeof window !== 'undefined' ? window.sessionStorage : localStorage,
    SESSION_STORAGE_KEY
  )
  const prefs = readJSON<StoredPrefs>(
    typeof window !== 'undefined' ? window.localStorage : (sessionStorage as unknown as Storage),
    PREFS_STORAGE_KEY
  )

  return {
    apiKey: session.apiKey ?? '',
    hubUrl: session.hubUrl ?? window.location?.origin ?? '',
    projectId: session.projectId ?? 'proj-default',
    theme: prefs.theme ?? 'cosmic',
    mode: prefs.mode ?? 'light',
  }
}

interface ConfigState extends StoredConfig {
  isConfigured: boolean
  bootstrapState: BootstrapState
  setConfig: (apiKey: string, hubUrl: string, projectId: string) => void
  setTheme: (theme: ThemeId) => void
  setMode:  (mode: ModeId) => void
  clearConfig: () => void
  bootstrap: () => Promise<void>
}

const initial = loadConfig()

function writeSession(apiKey: string, hubUrl: string, projectId: string): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({ apiKey, hubUrl, projectId } satisfies StoredSession)
    )
  } catch {
    // storage full or disabled — ignore
  }
}

function clearSession(): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY)
  } catch {
    // ignore
  }
}

function writePrefs(theme: ThemeId, mode: ModeId): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(
      PREFS_STORAGE_KEY,
      JSON.stringify({ theme, mode } satisfies StoredPrefs)
    )
  } catch {
    // storage full or disabled — ignore
  }
}

export const useConfigStore = create<ConfigState>()((set, get) => ({
  ...initial,
  isConfigured: !!initial.apiKey,
  bootstrapState: 'pending',

  setConfig: (apiKey, hubUrl, projectId) => {
    writeSession(apiKey, hubUrl, projectId)
    set({ apiKey, hubUrl, projectId, isConfigured: !!apiKey })
  },

  setTheme: (theme) => {
    const { mode } = get()
    writePrefs(theme, mode)
    set({ theme })
  },

  setMode: (mode) => {
    const { theme } = get()
    writePrefs(theme, mode)
    set({ mode })
  },

  clearConfig: () => {
    clearSession()
    set({ apiKey: '', hubUrl: window.location?.origin ?? '', projectId: 'proj-default', isConfigured: false })
  },

  bootstrap: async () => {
    // Don't overwrite an apiKey that already came from sessionStorage
    if (get().apiKey) {
      set({ bootstrapState: 'ready' })
      return
    }
    const token = await fetchSetupToken()
    if (token) {
      // Only persist if the user still hasn't configured a key (e.g. via SetupModal)
      if (!get().apiKey) {
        get().setConfig(token.apiKey, window.location.origin, token.projectId)
      }
      set({ bootstrapState: 'ready' })
    } else {
      set({ bootstrapState: 'failed' })
    }
  },
}))
