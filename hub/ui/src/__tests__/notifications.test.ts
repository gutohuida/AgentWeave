import { describe, it, expect, beforeEach, vi } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync } from 'node:fs'
import { noticeFrom } from '@/lib/notify/classify'
import { createNotifier, BURST_MS, GATHER_MS, type NotifierDeps } from '@/lib/notify/notifier'
import { DEFAULT_NOTIFY_PREFS, loadNotifyPrefs, saveNotifyPrefs, type NotifyPrefs } from '@/lib/notify/prefs'

// Changes `agentweave-calls-you-with-its-own-sound` and `windows-notifications-for-what-calls-the-operator`.
// Which events call the operator is decided by the Hub (hub/tests/test_operator_notices.py); the page
// draws its toasts from the `operator_notice` events it publishes, shaped as below.
const P1 = 'proj-one'
const P2 = 'proj-two'
let seq = 0
function wire(kind: string, project_id: string, text: string, extra: Record<string, unknown> = {}) {
  return { id: `ntc-${++seq}`, kind, project_id, agent: null, conversation_id: null, title: 'T', text, source_event: 'x', ...extra }
}
const notice = (data: ReturnType<typeof wire>) => noticeFrom('operator_notice', data)!
const QUESTION = () => notice(wire('ask', P1, 'Developer asked you a question', { agent: 'Developer', conversation_id: 'conv-q' }))
const PERMISSION = () => notice(wire('ask', P1, 'Developer wants permission for Bash', { agent: 'Developer' }))
const STALL = () => notice(wire('fail', P2, 'Work stalled: The task has not moved for 2 hours'))
const LOOP_DRAINED = () => notice(wire('done', P1, 'A loop finished its queue'))
const REPLIED = (conversation_id = 'conv-1') => notice(wire('reply', P1, 'Architect replied', { agent: 'Architect', conversation_id }))

describe('noticeFrom: the page reads the Hub notice', () => {
  it('reads an operator_notice into a notice', () => {
    expect(noticeFrom('operator_notice', wire('reply', P1, 'Architect replied', { agent: 'Architect', conversation_id: 'conv-1' }))).toMatchObject({
      kind: 'reply', projectId: P1, text: 'Architect replied', agent: 'Architect', conversationId: 'conv-1',
    })
  })

  it('ignores every other event, and a notice with no project, kind or text', () => {
    expect(noticeFrom('question_asked', { id: 'q-1', from_agent: 'Developer', project_id: P1 })).toBeNull()
    expect(noticeFrom('run_failed', { agent: 'Tester', project_id: P1 })).toBeNull()
    expect(noticeFrom('operator_notice', { ...wire('ask', P1, 'x'), project_id: '' })).toBeNull()
    expect(noticeFrom('operator_notice', wire('other', P1, 'x'))).toBeNull()
    expect(noticeFrom('operator_notice', wire('ask', P1, ''))).toBeNull()
  })
})

function harness(over: Partial<NotifierDeps> = {}, prefs: NotifyPrefs = DEFAULT_NOTIFY_PREFS) {
  let focused = true
  let toastSeq = 0
  const played: Array<{ kind: string; gain: number }> = []
  const toasts = new Map<number, { title: string; description?: string }>()
  const counts: number[] = []
  const deps: NotifierDeps = {
    focused: () => focused,
    play: (kind, gain) => played.push({ kind, gain }),
    toast: (t, id) => {
      const key = id ?? ++toastSeq
      toasts.set(key, t)
      return key
    },
    attention: (n) => counts.push(n),
    prefs: () => prefs,
    projectName: (id) => ({ [P1]: 'AgentWeave', [P2]: 'Docs site' })[id] ?? id,
    ...over,
  }
  const notifier = createNotifier(deps)
  return {
    notifier, played, toasts, counts,
    setFocused: (f: boolean) => { focused = f },
  }
}

describe('the notifier: front, behind, bursts', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
  })

  it('in front: one toast naming the project and a quiet sound; behind: the normal level, a count, cleared on focus', () => {
    const h = harness()
    h.notifier.notify(QUESTION())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.toasts.size).toBe(1)
    const [first] = [...h.toasts.values()]
    expect(`${first.title} ${first.description ?? ''}`).toContain('AgentWeave')
    expect(h.played).toHaveLength(1)
    expect(h.played[0].kind).toBe('ask')
    const quiet = h.played[0].gain
    expect(h.counts.filter((n) => n > 0)).toHaveLength(0)

    vi.advanceTimersByTime(BURST_MS)
    h.setFocused(false)
    h.notifier.notify(QUESTION())
    h.notifier.notify(PERMISSION())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played).toHaveLength(2)
    expect(h.played[1].gain).toBeGreaterThan(quiet)
    expect(h.counts[h.counts.length - 1]).toBe(2)
    expect(document.title).toMatch(/^\(2\) /)

    h.setFocused(true)
    h.notifier.focus()
    expect(h.counts[h.counts.length - 1]).toBe(0)
    expect(document.title).not.toMatch(/^\(\d+\) /)
  })

  it('a burst across two projects is one sound, the more urgent kind, and one toast naming both', () => {
    const h = harness()
    h.notifier.notify(QUESTION())
    vi.advanceTimersByTime(1000)
    h.notifier.notify(STALL())
    vi.advanceTimersByTime(BURST_MS)
    expect(h.played.map((p) => p.kind)).toEqual(['fail'])
    expect(h.toasts.size).toBe(1)
    const [grouped] = [...h.toasts.values()]
    expect(`${grouped.title} ${grouped.description ?? ''}`).toMatch(/2 projects|AgentWeave.*Docs site|Docs site.*AgentWeave/)

    h.notifier.notify(QUESTION())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played).toHaveLength(2)
    expect(h.toasts.size).toBe(2)
  })

  it('done is silent by default; a kind turned on notifies; sound off keeps the toast and drops the sound', () => {
    const h = harness()
    h.notifier.notify(LOOP_DRAINED())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played).toHaveLength(0)
    expect(h.toasts.size).toBe(0)

    const on = harness({}, { ...DEFAULT_NOTIFY_PREFS, kinds: { ...DEFAULT_NOTIFY_PREFS.kinds, done: true } })
    on.notifier.notify(LOOP_DRAINED())
    vi.advanceTimersByTime(GATHER_MS)
    expect(on.played.map((p) => p.kind)).toEqual(['done'])

    const muted = harness({}, { ...DEFAULT_NOTIFY_PREFS, sound: false })
    muted.notifier.notify(QUESTION())
    vi.advanceTimersByTime(GATHER_MS)
    expect(muted.played).toHaveLength(0)
    expect(muted.toasts.size).toBe(1)
  })
})

