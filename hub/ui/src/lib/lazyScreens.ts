import { createElement, lazy, useState, type ComponentType } from 'react'

/**
 * The screens the app opens on demand rather than in its first script.
 *
 * Opening a project lands on the Overview with the rail beside it; everything else (a
 * conversation, a tab, a dialog) arrives with a click. The app was one 1.5 MB script, which cost
 * about 2 s of script time on a CPU slowed six times before anything drew. Each screen here is its
 * own chunk; `prefetchScreens` loads them all once the page has drawn and gone idle, so opening one
 * later finds it already loaded and nothing is slower than it was.
 */
const loaders: Array<() => Promise<unknown>> = []

type AnyComponent = ComponentType<Record<string, unknown>>

/** `name` from the module `load` imports, as a component of the same type that loads on demand.
 *
 * Once its chunk has loaded (by a first use, or by `prefetchScreens`), the screen renders at once,
 * with no Suspense fallback: `React.lazy` alone suspends on its first render even when the chunk is
 * already here. An instance keeps the path it mounted with, so a screen opened while its chunk was
 * still loading is never remounted (and its state lost) when the chunk arrives. */
function screen<M, K extends keyof M>(load: () => Promise<M>, name: K): M[K] {
  let loaded: AnyComponent | null = null
  let pending: Promise<AnyComponent> | null = null
  const fetchScreen = () =>
    (pending ??= load().then(
      (module) => (loaded = module[name] as unknown as AnyComponent),
      (error: unknown) => {
        pending = null // a failed fetch (the Hub restarting) is tried again by the next use
        throw error
      },
    ))
  loaders.push(fetchScreen)
  const Lazy = lazy(async () => ({ default: await fetchScreen() }))
  function Screen(props: Record<string, unknown>) {
    const [Direct] = useState(() => loaded)
    return Direct ? createElement(Direct, props) : createElement(Lazy, props)
  }
  Screen.displayName = String(name)
  return Screen as unknown as M[K]
}

/** Every screen's chunk, loaded now. For tests that render the app and expect a screen at once. */
export function loadAllScreens(): Promise<unknown[]> {
  return Promise.all(loaders.map((load) => load()))
}

export const ConversationView = screen(() => import('@/components/agents/ConversationView'), 'ConversationView')
export const AgentCreateDialog = screen(() => import('@/components/agents/AgentCreateDialog'), 'AgentCreateDialog')
export const NewConversationSurface = screen(() => import('@/components/agents/NewConversationSurface'), 'NewConversationSurface')
export const JobsScreen = screen(() => import('@/components/jobs/JobsScreen'), 'JobsScreen')
export const ActivityScreen = screen(() => import('@/components/activity/ActivityScreen'), 'ActivityScreen')
export const ThreadScreen = screen(() => import('@/components/thread/ThreadScreen'), 'ThreadScreen')
export const AppSettingsScreen = screen(() => import('@/components/settings/AppSettingsScreen'), 'AppSettingsScreen')
export const ProjectSettingsScreen = screen(() => import('@/components/settings/ProjectSettingsScreen'), 'ProjectSettingsScreen')
export const VaultScreen = screen(() => import('@/components/vault/VaultScreen'), 'VaultScreen')
export const SpecPage = screen(() => import('@/components/spec/SpecPage'), 'SpecPage')
export const EvidenceBrowser = screen(() => import('@/components/evidence/EvidenceBrowser'), 'EvidenceBrowser')
export const RequirementStory = screen(() => import('@/components/spec/RequirementStory'), 'RequirementStory')
export const TasksScreen = screen(() => import('@/components/tasks/TasksScreen'), 'TasksScreen')
export const AgentSettingsPage = screen(() => import('@/components/agents/AgentSettingsPage'), 'AgentSettingsPage')
export const QuestionsPanel = screen(() => import('@/components/questions/QuestionsPanel'), 'QuestionsPanel')
export const ArchivedAgentNotice = screen(() => import('@/components/agents/ArchivedAgentNotice'), 'ArchivedAgentNotice')

let prefetched = false

/** Load every screen above, one per idle period, starting `delayMs` after the call. Idempotent. */
export function prefetchScreens(delayMs = 1500): void {
  if (prefetched) return
  prefetched = true
  const idle = (cb: () => void) => {
    const ric = (window as unknown as { requestIdleCallback?: (cb: () => void, o?: object) => number })
      .requestIdleCallback
    if (ric) ric(cb, { timeout: 5000 })
    else setTimeout(cb, 50)
  }
  const queue = [...loaders]
  const next = () => {
    const load = queue.shift()
    if (!load) return
    load().then(
      () => idle(next),
      () => idle(next),
    )
  }
  setTimeout(() => idle(next), delayMs)
}
