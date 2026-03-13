import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ConfigState {
  apiKey: string
  hubUrl: string
  projectId: string
  isConfigured: boolean
  setConfig: (apiKey: string, hubUrl: string, projectId: string) => void
  clearConfig: () => void
}

export const useConfigStore = create<ConfigState>()(
  persist(
    (set) => ({
      apiKey: '',
      hubUrl: 'http://localhost:8000',
      projectId: 'proj-default',
      isConfigured: false,
      setConfig: (apiKey, hubUrl, projectId) =>
        set({ apiKey, hubUrl, projectId, isConfigured: !!apiKey }),
      clearConfig: () =>
        set({ apiKey: '', hubUrl: 'http://localhost:8000', projectId: 'proj-default', isConfigured: false }),
    }),
    { name: 'agentweave-config' }
  )
)
