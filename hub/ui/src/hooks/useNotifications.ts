import { useEffect, useMemo, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { ProjectSummary } from '@/api/projects'
import { classify } from '@/lib/notify/classify'
import { createNotifier, type NotifierToast } from '@/lib/notify/notifier'
import { loadNotifyPrefs } from '@/lib/notify/prefs'
import { playSound, unlockSoundOnFirstGesture } from '@/lib/sound/player'
import { useToastStore } from '@/lib/toast'
import { useSSE } from './useSSE'

/** The native app window's bridge (cli._AppWindowApi, pywebview js_api). Absent in a browser tab. */
interface AppWindowApi {
  attention?: (count: number) => Promise<unknown>
  foreground?: () => Promise<boolean>
  sound?: (enabled: boolean) => Promise<unknown>
}

export function appWindowApi(): AppWindowApi | null {
  const api = (window as { pywebview?: { api?: AppWindowApi } }).pywebview?.api
  return api ?? null
}

/** Change `agentweave-calls-you-with-its-own-sound`: every project's ask and fail events, from the
 *  one instance-wide stream, become a toast and the brand's sound; behind the window, a count in
 *  the title and a flashing taskbar button. Mounted once, in App. */
export function useNotifications(
  onOpen: (projectId: string, conversation?: NotifierToast['conversation']) => void,
  isViewing: (conversationId: string) => boolean = () => false,
) {
  const queryClient = useQueryClient()
  const onOpenRef = useRef(onOpen)
  onOpenRef.current = onOpen
  const isViewingRef = useRef(isViewing)
  isViewingRef.current = isViewing

  const notifier = useMemo(
    () =>
      createNotifier({
        // The native window's bridge answers from the OS foreground window; WebView2 keeps
        // document.hasFocus() true while the window is minimised or covered (drive, 2026-10-23).
        focused: () => {
          const foreground = appWindowApi()?.foreground
          return foreground ? foreground().then(Boolean) : document.hasFocus()
        },
        play: playSound,
        toast: (t, id) => {
          const input = {
            title: t.title,
            description: t.description,
            duration: 8000,
            action: { label: 'Open', onClick: () => onOpenRef.current(t.projectId, t.conversation) },
          }
          const store = useToastStore.getState()
          return id == null ? store.push(input) : store.update(id, input)
        },
        attention: (count) => {
          appWindowApi()?.attention?.(count)?.catch(() => {})
        },
        prefs: loadNotifyPrefs,
        projectName: (id) =>
          queryClient.getQueryData<ProjectSummary[]>(['projects'])?.find((p) => p.id === id)?.name ?? 'a project',
        viewing: (notice) => !!notice.conversationId && isViewingRef.current(notice.conversationId),
      }),
    [queryClient],
  )

  useSSE((event) => {
    const notice = classify(event.type, event.data)
    if (notice) notifier.notify(notice)
  })

  useEffect(() => {
    // `aw-app-focus` is the native window's bridge saying it came back to the front.
    const onFocus = () => notifier.focus()
    window.addEventListener('focus', onFocus)
    window.addEventListener('aw-app-focus', onFocus)
    const removeUnlock = unlockSoundOnFirstGesture()
    return () => {
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('aw-app-focus', onFocus)
      removeUnlock()
    }
  }, [notifier])
}
