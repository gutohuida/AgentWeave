import { describe, it, expect, beforeEach, vi } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync } from 'node:fs'
import { classify } from '@/lib/notify/classify'
import { createNotifier, BURST_MS, GATHER_MS, type NotifierDeps } from '@/lib/notify/notifier'
import { DEFAULT_NOTIFY_PREFS, loadNotifyPrefs, saveNotifyPrefs, type NotifyPrefs } from '@/lib/notify/prefs'

// Change `agentweave-calls-you-with-its-own-sound` (trial spdoc-3e64f37b5229). Every payload below is
// the shape the Hub broadcasts, with the `project_id` hub/hub/sse.py stamps into the operator stream.
const P1 = 'proj-one'
const P2 = 'proj-two'
const QUESTION = { id: 'q-1', from_agent: 'Developer', blocking: false, project_id: P1 } // questions.py
const PERMISSION = { id: 'pr-1', agent: 'Developer', tool_name: 'Bash', run_id: 'run-1', project_id: P1 } // agent_trigger.py
const STALL = {
  // stalls.view()
  id: 'stall-1', key: 'k', cause: 'task_stuck', reason: 'The task has not moved for 2 hours', task_id: 'task-1',
  loop_id: null, first_seen_at: '2026-10-23T10:00:00', last_seen_at: '2026-10-23T10:00:00', seen_count: 1,
  conversation_id: null, mender_turns: 0, outcome: null, outcome_detail: '', ended_at: null, project_id: P2,
}
const RUN_FAILED = { agent: 'Tester', run_id: 'run-2', error: 'Run failed (exit 1)', project_id: P2 } // agent_trigger.py
const LOOP_STOPPED = { job_id: 'job-1', loop_id: 'loop-1', reason: 'budget reached', project_id: P1 } // scheduler.py
const LOOP_DRAINED = { job_id: 'job-1', loop_id: 'loop-1', reason: 'loop queue is empty', project_id: P1 }
const CHAIN = { entry_id: 'qe-1', agent: 'Reviewer', hop_depth: 9, hop_budget: 8, project_id: P1 } // messages.py

describe('classify: which Hub events call the operator', () => {
  it('asks for a question and a permission', () => {
    expect(classify('question_asked', QUESTION)).toMatchObject({ kind: 'ask', projectId: P1 })
    expect(classify('question_asked', QUESTION)?.text).toContain('Developer')
    expect(classify('permission_requested', PERMISSION)).toMatchObject({ kind: 'ask', projectId: P1 })
    expect(classify('permission_requested', PERMISSION)?.text).toContain('Bash')
  })

  it('fails for a stall, a failed run, a suspended chain and a loop stopped short', () => {
    expect(classify('stall_recorded', STALL)).toMatchObject({ kind: 'fail', projectId: P2 })
    expect(classify('run_failed', RUN_FAILED)).toMatchObject({ kind: 'fail', projectId: P2 })
    expect(classify('run_failed', RUN_FAILED)?.text).toContain('Tester')
    expect(classify('queue_chain_suspended', CHAIN)).toMatchObject({ kind: 'fail' })
    expect(classify('loop_stopped', LOOP_STOPPED)).toMatchObject({ kind: 'fail' })
  })

  it('is done when a loop drained its queue', () => {
    expect(classify('loop_stopped', LOOP_DRAINED)).toMatchObject({ kind: 'done' })
  })

  it('ignores everyday traffic and events with no project', () => {
    expect(classify('run_completed', { agent: 'Developer', run_id: 'r', project_id: P1 })).toBeNull()
    expect(classify('task_updated', { id: 't', status: 'completed', project_id: P1 })).toBeNull()
    expect(classify('question_answered', { id: 'q-1', project_id: P1 })).toBeNull()
    expect(classify('question_asked', { id: 'q-1', from_agent: 'Developer', blocking: false })).toBeNull()
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
    h.notifier.notify(classify('question_asked', QUESTION)!)
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
    h.notifier.notify(classify('question_asked', { ...QUESTION, id: 'q-2' })!)
    h.notifier.notify(classify('permission_requested', PERMISSION)!)
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
    h.notifier.notify(classify('question_asked', QUESTION)!)
    vi.advanceTimersByTime(1000)
    h.notifier.notify(classify('stall_recorded', STALL)!)
    vi.advanceTimersByTime(BURST_MS)
    expect(h.played.map((p) => p.kind)).toEqual(['fail'])
    expect(h.toasts.size).toBe(1)
    const [grouped] = [...h.toasts.values()]
    expect(`${grouped.title} ${grouped.description ?? ''}`).toMatch(/2 projects|AgentWeave.*Docs site|Docs site.*AgentWeave/)

    h.notifier.notify(classify('question_asked', { ...QUESTION, id: 'q-3' })!)
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played).toHaveLength(2)
    expect(h.toasts.size).toBe(2)
  })

  it('done is silent by default; a kind turned on notifies; sound off keeps the toast and drops the sound', () => {
    const h = harness()
    h.notifier.notify(classify('loop_stopped', LOOP_DRAINED)!)
    vi.advanceTimersByTime(GATHER_MS)
    expect(h.played).toHaveLength(0)
    expect(h.toasts.size).toBe(0)

    const on = harness({}, { ...DEFAULT_NOTIFY_PREFS, kinds: { ...DEFAULT_NOTIFY_PREFS.kinds, done: true } })
    on.notifier.notify(classify('loop_stopped', LOOP_DRAINED)!)
    vi.advanceTimersByTime(GATHER_MS)
    expect(on.played.map((p) => p.kind)).toEqual(['done'])

    const muted = harness({}, { ...DEFAULT_NOTIFY_PREFS, sound: false })
    muted.notifier.notify(classify('question_asked', QUESTION)!)
    vi.advanceTimersByTime(GATHER_MS)
    expect(muted.played).toHaveLength(0)
    expect(muted.toasts.size).toBe(1)
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
    h.notifier.notify(classify('question_asked', QUESTION)!)
    await vi.advanceTimersByTimeAsync(GATHER_MS)
    expect(h.counts[h.counts.length - 1]).toBe(1)
    expect(document.title).toBe('(1) AgentWeave')
    expect(h.played).toHaveLength(1)
    expect(h.played[0].gain).toBeGreaterThan(0.5 * DEFAULT_NOTIFY_PREFS.volume)
  })
})

describe('preferences', () => {
  beforeEach(() => localStorage.clear())

  it('default to sound on, ask and fail on, done off, and survive a reload', () => {
    expect(loadNotifyPrefs()).toEqual(DEFAULT_NOTIFY_PREFS)
    expect(DEFAULT_NOTIFY_PREFS.sound).toBe(true)
    expect(DEFAULT_NOTIFY_PREFS.kinds).toEqual({ ask: true, fail: true, done: false })
    saveNotifyPrefs({ ...DEFAULT_NOTIFY_PREFS, volume: 0.3, kinds: { ask: true, fail: false, done: true } })
    expect(loadNotifyPrefs()).toMatchObject({ volume: 0.3, kinds: { ask: true, fail: false, done: true } })
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
