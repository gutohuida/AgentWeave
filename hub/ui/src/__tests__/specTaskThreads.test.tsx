import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { render, fireEvent, cleanup, within } from '@testing-library/react'
import { TaskList } from '@/components/spec/page/SpecDocumentBody'
import { railLayout } from '@/components/spec/page/threads/railLayout'
import type { SpecTaskView } from '@/components/spec/page/model'

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})
afterEach(cleanup)

const task = (key: string, status: string, dependsOn: string[] = []): SpecTaskView =>
  ({ key, title: key.toUpperCase(), status, dependsOn, requirementIds: ['FR-1'], description: `about ${key}`, agent: null }) as unknown as SpecTaskView

function show(all: SpecTaskView[], handlers: { onJump?: (a: string) => void; onCopyLink?: (a: string) => void } = {}) {
  return render(
    <TaskList tasks={all} all={all} order="build" findingsFor={() => []} flash={null} onJump={handlers.onJump ?? (() => {})} onCopyLink={handlers.onCopyLink ?? (() => {})} />,
  )
}

describe('railLayout', () => {
  it('keeps a chain on one lane', () => {
    const { laneOf, lanes } = railLayout([task('a', 'approved'), task('b', 'approved', ['a']), task('c', 'pending', ['b'])])
    expect(lanes).toBe(1)
    expect(new Set(laneOf.values()).size).toBe(1)
  })

  it('gives three dependants three distinct runs, none across another knot', () => {
    const tasks = [task('a', 'approved'), task('b', 'pending', ['a']), task('c', 'pending', ['a']), task('d', 'pending', ['a'])]
    const { edges, laneOf } = railLayout(tasks)
    expect(edges).toHaveLength(3)
    const row = (k: string) => tasks.findIndex((t) => t.key === k)
    const byLane = new Map<number, Array<[number, number]>>()
    for (const e of edges) byLane.set(e.lane, [...(byLane.get(e.lane) ?? []), [row(e.from), row(e.to)]])
    for (const runs of byLane.values())
      for (let i = 0; i < runs.length; i++)
        for (let j = i + 1; j < runs.length; j++) expect(runs[i]![0] < runs[j]![1] && runs[j]![0] < runs[i]![1]).toBe(false)
    for (const e of edges)
      for (const t of tasks) if (laneOf.get(t.key) === e.lane) expect(row(e.from) < row(t.key) && row(t.key) < row(e.to)).toBe(false)
    expect(new Set(edges.map((e) => e.lane)).size).toBeGreaterThan(1)
  })
})

describe('build-order threads', () => {
  it('each thread carries its prerequisite state and the legend lists the states present', () => {
    const { container, getByLabelText } = show([
      task('a', 'approved'),
      task('b', 'pending'),
      task('c', 'in_progress'),
      task('d', 'rejected'),
      task('e', 'pending', ['a', 'b', 'c', 'd']),
    ])
    const states = [...container.querySelectorAll<SVGPathElement>('path.aw-st-thread')].map((p) => p.dataset.state)
    expect(new Set(states)).toEqual(new Set(['done', 'waiting', 'active', 'rejected']))
    const legend = within(getByLabelText('Thread colours'))
    for (const label of ['Done', 'In progress', 'Not started', 'Sent back']) expect(legend.getByText(label)).toBeTruthy()
  })

  it('hover and focus light the chain and dim the rest; leaving restores', () => {
    const { container } = show([task('a', 'approved'), task('b', 'approved', ['a']), task('c', 'pending', ['b']), task('d', 'pending')])
    const row = (k: string) => container.querySelector<HTMLElement>(`[data-task="${k}"]`)!
    const lit = () => ['a', 'b', 'c', 'd'].map((k) => row(k).dataset.lit)
    expect(lit()).toEqual([undefined, undefined, undefined, undefined])
    fireEvent.mouseEnter(row('b'))
    expect(lit()).toEqual(['on', 'on', 'on', 'dim'])
    fireEvent.mouseLeave(row('b'))
    expect(lit()).toEqual([undefined, undefined, undefined, undefined])
    fireEvent.focus(row('b'))
    expect(lit()).toEqual(['on', 'on', 'on', 'dim'])
    fireEvent.blur(row('b'))
    expect(lit()).toEqual([undefined, undefined, undefined, undefined])
  })

  it('still expands a description, copies a link and jumps from a requirement chip', () => {
    const jumps: string[] = []
    const copies: string[] = []
    const { container, getByRole, getByLabelText } = show([task('a', 'approved')], { onJump: (a) => jumps.push(a), onCopyLink: (a) => copies.push(a) })
    const title = getByRole('button', { name: 'A' })
    expect(title.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(title)
    expect(title.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(getByLabelText('Copy a link to A'))
    expect(copies).toHaveLength(1)
    fireEvent.click(getByRole('button', { name: 'FR-1' }))
    expect(jumps).toHaveLength(1)
    expect(container.querySelector('li[data-task="a"]')!.id).toBeTruthy()
  })
})
