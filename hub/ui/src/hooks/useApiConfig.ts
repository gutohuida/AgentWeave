import { useConfigStore } from '@/store/configStore'

export function useApiConfig() {
  const { apiKey, hubUrl, projectId, isConfigured, setConfig, clearConfig } = useConfigStore()
  return { apiKey, hubUrl, projectId, isConfigured, setConfig, clearConfig }
}