describe('a reply', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    document.title = 'AgentWeave'
  })

  it('sounds the bright pair and opens its conversation; an ask in the same burst wins the sound', () => {
    const h = harness()
    h.notifier.notify(REPLIED())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played.map((p) => p.kind)).toEqual(['reply'])
    const [toast] = [...h.toasts.values()] as Array<{ title: string; conversation?: unknown }>
    expect(toast.title).toContain('Architect')
    expect(toast.conversation).toEqual({ agent: 'Architect', conversationId: 'conv-1' })

    vi.advanceTimersByTime(BURST_MS)
    h.notifier.notify(REPLIED())
    h.notifier.notify(QUESTION())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played.map((p) => p.kind)).toEqual(['reply', 'ask'])
  })

  it('is silent while the operator is in front, looking at that conversation; behind, it calls', async () => {
    const h = harness({ viewing: (n) => n.conversationId === 'conv-1' })
    h.notifier.notify(REPLIED())
    await vi.advanceTimersByTimeAsync(GATHER_MS)
    expect(h.played).toHaveLength(0)
    expect(h.toasts.size).toBe(0)

    h.notifier.notify(REPLIED('conv-2'))
    await vi.advanceTimersByTimeAsync(BURST_MS)
    expect(h.played.map((p) => p.kind)).toEqual(['reply'])

    h.setFocused(false)
    h.notifier.notify(REPLIED())
    await vi.advanceTimersByTimeAsync(GATHER_MS)
    expect(h.played).toHaveLength(2)
    expect(document.title).toBe('(1) AgentWeave')
  })

  it('a question opens its conversation, and is not silenced by watching it', async () => {
    const h = harness({ viewing: () => true })
    h.notifier.notify(QUESTION())
    await vi.advanceTimersByTimeAsync(GATHER_MS)
    expect(h.played.map((p) => p.kind)).toEqual(['ask'])
    const [toast] = [...h.toasts.values()] as Array<{ conversation?: unknown }>
    expect(toast.conversation).toEqual({ agent: 'Developer', conversationId: 'conv-q' })
  })

  it('can be turned off', () => {
    const h = harness({}, { ...DEFAULT_NOTIFY_PREFS, kinds: { ...DEFAULT_NOTIFY_PREFS.kinds, reply: false } })
    h.notifier.notify(REPLIED())
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played).toHaveLength(0)
    expect(h.toasts.size).toBe(0)
  })
})

describe('the native window answers whether it is in front', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    document.title = 'AgentWeave'
  })

  // In pywebview's WebView2 document.hasFocus() stays true while the window is minimised or covered
  // (drive, 2026-10-23), so the app window's bridge answers from the OS foreground window instead,
  // asynchronously.
  it('an asynchronous "not in front" still counts the call and sounds at the normal level', async () => {
    const h = harness({ focused: () => Promise.resolve(false) })
    h.notifier.notify(QUESTION())
    await vi.advanceTimersByTimeAsync(GATHER_MS)
    expect(h.counts[h.counts.length - 1]).toBe(1)
    expect(document.title).toBe('(1) AgentWeave')
    expect(h.played).toHaveLength(1)
    expect(h.played[0].gain).toBeGreaterThan(0.5 * DEFAULT_NOTIFY_PREFS.volume)
  })
})

describe('preferences', () => {
  beforeEach(() => localStorage.clear())

  it('default to sound on, ask, fail and reply on, done off, and survive a reload', () => {
    expect(loadNotifyPrefs()).toEqual(DEFAULT_NOTIFY_PREFS)
    expect(DEFAULT_NOTIFY_PREFS.sound).toBe(true)
    expect(DEFAULT_NOTIFY_PREFS.kinds).toEqual({ ask: true, fail: true, done: false, reply: true })
    saveNotifyPrefs({ ...DEFAULT_NOTIFY_PREFS, volume: 0.3, kinds: { ask: true, fail: false, done: true, reply: false } })
    expect(loadNotifyPrefs()).toMatchObject({ volume: 0.3, kinds: { ask: true, fail: false, done: true, reply: false } })
  })

  it('saved before reply existed, reply reads as its default', () => {
    localStorage.setItem('agentweave-notify', JSON.stringify({ sound: true, volume: 0.5, kinds: { ask: true, fail: true, done: false } }))
    expect(loadNotifyPrefs().kinds.reply).toBe(true)
  })
})

describe('one synth', () => {
  it('the app plays a byte-identical copy of brand/sound/agentweave-sound.js', () => {
    // Vitest runs from hub/ui.
    const ui = readFileSync('src/lib/sound/agentweave-sound.js', 'utf8')
    const brand = readFileSync('../../brand/sound/agentweave-sound.js', 'utf8')
    expect(ui.length).toBeGreaterThan(1000)
    expect(ui).toBe(brand)
  })
})
