import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

/* Change `windows-notifications-for-what-calls-the-operator`, task launcher-notify: the page hands
 * an `operator_notice` of a kind switched on for Windows to the window's bridge (FR-1), and a click
 * on a Windows notification reaches the page as `aw-app-open`, which opens its conversation (FR-6). */

let handler: ((event: { type: string; data: unknown }) => void) | null = null
vi.mock('@/hooks/useSSE', () => ({
  useSSE: (fn: (event: { type: string; data: unknown }) => void) => {
    handler = fn
  },
}))

let kinds: Record<string, boolean> | undefined
vi.mock('@/api/notifySettings', () => ({
  useWindowsNotifyKinds: () => ({ data: kinds }),
}))

vi.mock('@/lib/sound/player', () => ({
  playSound: vi.fn(),
  unlockSoundOnFirstGesture: () => () => {},
}))

import { useNotifications } from '@/hooks/useNotifications'

const NOTICE = {
  id: 'ntc-1',
  kind: 'ask',
  project_id: 'proj-a',
  agent: 'behindbot',
  conversation_id: 'conv-1',
  title: 'An agent needs you',
  text: 'behindbot asks: ship it?',
  source_event: 'question_asked',
}

function mount(onOpen = vi.fn()) {
  const client = new QueryClient()
  client.setQueryData(['projects'], [{ id: 'proj-a', name: 'Spike' }])
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  renderHook(() => useNotifications(onOpen), { wrapper })
  return onOpen
}

describe('Windows notifications from the page', () => {
  let notify: ReturnType<typeof vi.fn>

  beforeEach(() => {
    handler = null
    kinds = undefined
    notify = vi.fn(() => Promise.resolve(true))
    ;(window as unknown as { pywebview: unknown }).pywebview = {
      api: { notify, foreground: () => Promise.resolve(false), attention: () => Promise.resolve(true) },
    }
  })

  afterEach(() => {
    delete (window as unknown as { pywebview?: unknown }).pywebview
  })

  it('hands a question to the bridge with the project name, under the default kinds', () => {
    mount()
    handler!({ type: 'operator_notice', data: NOTICE })
    expect(notify).toHaveBeenCalledTimes(1)
    expect(notify).toHaveBeenCalledWith({ ...NOTICE, project_name: 'Spike' })
  })

  it('does not hand a kind switched off for Windows, and follows the Hub-held choice', () => {
    mount()
    handler!({ type: 'operator_notice', data: { ...NOTICE, id: 'ntc-2', kind: 'reply' } })
    expect(notify).not.toHaveBeenCalled()

    kinds = { ask: false, fail: true, done: false, reply: true }
    mount()
    handler!({ type: 'operator_notice', data: { ...NOTICE, id: 'ntc-3', kind: 'ask' } })
    expect(notify).not.toHaveBeenCalled()
    handler!({ type: 'operator_notice', data: { ...NOTICE, id: 'ntc-4', kind: 'reply' } })
    expect(notify).toHaveBeenCalledTimes(1)
  })

  it('hands nothing for an event that is not a notice', () => {
    mount()
    handler!({ type: 'question_asked', data: { id: 'q-1', from_agent: 'behindbot', project_id: 'proj-a' } })
    expect(notify).not.toHaveBeenCalled()
  })

  it('a bridge that refuses or fails is not an error', async () => {
    notify.mockImplementation(() => Promise.reject(new Error('shell gone')))
    mount()
    expect(() => handler!({ type: 'operator_notice', data: NOTICE })).not.toThrow()
    await Promise.resolve()
  })

  it('aw-app-open opens the conversation a click names', () => {
    const onOpen = mount()
    act(() => {
      window.dispatchEvent(
        new CustomEvent('aw-app-open', {
          detail: { project_id: 'proj-a', agent: 'behindbot', conversation_id: 'conv-1' },
        }),
      )
    })
    expect(onOpen).toHaveBeenCalledWith('proj-a', { agent: 'behindbot', conversationId: 'conv-1' })
  })

  it('aw-app-open without a conversation opens the project', () => {
    const onOpen = mount()
    act(() => {
      window.dispatchEvent(
        new CustomEvent('aw-app-open', { detail: { project_id: 'proj-a', agent: null, conversation_id: null } }),
      )
    })
    expect(onOpen).toHaveBeenCalledWith('proj-a', undefined)
  })
})
