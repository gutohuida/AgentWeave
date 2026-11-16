import { useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

export interface HubVersion {
  version?: string
  install?: string
  /** Present only for a Hub run from a git checkout. */
  commit?: string
  branch?: string
}

/** What `/health` says about the Hub this window is connected to; it needs no key. */
export function useHubVersion() {
  const hubUrl = useConfigStore((state) => state.hubUrl)
  return useQuery<HubVersion>({
    queryKey: ['app', 'hub-version', hubUrl],
    queryFn: async () => {
      const res = await fetch(`${hubUrl}/health`)
      if (!res.ok) throw new Error(`health ${res.status}`)
      return res.json() as Promise<HubVersion>
    },
    staleTime: 60_000,
  })
}
