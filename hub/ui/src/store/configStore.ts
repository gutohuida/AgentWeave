import { create } from 'zustand'

const STORAGE_KEY = 'agentweave-config'

interface StoredConfig {
  apiKey: string
  hubUrl: string
  projectId: string
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
    }
  }

  // 2. localStorage fallback — dev mode (npm run dev pointing at a separate Hub).
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { hubUrl: window.location.origin, ...JSON.parse(raw) } as StoredConfig
  } catch {}

  return { apiKey: '', hubUrl: window.location.origin, projectId: 'proj-default' }
}

interface ConfigState extends StoredConfig {
  isConfigured: boolean
  setConfig: (apiKey: string, hubUrl: string, projectId: string) => void
  clearConfig: () => void
}

const initial = loadConfig()

export const useConfigStore = create<ConfigState>()((set) => ({
  ...initial,
  isConfigured: !!initial.apiKey,
  setConfig: (apiKey, hubUrl, projectId) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId })) } catch {}
    set({ apiKey, hubUrl, projectId, isConfigured: !!apiKey })
  },
  clearConfig: () => {
    try { localStorage.removeItem(STORAGE_KEY) } catch {}
    set({ apiKey: '', hubUrl: window.location.origin, projectId: 'proj-default', isConfigured: false })
  },
}))
