import { create } from 'zustand'

const STORAGE_KEY = 'agentweave-config'

export type ThemeId = 'ocean' | 'cosmic' | 'solar' | 'forest' | 'rose'

interface StoredConfig {
  apiKey: string
  hubUrl: string
  projectId: string
  theme: ThemeId
}

function loadConfig(): StoredConfig {
  // 1. Server-injected config — Hub serves the dashboard and injects its own key.
  //    This is the normal production path: no setup needed.
  const injected = (window as unknown as Record<string, unknown>).__AW_CONFIG__ as Partial<StoredConfig> | undefined
  if (injected?.apiKey) {
    return {
      apiKey: injected.apiKey,
      hubUrl: window.location.origin,
      projectId: injected.projectId ?? 'proj-default',
      theme: (injected.theme as ThemeId) ?? 'ocean',
    }
  }

  // 2. localStorage fallback — dev mode (npm run dev pointing at a separate Hub).
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { hubUrl: window.location.origin, theme: 'ocean', ...JSON.parse(raw) } as StoredConfig
  } catch {}

  return { apiKey: '', hubUrl: window.location.origin, projectId: 'proj-default', theme: 'ocean' }
}

interface ConfigState extends StoredConfig {
  isConfigured: boolean
  setConfig: (apiKey: string, hubUrl: string, projectId: string) => void
  setTheme: (theme: ThemeId) => void
  clearConfig: () => void
}

const initial = loadConfig()

export const useConfigStore = create<ConfigState>()((set, get) => ({
  ...initial,
  isConfigured: !!initial.apiKey,
  setConfig: (apiKey, hubUrl, projectId) => {
    const { theme } = get()
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId, theme })) } catch {}
    set({ apiKey, hubUrl, projectId, isConfigured: !!apiKey })
  },
  setTheme: (theme) => {
    const { apiKey, hubUrl, projectId } = get()
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId, theme })) } catch {}
    set({ theme })
  },
  clearConfig: () => {
    try { localStorage.removeItem(STORAGE_KEY) } catch {}
    set({ apiKey: '', hubUrl: window.location.origin, projectId: 'proj-default', isConfigured: false })
  },
}))
