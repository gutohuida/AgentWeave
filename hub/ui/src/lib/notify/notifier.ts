import type { Notice, NotifyKind } from './classify'
import type { NotifyPrefs } from './prefs'

/** A burst is one sound and one toast: the events of the first GATHER_MS decide the sound (the
 *  more urgent kind wins), and every event until BURST_MS after the first joins the same toast. */
export const GATHER_MS = 1200
export const BURST_MS = 4000

/** In front the sound is quiet; behind it has to carry across the room (identity record §7). */
const GAIN_FRONT = 0.35
const GAIN_BEHIND = 0.7

const URGENCY: Record<NotifyKind, number> = { done: 0, reply: 1, ask: 2, fail: 3 }

export interface NotifierToast {
  title: string
  description?: string
  /** The project the toast's action opens: the latest event's. */
  projectId: string
  /** A reply's conversation, which the toast's action opens instead of the project. */
  conversation?: { agent: string; conversationId: string }
}

export interface NotifierDeps {
  /** Whether the window is in front. The native app window answers through its bridge (a
   *  promise): WebView2 keeps document.hasFocus() true while the window is minimised or covered. */
  focused: () => boolean | Promise<boolean>
  play: (kind: NotifyKind, gain: number) => void
  /** Show a toast, or replace the one `id` names; returns its id. */
  toast: (t: NotifierToast, id?: number) => number
  /** The unseen count behind the window, for the native window's title and taskbar. */
  attention: (count: number) => void
  prefs: () => NotifyPrefs
  projectName: (projectId: string) => string
  /** Whether the app is showing this notice's conversation. A reply the operator is watching
   *  arrive, with the window in front, calls nobody. */
  viewing?: (notice: Notice) => boolean
}

interface Burst {
  notices: Notice[]
  toastId: number
  startedAt: number
}

const COUNT_PREFIX = /^\(\d+\) /

function setTitleCount(count: number) {
  if (typeof document === 'undefined') return
  const base = document.title.replace(COUNT_PREFIX, '') || 'AgentWeave'
  document.title = count > 0 ? `(${count}) ${base}` : base
}

function describe(notices: Notice[], name: (id: string) => string): Omit<NotifierToast, 'projectId'> {
  if (notices.length === 1) return { title: notices[0].text, description: name(notices[0].projectId) }
  const projects = [...new Set(notices.map((n) => n.projectId))]
  const needsYou = notices.some((n) => n.kind === 'ask')
  const failed = notices.some((n) => n.kind === 'fail')
  const replies = notices.every((n) => n.kind === 'reply')
  const what = replies ? 'replied' : needsYou && !failed ? 'need you' : failed && !needsYou ? 'stalled or failed' : 'happened'
  const title = `${notices.length} things ${what}`
  const description = projects.length === 1
    ? `in ${name(projects[0])}`
    : projects.length === 2
      ? `in ${name(projects[0])} and ${name(projects[1])}`
      : `across ${projects.length} projects`
  return { title, description }
}

export function createNotifier(deps: NotifierDeps) {
  let burst: Burst | null = null
  let unseen = 0

  function whenFocus(then: (front: boolean) => void) {
    let answer: boolean | Promise<boolean>
    try {
      answer = deps.focused()
    } catch {
      answer = true
    }
    if (typeof answer === 'boolean') then(answer)
    else answer.then(then, () => then(true))
  }

  function soundBurst(b: Burst) {
    const prefs = deps.prefs()
    if (!prefs.sound || prefs.volume <= 0) return
    const kind = b.notices.reduce((k, n) => (URGENCY[n.kind] > URGENCY[k] ? n.kind : k), b.notices[0].kind)
    whenFocus((front) => deps.play(kind, prefs.volume * (front ? GAIN_FRONT : GAIN_BEHIND)))
  }

  function toastFor(notices: Notice[], latest: Notice): NotifierToast {
    const t: NotifierToast = { ...describe(notices, deps.projectName), projectId: latest.projectId }
    if (latest.kind === 'reply' && latest.agent && latest.conversationId) {
      t.conversation = { agent: latest.agent, conversationId: latest.conversationId }
    }
    return t
  }

  function notify(notice: Notice) {
    if (!deps.prefs().kinds[notice.kind]) return
    if (notice.kind === 'reply' && deps.viewing?.(notice)) {
      whenFocus((front) => {
        if (!front) deliver(notice)
      })
      return
    }
    deliver(notice)
  }

  function deliver(notice: Notice) {
    const now = Date.now()
    if (burst && now - burst.startedAt < BURST_MS) {
      burst.notices.push(notice)
      deps.toast(toastFor(burst.notices, notice), burst.toastId)
    } else {
      const b: Burst = { notices: [notice], toastId: 0, startedAt: now }
      b.toastId = deps.toast(toastFor(b.notices, notice))
      burst = b
      setTimeout(() => soundBurst(b), GATHER_MS)
    }
    whenFocus((front) => {
      if (front) return
      unseen += 1
      setTitleCount(unseen)
      deps.attention(unseen)
    })
  }

  /** The window came back to the front: what it was calling for has been seen. */
  function focus() {
    if (unseen === 0) return
    unseen = 0
    setTitleCount(0)
    deps.attention(0)
  }

  return { notify, focus }
}

export type Notifier = ReturnType<typeof createNotifier>
