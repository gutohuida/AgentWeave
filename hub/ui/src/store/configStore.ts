import { create } from 'zustand'
import { fetchSetupToken } from '@/api/setup'
import { fetchProjectSummaries } from '@/api/projects'

const SESSION_STORAGE_KEY = 'agentweave-session'
const PREFS_STORAGE_KEY = 'agentweave-prefs'
const SELECTED_PROJECT_STORAGE_KEY = 'agentweave-selected-project'

export type ModeId  = 'light' | 'dark'
export type BootstrapState = 'pending' | 'ready' | 'failed' | 'unreachable'

interface StoredSession {
  apiKey: string
  hubUrl: string
}

// A previously persisted `theme` key (the removed 5-theme picker) is simply
// not read — readJSON only pulls the fields this shape declares, so stale
// localStorage from an older build loads without failing.
interface StoredPrefs {
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
    mode: prefs.mode ?? 'light',
  }
}

function loadSelectedProject(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(SELECTED_PROJECT_STORAGE_KEY)
  } catch {
    return null
  }
}

interface ConfigState extends StoredConfig {
  /** The project currently open in the workspace, or null before the
   * project collection has loaded / when none is registered yet. Every
   * project-scoped API hook reads this reactively rather than an
   * imperative getState() call, so an in-flight request keeps the project
   * ID it started with even if the operator switches projects before the
   * response arrives (design.md: "Mutations receive project ID as an
   * immutable argument"). */
  selectedProjectId: string | null
  isConfigured: boolean
  bootstrapState: BootstrapState
  setConfig: (apiKey: string, hubUrl: string) => void
  setSelectedProject: (projectId: string | null) => void
  setMode:  (mode: ModeId) => void
  clearConfig: () => void
  bootstrap: () => Promise<void>
}

const initial = loadConfig()

function writeSession(apiKey: string, hubUrl: string): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({ apiKey, hubUrl } satisfies StoredSession)
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

function writeSelectedProject(projectId: string | null): void {
  if (typeof window === 'undefined') return
  try {
    if (projectId) {
      window.localStorage.setItem(SELECTED_PROJECT_STORAGE_KEY, projectId)
    } else {
      window.localStorage.removeItem(SELECTED_PROJECT_STORAGE_KEY)
    }
  } catch {
    // storage full or disabled — ignore
  }
}

function writePrefs(mode: ModeId): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(
      PREFS_STORAGE_KEY,
      JSON.stringify({ mode } satisfies StoredPrefs)
    )
  } catch {
    // storage full or disabled — ignore
  }
}

export const useConfigStore = create<ConfigState>()((set, get) => ({
  ...initial,
  selectedProjectId: loadSelectedProject(),
  isConfigured: !!initial.apiKey,
  bootstrapState: 'pending',

  setConfig: (apiKey, hubUrl) => {
    writeSession(apiKey, hubUrl)
    set({ apiKey, hubUrl, isConfigured: !!apiKey })
  },

  setSelectedProject: (projectId) => {
    writeSelectedProject(projectId)
    set({ selectedProjectId: projectId })
  },

  setMode: (mode) => {
    writePrefs(mode)
    set({ mode })
  },

  clearConfig: () => {
    clearSession()
    writeSelectedProject(null)
    set({
      apiKey: '',
      hubUrl: window.location?.origin ?? '',
      selectedProjectId: null,
      isConfigured: false,
    })
  },

  bootstrap: async () => {
    const current = get()
    const localHub = !current.hubUrl ||
      /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?\/?$/i.test(current.hubUrl)

    // For a local Hub, reconcile stale sessionStorage with the Hub's current
    // setup token. This prevents normal browser sessions from getting stuck
    // on an old key while private mode appears to work. The instance
    // credential carries no project selection — see api/setup.ts.
    const result = localHub ? await fetchSetupToken() : null
    if (result?.status === 'ok' && result.apiKey !== get().apiKey) {
      get().setConfig(result.apiKey, get().hubUrl || window.location.origin)
    }

    if (get().apiKey) {
      set({ bootstrapState: 'ready' })
      // Auto-select a project if none is persisted, or the persisted one no
      // longer exists in this instance's collection (e.g. after a reset).
      // Phase 5's rail is what lets the operator change this deliberately;
      // until then, the most-recently-opened project keeps the workspace
      // usable the same way the old implicit single project did.
      const { hubUrl, apiKey, selectedProjectId } = get()
      const projects = await fetchProjectSummaries(hubUrl, apiKey)
      const stillExists = projects.some((project) => project.id === selectedProjectId)
      if (!stillExists) {
        get().setSelectedProject(projects[0]?.id ?? null)
      }
    } else if (result?.status === 'unreachable') {
      // The Hub process itself didn't respond — asking the operator to paste
      // an API key can't fix that. Report the connection failure instead.
      set({ bootstrapState: 'unreachable' })
    } else {
      set({ bootstrapState: 'failed' })
    }
  },
}))
