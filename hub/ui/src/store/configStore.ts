import { create } from 'zustand'

const STORAGE_KEY = 'agentweave-config'

export type ThemeId = 'ocean' | 'cosmic' | 'solar' | 'forest' | 'rose'
export type ModeId  = 'light' | 'dark'

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

  // 2. Server-injected config takes precedence for connection settings
  const injected = (window as unknown as Record<string, unknown>).__AW_CONFIG__ as Partial<StoredConfig> | undefined
  if (injected?.apiKey) {
    return {
      apiKey:    injected.apiKey,
      hubUrl:    window.location.origin,
      projectId: injected.projectId ?? 'proj-default',
      theme:     stored.theme ?? 'cosmic',      // Use stored theme preference
      mode:      stored.mode  ?? 'light',       // Use stored mode preference
    }
  }

  // 3. localStorage fallback
  if (stored.apiKey) {
    return { 
      hubUrl: window.location.origin, 
      theme: 'cosmic', 
      mode: 'light', 
      ...stored 
    } as StoredConfig
  }

  return { apiKey: '', hubUrl: window.location.origin, projectId: 'proj-default', theme: 'cosmic', mode: 'light' }
}

interface ConfigState extends StoredConfig {
  isConfigured: boolean
  setConfig: (apiKey: string, hubUrl: string, projectId: string) => void
  setTheme: (theme: ThemeId) => void
  setMode:  (mode: ModeId) => void
  clearConfig: () => void
}

const initial = loadConfig()

export const useConfigStore = create<ConfigState>()((set, get) => ({
  ...initial,
  isConfigured: !!initial.apiKey,

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
}))
