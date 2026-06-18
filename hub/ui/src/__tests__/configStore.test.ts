import { describe, it, expect, beforeEach } from 'vitest'
import { useConfigStore } from '@/store/configStore'

const SESSION_KEY = 'agentweave-session'
const PREFS_KEY = 'agentweave-prefs'

describe('S4 — configStore: apiKey lives in sessionStorage, prefs in localStorage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    useConfigStore.setState({
      apiKey: '',
      hubUrl: 'http://hub.test',
      projectId: 'proj-default',
      theme: 'cosmic',
      mode: 'light',
      isConfigured: false,
      bootstrapState: 'pending',
    })
  })

  it('setConfig writes apiKey/hubUrl/projectId to sessionStorage and never to localStorage', () => {
    useConfigStore.getState().setConfig('aw_live_SECRET', 'http://hub.test', 'proj-x')

    const sessionRaw = sessionStorage.getItem(SESSION_KEY)
    expect(sessionRaw).not.toBeNull()
    const session = JSON.parse(sessionRaw!) as Record<string, unknown>
    expect(session.apiKey).toBe('aw_live_SECRET')
    expect(session.hubUrl).toBe('http://hub.test')
    expect(session.projectId).toBe('proj-x')

    const localRaw = localStorage.getItem(SESSION_KEY)
    expect(localRaw).toBeNull()
    const prefsRaw = localStorage.getItem(PREFS_KEY)
    if (prefsRaw !== null) {
      const prefs = JSON.parse(prefsRaw) as Record<string, unknown>
      expect(prefs.apiKey).toBeUndefined()
    }
  })

  it('setTheme writes only theme/mode to localStorage and never touches sessionStorage', () => {
    useConfigStore.getState().setConfig('aw_live_SECRET', 'http://hub.test', 'proj-x')
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

  it('clearConfig removes apiKey from sessionStorage and resets isConfigured', () => {
    useConfigStore.getState().setConfig('aw_live_SECRET', 'http://hub.test', 'proj-x')
    useConfigStore.getState().clearConfig()

    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
    const state = useConfigStore.getState()
    expect(state.apiKey).toBe('')
    expect(state.isConfigured).toBe(false)
  })
})
