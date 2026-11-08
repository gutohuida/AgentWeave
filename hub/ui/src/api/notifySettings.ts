import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** Which kinds of notice reach Windows: question (`ask`), failure (`fail`), `done` and `reply`.
 *  Held by the Hub (hub/hub/api/v1/notify_settings.py), instance-wide, so the launcher's watcher
 *  applies it with no window open; separate from the page's in-app switches (`lib/notify/prefs`).
 *  Change `windows-notifications-for-what-calls-the-operator`, FR-10. */
export interface WindowsNotifyKinds {
  ask: boolean
  fail: boolean
  done: boolean
  reply: boolean
}

const NOTIFY_SETTINGS = '/api/v1/notify-settings'
const KEY = ['notify-settings'] as const

export function useWindowsNotifyKinds() {
  const { isConfigured } = useConfigStore()
  return useQuery<WindowsNotifyKinds>({
    queryKey: KEY,
    queryFn: () => getJson<WindowsNotifyKinds>(NOTIFY_SETTINGS),
    enabled: isConfigured,
  })
}

export function useSetWindowsNotifyKinds() {
  const queryClient = useQueryClient()
  return useMutation<WindowsNotifyKinds, unknown, WindowsNotifyKinds>({
    mutationFn: (kinds) => putJson<WindowsNotifyKinds>(NOTIFY_SETTINGS, kinds),
    onSuccess: (kinds) => queryClient.setQueryData(KEY, kinds),
  })
}
