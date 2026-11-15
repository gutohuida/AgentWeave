import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { WatchTab, type WatchTone } from '@/components/panel/WatchTab'

const STATES: Record<WatchTone, string> = { working: 'working', waiting: 'waiting for your answer', idle: 'idle' }

function tab(tone: WatchTone) {
  return (
    <WatchTab
      peers={[
        { name: 'B', colorIndex: 1, state: STATES[tone], tone },
        { name: 'W', colorIndex: 2, state: STATES.working, tone: 'working' },
        { name: 'Q', colorIndex: 3, state: STATES.waiting, tone: 'waiting' },
        { name: 'I', colorIndex: 4, state: STATES.idle, tone: 'idle' },
      ]}
      peer="B"
      onPeerChange={() => {}}
      conversations={[{ id: 'c', title: 'C', when: 'now' }]}
      conversationId="c"
      onConversationChange={() => {}}
      onOpenConversation={() => {}}
    />
  )
}

// @ts-expect-error no node typings in the UI project
const { readFileSync } = (await import('node:fs')) as { readFileSync: (p: string, enc: string) => string }
const css = readFileSync('src/styles/panel-tabs.css', 'utf8')
const primitives = readFileSync('src/styles/primitives.css', 'utf8')
// jsdom resolves neither var() nor imported CSS, so the declared rules are read from the sheet.
const rule = (sheet: string, selector: string) => {
  const at = sheet.indexOf(selector)
  expect(at).toBeGreaterThanOrEqual(0)
  return sheet.slice(at, sheet.indexOf('}', at))
}

describe('Watch tab status colour', () => {
  it.each(['working', 'waiting', 'idle'] as const)('carries its own state marker: %s', (tone) => {
    render(tab(tone))
    expect(screen.getByTestId('watch-status')).toHaveAttribute('data-tone', tone)
    expect(screen.getByTestId('watch-mark')).toHaveAttribute('data-tone', tone)
  })

  it('colours green, amber and a neutral token, idle differing from waiting', () => {
    expect(rule(css, '.aw-watch-live[data-tone="working"]')).toMatch(/background: var\(--green\)/)
    expect(rule(css, '.aw-watch-live[data-tone="waiting"]')).toMatch(/background: var\(--amber\)/)
    expect(rule(css, '.aw-watch-live[data-tone="idle"]')).toMatch(/background: var\(--text-3\)/)
    expect(rule(css, '.aw-watch-status[data-tone="waiting"]')).toMatch(/--tone: var\(--amber\)/)
  })
})

describe('Watch tab status motion', () => {
  it('pulses working and waiting differently, and leaves idle still', () => {
    const working = rule(css, '.aw-watch-live[data-tone="working"]').match(/animation: (\S+) (\S+)/)!
    const waiting = rule(css, '.aw-watch-live[data-tone="waiting"]').match(/animation: (\S+) (\S+)/)!
    expect(`${working[1]} ${working[2]}`).not.toBe(`${waiting[1]} ${waiting[2]}`)
    expect(parseFloat(waiting[2])).toBeGreaterThan(parseFloat(working[2]))
    expect(rule(css, '.aw-watch-live[data-tone="idle"]')).toMatch(/animation: none/)
  })

  it('switches the mark when the same peer goes from working to waiting', () => {
    const { rerender } = render(tab('working'))
    expect(screen.getByTestId('watch-mark')).toHaveAttribute('data-tone', 'working')
    rerender(tab('waiting'))
    expect(screen.getByTestId('watch-mark')).toHaveAttribute('data-tone', 'waiting')
    expect(screen.getByTestId('watch-status')).toHaveTextContent('B is waiting for your answer')
  })

  it('keeps colour but stops the pulse under reduced motion', () => {
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(reduced).toMatch(/\.aw-watch-live \{ animation: none !important/)
    expect(rule(css, '.aw-watch-live[data-tone="working"]')).toMatch(/background: var\(--green\)/)
  })
})

describe('Watch tab agent menu', () => {
  it('marks each entry’s state detail with the same tone as the status line', async () => {
    render(tab('working'))
    fireEvent.keyDown(screen.getByRole('button', { name: 'Agent to watch' }), { key: 'Enter' })
    for (const [text, tone] of [
      ['working', 'working'],
      ['waiting for your answer', 'waiting'],
      ['idle', 'idle'],
    ]) {
      const detail = (await screen.findAllByText(text, { selector: '.aw-menu-item-detail' }))[0]
      expect(detail).toHaveAttribute('data-tone', tone)
    }
    expect(rule(primitives, '.aw-menu-item-detail[data-tone="waiting"]')).toMatch(/var\(--amber\)/)
  })
})
