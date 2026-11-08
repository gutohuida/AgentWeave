import { useEffect, useMemo, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWindowsNotifyKinds, type WindowsNotifyKinds } from '@/api/notifySettings'
import type { ProjectSummary } from '@/api/projects'
import { noticeFrom } from '@/lib/notify/classify'
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
  /** Show an `operator_notice` as a Windows notification; the bridge refuses it while the window
   *  is in front, and answers false rather than failing (cli._AppWindowApi.notify). */
  notify?: (notice: Record<string, unknown>) => Promise<boolean>
  /** The close prompt's answer (`components/app/ClosePrompt`). */
  close_choice?: (choice: 'stop' | 'keep' | 'cancel') => Promise<unknown>
  /** App settings' 'Closing the window leaves AgentWeave running', kept by the launcher. */
  close_keeps_running?: () => Promise<boolean>
  set_close_keeps_running?: (on: boolean) => Promise<boolean>
}

export function appWindowApi(): AppWindowApi | null {
  const api = (window as { pywebview?: { api?: AppWindowApi } }).pywebview?.api
  return api ?? null
}

/** The Hub's defaults until its answer arrives (hub/hub/operator_notices.py DEFAULT_WINDOWS_KINDS). */
export const DEFAULT_WINDOWS_KINDS: WindowsNotifyKinds = { ask: true, fail: true, done: false, reply: false }

/** `aw-app-open`: the launcher saying a Windows notification was clicked (cli._app_open_script). */
export interface AppOpenDetail {
  project_id?: string | null
  agent?: string | null
  conversation_id?: string | null
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
  // Which kinds reach Windows: the Hub's choice, separate from the in-app switches (FR-10).
  const { data: windowsKinds } = useWindowsNotifyKinds()
  const windowsKindsRef = useRef<WindowsNotifyKinds>(DEFAULT_WINDOWS_KINDS)
  windowsKindsRef.current = windowsKinds ?? DEFAULT_WINDOWS_KINDS

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
    const notice = noticeFrom(event.type, event.data)
    if (!notice) return
    notifier.notify(notice)
    // Behind the window, a kind switched on for Windows also becomes a Windows notification, drawn
    // from the same notice; the bridge refuses it while the window is in front (FR-1, FR-3).
    const notify = appWindowApi()?.notify
    if (notify && windowsKindsRef.current[notice.kind]) {
      const projectName = queryClient
        .getQueryData<ProjectSummary[]>(['projects'])
        ?.find((p) => p.id === notice.projectId)?.name
      const payload = { ...(event.data as Record<string, unknown>), ...(projectName ? { project_name: projectName } : {}) }
      notify(payload)?.catch(() => {})
    }
  })

  useEffect(() => {
    // `aw-app-focus` is the native window's bridge saying it came back to the front.
    const onFocus = () => notifier.focus()
    // `aw-app-open` is a Windows notification's click: go where its notice points (FR-6).
    const onAppOpen = (e: Event) => {
      const detail = (e as CustomEvent<AppOpenDetail>).detail
      if (!detail?.project_id) return
      onOpenRef.current(
        detail.project_id,
        detail.agent && detail.conversation_id
          ? { agent: detail.agent, conversationId: detail.conversation_id }
          : undefined,
      )
    }
    window.addEventListener('focus', onFocus)
    window.addEventListener('aw-app-focus', onFocus)
    window.addEventListener('aw-app-open', onAppOpen)
    const removeUnlock = unlockSoundOnFirstGesture()
    return () => {
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('aw-app-focus', onFocus)
      window.removeEventListener('aw-app-open', onAppOpen)
      removeUnlock()
    }
  }, [notifier])
}
