import { describe, it, expect, afterEach } from 'vitest'
import { act, fireEvent, render, waitFor } from '@testing-library/react'
import { WatchTab } from '@/components/panel/WatchTab'

const props = {
  peers: [{ name: 'B', colorIndex: 1, state: 'working', working: true }],
  peer: 'B',
  onPeerChange: () => {},
  conversations: [{ id: 'c3', title: 'C3', when: 'now' }],
  conversationId: 'c3',
  onConversationChange: () => {},
  onOpenConversation: () => {},
}

// jsdom has no layout: give the body a 100px viewport over 1000px of content.
const proto = HTMLElement.prototype
const original = {
  scrollHeight: Object.getOwnPropertyDescriptor(proto, 'scrollHeight'),
  clientHeight: Object.getOwnPropertyDescriptor(proto, 'clientHeight'),
}
Object.defineProperty(proto, 'scrollHeight', { configurable: true, get: () => 1000 })
Object.defineProperty(proto, 'clientHeight', { configurable: true, get: () => 100 })
afterEach(() => {
  if (original.scrollHeight) Object.defineProperty(proto, 'scrollHeight', original.scrollHeight)
  if (original.clientHeight) Object.defineProperty(proto, 'clientHeight', original.clientHeight)
})

function body(container: HTMLElement) {
  return container.querySelector('.aw-watch-body') as HTMLDivElement
}

describe('WatchTab follows the newest output', () => {
  it('stays pinned to the bottom while new entries arrive', async () => {
    const { container } = render(<WatchTab {...props}><div id="slot" /></WatchTab>)
    const el = body(container)
    expect(el.scrollTop).toBe(1000)
    el.scrollTop = 880 // within 48px of the bottom: still "at the bottom"
    fireEvent.scroll(el)
    act(() => { container.querySelector('#slot')!.appendChild(document.createElement('p')) })
    await waitFor(() => expect(el.scrollTop).toBe(1000))
  })

  it('leaves an operator who scrolled up where they are', async () => {
    const { container } = render(<WatchTab {...props}><div id="slot" /></WatchTab>)
    const el = body(container)
    el.scrollTop = 200
    fireEvent.scroll(el)
    act(() => { container.querySelector('#slot')!.appendChild(document.createElement('p')) })
    await new Promise((r) => setTimeout(r, 20))
    expect(el.scrollTop).toBe(200)
  })
})
