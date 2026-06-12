import { create } from 'zustand'
import { fetchSetupToken } from '@/api/setup'

const STORAGE_KEY = 'agentweave-config'

export type ThemeId = 'ocean' | 'cosmic' | 'solar' | 'forest' | 'rose'
export type ModeId  = 'light' | 'dark'
export type BootstrapState = 'pending' | 'ready' | 'failed'

interface StoredConfig {
  apiKey: string
  hubUrl: string
  projectId: string
  theme: ThemeId
  mode: ModeId
}

function loadConfig(): StoredConfig {
  // 1. Load from localStorage for theme/mode persistence
  let stored: Partial<StoredConfig> = {}
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) stored = JSON.parse(raw) as Partial<StoredConfig>
  } catch {}

  // 2. localStorage fallback (apiKey may already be present from a prior session)
  if (stored.apiKey) {
    return {
      hubUrl: window.location.origin,
      theme: 'cosmic',
      mode: 'light',
      ...stored,
    } as StoredConfig
  }

  // 3. No key in localStorage — App will call bootstrap() to try /setup/token
  return {
    apiKey: '',
    hubUrl: window.location.origin,
    projectId: 'proj-default',
    theme: 'cosmic',
    mode: 'light',
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

export const useConfigStore = create<ConfigState>()((set, get) => ({
  ...initial,
  isConfigured: !!initial.apiKey,
  bootstrapState: 'pending',

  setConfig: (apiKey, hubUrl, projectId) => {
    const { theme, mode } = get()
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId, theme, mode })) } catch {}
    set({ apiKey, hubUrl, projectId, isConfigured: !!apiKey })
  },

  setTheme: (theme) => {
    const { apiKey, hubUrl, projectId, mode } = get()
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId, theme, mode })) } catch {}
    set({ theme })
  },

  setMode: (mode) => {
    const { apiKey, hubUrl, projectId, theme } = get()
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId, theme, mode })) } catch {}
    set({ mode })
  },

  clearConfig: () => {
    try { localStorage.removeItem(STORAGE_KEY) } catch {}
    set({ apiKey: '', hubUrl: window.location.origin, projectId: 'proj-default', isConfigured: false })
  },

  bootstrap: async () => {
    // Don't overwrite an apiKey that already came from localStorage
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
