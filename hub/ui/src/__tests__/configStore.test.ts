import { describe, it, expect, beforeEach } from 'vitest'
import { useConfigStore } from '@/store/configStore'

const SESSION_KEY = 'agentweave-session'
const PREFS_KEY = 'agentweave-prefs'
const SELECTED_PROJECT_KEY = 'agentweave-selected-project'

describe('S4 — configStore: apiKey lives in sessionStorage, prefs in localStorage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    useConfigStore.setState({
      apiKey: '',
      hubUrl: 'http://hub.test',
      selectedProjectId: null,
      theme: 'cosmic',
      mode: 'light',
      isConfigured: false,
      bootstrapState: 'pending',
    })
  })

  it('setConfig writes apiKey/hubUrl to sessionStorage and never to localStorage', () => {
    useConfigStore.getState().setConfig('aw_live_SECRET', 'http://hub.test')

    const sessionRaw = sessionStorage.getItem(SESSION_KEY)
    expect(sessionRaw).not.toBeNull()
    const session = JSON.parse(sessionRaw!) as Record<string, unknown>
    expect(session.apiKey).toBe('aw_live_SECRET')
    expect(session.hubUrl).toBe('http://hub.test')
    expect(session.projectId).toBeUndefined()

    const localRaw = localStorage.getItem(SESSION_KEY)
    expect(localRaw).toBeNull()
    const prefsRaw = localStorage.getItem(PREFS_KEY)
    if (prefsRaw !== null) {
      const prefs = JSON.parse(prefsRaw) as Record<string, unknown>
      expect(prefs.apiKey).toBeUndefined()
    }
  })

  it('setSelectedProject writes the project ID to its own localStorage key, not the session', () => {
    useConfigStore.getState().setSelectedProject('proj-x')

    expect(localStorage.getItem(SELECTED_PROJECT_KEY)).toBe('proj-x')
    expect(useConfigStore.getState().selectedProjectId).toBe('proj-x')
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()

    useConfigStore.getState().setSelectedProject(null)
    expect(localStorage.getItem(SELECTED_PROJECT_KEY)).toBeNull()
  })

  it('setTheme writes only theme/mode to localStorage and never touches sessionStorage', () => {
    useConfigStore.getState().setConfig('aw_live_SECRET', 'http://hub.test')
    sessionStorage.clear()
    useConfigStore.getState().setTheme('forest')

    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as Record<string, unknown>
    expect(prefs.theme).toBe('forest')
    expect(prefs.apiKey).toBeUndefined()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  })

  it('setMode writes only theme/mode to localStorage and never touches sessionStorage', () => {
    useConfigStore.getState().setMode('dark')

    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as Record<string, unknown>
    expect(prefs.mode).toBe('dark')
    expect(prefs.apiKey).toBeUndefined()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  })

  it('clearConfig removes apiKey from sessionStorage, clears the selected project, and resets isConfigured', () => {
    useConfigStore.getState().setConfig('aw_live_SECRET', 'http://hub.test')
    useConfigStore.getState().setSelectedProject('proj-x')
    useConfigStore.getState().clearConfig()

    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
    expect(localStorage.getItem(SELECTED_PROJECT_KEY)).toBeNull()
    const state = useConfigStore.getState()
    expect(state.apiKey).toBe('')
    expect(state.selectedProjectId).toBeNull()
    expect(state.isConfigured).toBe(false)
  })
})
