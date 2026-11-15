import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { render, fireEvent, cleanup, within } from '@testing-library/react'
import { TaskList } from '@/components/spec/page/SpecDocumentBody'
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
  ({ key, title: key.toUpperCase(), status, dependsOn, requirementIds: [], description: '', agent: null }) as unknown as SpecTaskView

function show(all: SpecTaskView[]) {
  return render(<TaskList tasks={all} all={all} order="build" findingsFor={() => []} flash={null} onJump={() => {}} onCopyLink={() => {}} />)
}

describe('build-order threads', () => {
  it('ac-fanout: three dependants get three separate lanes at least 8px apart', () => {
    const { container } = show([task('a', 'approved'), task('b', 'pending', ['a']), task('c', 'pending', ['a']), task('d', 'pending', ['a'])])
    const paths = [...container.querySelectorAll<SVGPathElement>('path.aw-sp-thread')]
    expect(paths).toHaveLength(3)
    const lanes = paths.map((p) => Number(p.dataset.lane)).sort((x, y) => x - y)
    expect(new Set(lanes).size).toBe(3)
    expect(lanes[1]! - lanes[0]!).toBeGreaterThanOrEqual(8)
    expect(lanes[2]! - lanes[1]!).toBeGreaterThanOrEqual(8)
    for (const p of paths) expect(p.getAttribute('d')).toContain(`V`)
  })

  it('ac-colour: each thread carries its prerequisite state class and the legend lists the states present', () => {
    const { container, getByLabelText } = show([
      task('a', 'approved'),
      task('b', 'pending'),
      task('c', 'in_progress'),
      task('d', 'rejected'),
      task('e', 'pending', ['a', 'b', 'c', 'd']),
    ])
    const state = (from: string) => container.querySelector<SVGPathElement>(`path[data-from="${from}"]`)!
    expect(state('a').dataset.state).toBe('done')
    expect(state('b').dataset.state).toBe('waiting')
    expect(state('c').dataset.state).toBe('in-progress')
    expect(state('d').dataset.state).toBe('rejected')
    expect(state('c').getAttribute('class')).toContain('dependency-edge-live')
    expect(state('d').getAttribute('class')).toContain('dependency-edge-rejected')
    const legend = within(getByLabelText('Thread colours'))
    for (const label of ['Done', 'In progress', 'Waiting', 'Rejected']) expect(legend.getByText(label)).toBeTruthy()
  })

  it('legend omits states no thread has', () => {
    const { getByLabelText, queryByText } = show([task('a', 'approved'), task('b', 'pending', ['a'])])
    expect(within(getByLabelText('Thread colours')).getByText('Done')).toBeTruthy()
    expect(queryByText('Rejected')).toBeNull()
  })

  it('ac-hover: hover and focus light the chain and dim the rest; leaving restores', () => {
    const { container } = show([task('a', 'approved'), task('b', 'approved', ['a']), task('c', 'pending', ['b']), task('d', 'pending')])
    const row = (k: string) => container.querySelector<HTMLElement>(`[data-task="${k}"]`)!
    const lit = () => ['a', 'b', 'c', 'd'].map((k) => row(k).dataset.lit)
    expect(lit()).toEqual([undefined, undefined, undefined, undefined])
    fireEvent.mouseEnter(row('b'))
    expect(lit()).toEqual(['on', 'on', 'on', 'dim'])
    expect([...container.querySelectorAll<SVGPathElement>('path.aw-sp-thread')].map((p) => p.dataset.lit)).toEqual(['on', 'on'])
    fireEvent.mouseLeave(row('b'))
    expect(lit()).toEqual([undefined, undefined, undefined, undefined])
    fireEvent.focus(row('b'))
    expect(lit()).toEqual(['on', 'on', 'on', 'dim'])
    fireEvent.blur(row('b'))
    expect(lit()).toEqual([undefined, undefined, undefined, undefined])
  })
})
