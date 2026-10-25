import * as React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThreadLoom } from '@/components/thread/loom/ThreadLoom'
import { Loom } from '@/components/thread/loom/Loom'
import { weave } from '@/components/thread/loom/geometry'
import { agentColorVars } from '@/lib/agentColors'
import type { ThreadKnot } from '@/api/thread'
import recorded from '../../mock/thread-chapters-fixture.json'

/** This repository's thread with its 17 chapters, as the approved mock renders it: every level in
 *  the order `GET /thread` returned it. */
const levels = (recorded as unknown as { levels: Record<string, { knots: ThreadKnot[] }> }).levels
const surface = levels.surface!.knots
const inner: Record<string, ThreadKnot[]> = Object.fromEntries(
  Object.entries(levels)
    .filter(([k]) => k !== 'surface')
    .map(([k, v]) => [k, v.knots]),
)
const now = new Date('2026-10-24T23:00:00Z')
const SURFACE_SIZE = { gap: 196, pad: 120, thickness: 312, swing: 34, swell: 26 }

function knot(key: string, start: string, end = start, extra: Partial<ThreadKnot> = {}): ThreadKnot {
  return {
    key, address: key, kind: 'run', fold_of: null, word: 'Run', title: key, start, end,
    actors: [], child_count: 0, descendant_count: 0, link: null, ...extra,
  }
}

function Harness({ start, knots = surface }: { start: string[]; knots?: ThreadKnot[] }) {
  const [path, setPath] = React.useState(start)
  return (
    <ThreadLoom
      surface={knots}
      levels={inner}
      path={path}
      onPath={setPath}
      now={now}
      actorColor={(name) => agentColorVars(name === 'Architect' ? 2 : null)}
      onOpenLink={() => undefined}
    />
  )
}

const position = () => {
  const kind = document.querySelector('.aw-loom-detail-kind')
  const of = kind?.querySelector('.aw-loom-detail-of')?.textContent ?? ''
  return `${(kind?.textContent ?? '').slice(0, -of.length || undefined)} ${of}`.trim()
}
const fact = (label: string) =>
  Array.from(document.querySelectorAll('.aw-loom-fact')).find((f) => f.querySelector('dt')?.textContent === label)?.querySelector('dd')
const innerBeads = () => Array.from(document.querySelectorAll<HTMLElement>('.aw-loom-inner [data-slot="loom-bead"]'))

const mender = surface.find((k) => k.title === 'The mender and the stall alarms')!

describe('ThreadLoom against the approved recording', () => {
  it('states the chapters, their span and the newer knots not in one', () => {
    render(<Harness start={[mender.key]} />)
    expect(document.querySelector('.aw-loom-bar-count')?.textContent).toBe('17 chapters')
    expect(document.querySelector('.aw-loom-bar-span')?.textContent).toBe('Mar 7 to Oct 24 · 1 newer knot not in a chapter yet')
  })

  it('states the number of surface knots when there are no chapters', () => {
    const knots = [knot('run:a', '2026-10-01T09:00:00Z'), knot('run:b', '2026-10-02T09:00:00Z')]
    render(<Harness start={['run:a']} knots={knots} />)
    expect(document.querySelector('.aw-loom-bar-count')?.textContent).toBe('2 knots')
  })

  it('describes the selected chapter in the panel', () => {
    render(<Harness start={[mender.key]} />)
    expect(position()).toBe('Chapter 17 of 17')
    expect(screen.getByRole('heading', { name: 'The mender and the stall alarms' })).toBeTruthy()
    expect(document.querySelector('.aw-loom-detail-summary')?.textContent).toBe(mender.summary)
    expect(fact('When')?.textContent).toBe('Oct 24 · 1 day')
    expect(fact('Holds')?.textContent).toBe('47 knots · 97 all the way down')
    const chips = Array.from(document.querySelectorAll<HTMLElement>('.aw-loom-actor'))
    expect(chips.map((c) => c.textContent)).toEqual(expect.arrayContaining(['manager', 'Operator', 'mender', 'Architect']))
    expect(chips.find((c) => c.textContent === 'Architect')?.style.getPropertyValue('--actor')).toBe('var(--agent-3)')
    const kinds = Array.from(document.querySelectorAll('.aw-loom-kindchip')).map((c) => c.textContent)
    expect(kinds).toEqual(['45 conversations', '1 vault entry', '1 document'])
  })

  it('descends to the third knot on the panel thread, and the trail selects the chapter again', () => {
    render(<Harness start={[mender.key]} />)
    expect(innerBeads()).toHaveLength(47)
    fireEvent.click(innerBeads()[2]!)
    // Counted among the knots of its kind beside it: this chapter holds 45 conversations of its 47.
    expect(position()).toBe('Conversation 3 of 45')
    const crumbs = Array.from(document.querySelectorAll<HTMLElement>('[data-slot="loom-crumb"]'))
    expect(crumbs.map((c) => c.textContent)).toEqual(['The mender and the stall alarms'])
    fireEvent.click(crumbs[0]!)
    expect(position()).toBe('Chapter 17 of 17')
  })

  it('a chapter of 47 conversations: the third reads Conversation 3 of 47', () => {
    const ch = knot('chapter:c47', '2026-10-24T00:00:00Z', '2026-10-24T23:59:59Z', {
      kind: 'chapter', word: 'Chapter', title: 'Forty-seven', child_count: 47, descendant_count: 47,
    })
    inner[ch.key] = Array.from({ length: 47 }, (_, i) =>
      knot(`conversation:${i}`, `2026-10-24T${String(i % 24).padStart(2, '0')}:00:00Z`, undefined, { kind: 'conversation', word: 'Conversation' }),
    )
    render(<Harness start={[ch.key]} knots={[ch]} />)
    fireEvent.click(innerBeads()[2]!)
    expect(position()).toBe('Conversation 3 of 47')
    delete inner[ch.key]
  })

  it('shows a knot that holds nothing on the thread beside it, marked as selected', () => {
    const leaf = inner[mender.key]!.find((k) => k.child_count === 0)!
    render(<Harness start={[mender.key, leaf.key]} />)
    expect(document.querySelector('.aw-loom-inner-head')?.textContent).toContain('Beside it on the thread')
    expect(innerBeads()).toHaveLength(47)
    expect(innerBeads().filter((b) => b.getAttribute('aria-selected') === 'true').map((b) => b.dataset.key)).toEqual([leaf.key])
  })

  it('a surface knot that holds nothing shows the surface beside it', () => {
    const knots = [knot('run:a', '2026-10-01T09:00:00Z'), knot('run:b', '2026-10-02T09:00:00Z')]
    render(<Harness start={['run:b']} knots={knots} />)
    expect(innerBeads().map((b) => [b.dataset.key, b.getAttribute('aria-selected')])).toEqual([
      ['run:a', 'false'],
      ['run:b', 'true'],
    ])
  })
})

/** Node's environment: changing TZ there moves every Date read after it to that zone. */
const env = (globalThis as unknown as { process: { env: Record<string, string | undefined> } }).process.env

describe('the loom thread', () => {
  const tz = env.TZ
  afterEach(() => {
    env.TZ = tz
  })

  it('reads a chapter as the calendar days it was written for, east and west of UTC', () => {
    const one = knot('chapter:x', '2026-10-24T00:00:00Z', '2026-10-24T23:59:59Z', {
      kind: 'chapter', word: 'Chapter', title: 'One day', child_count: 1, descendant_count: 1,
    })
    for (const zone of ['Europe/Berlin', 'America/New_York']) {
      env.TZ = zone
      // The zone is in force: the start of that day, read as an instant, falls on another day east or west.
      expect(new Date('2026-10-24T00:00:00Z').getHours()).toBe(zone === 'Europe/Berlin' ? 2 : 20)
      const { unmount } = render(<Harness start={[one.key]} knots={[one]} />)
      expect(document.querySelector('.aw-loom-label-when')?.textContent).toBe('Oct 24')
      expect(fact('When')?.textContent).toBe('Oct 24 · 1 day')
      unmount()
    }
  })

  it('spaces neighbouring knots evenly whatever lies between them in time', () => {
    const knots = [
      knot('a', '2026-03-01T00:00:00Z'),
      knot('b', '2026-05-01T00:00:00Z'),
      knot('c', '2026-05-02T00:00:00Z'),
      knot('d', '2026-05-03T00:00:00Z'),
    ]
    const g = weave(knots, SURFACE_SIZE)
    const steps = g.beads.slice(1).map((b, i) => b.along - g.beads[i]!.along)
    expect(steps).toEqual([196, 196, 196])
  })

  it('names a long silence and leaves a short one unnamed', () => {
    const knots = [
      knot('a', '2026-03-01T00:00:00Z', '2026-03-01T10:00:00Z'),
      knot('b', '2026-04-30T10:00:00Z'),
      knot('c', '2026-05-01T10:00:00Z'),
    ]
    const { container } = render(<Loom knots={knots} selected={null} onSelect={() => undefined} now={now} scale="surface" label="t" />)
    expect(Array.from(container.querySelectorAll('.aw-loom-gap')).map((g) => g.textContent)).toEqual(['2 months later'])
  })

  it('sits five knots alternately above and below the middle, each label beyond its knot, on a madder line', () => {
    const knots = ['a', 'b', 'c', 'd', 'e'].map((k, i) => knot(k, `2026-05-0${i + 1}T00:00:00Z`))
    const g = weave(knots, SURFACE_SIZE)
    const mid = SURFACE_SIZE.thickness / 2
    expect(g.beads.map((b) => (b.across < mid ? 'above' : 'below'))).toEqual(['above', 'below', 'above', 'below', 'above'])
    const { container } = render(<Loom knots={knots} selected={null} onSelect={() => undefined} now={now} scale="surface" label="t" />)
    const sides = Array.from(container.querySelectorAll<HTMLElement>('.aw-loom-label')).map((l) => l.dataset.side)
    expect(sides).toEqual(['before', 'after', 'before', 'after', 'before'])
    expect(container.querySelector('.aw-loom-line')).toBeTruthy()
    expect(container.querySelector('.aw-loom-strand')).toBeNull()
  })

  it('keeps every knot on its side when an older page of odd length joins on the left', () => {
    const later = ['c', 'd', 'e'].map((k, i) => knot(k, `2026-05-0${i + 3}T00:00:00Z`))
    const older = [knot('b', '2026-05-02T00:00:00Z'), ...later]
    const sides = (c: HTMLElement) =>
      Object.fromEntries(Array.from(c.querySelectorAll<HTMLElement>('.aw-loom-label')).map((l, i) => [i, l.dataset.side]))
    const { container, rerender } = render(<Loom knots={later} selected="d" onSelect={() => undefined} now={now} scale="surface" label="t" />)
    const before = sides(container)
    rerender(<Loom knots={older} selected="d" onSelect={() => undefined} now={now} scale="surface" label="t" />)
    const after = sides(container)
    expect([after[1], after[2], after[3]]).toEqual([before[0], before[1], before[2]])
  })

  it('a wheel turned over the thread scrolls it sideways', () => {
    const knots = ['a', 'b', 'c'].map((k, i) => knot(k, `2026-05-0${i + 1}T00:00:00Z`))
    const onSelect = vi.fn()
    const { container } = render(<Loom knots={knots} selected="a" onSelect={onSelect} now={now} scale="surface" label="t" />)
    const scroller = container.querySelector<HTMLElement>('.aw-loom')!
    scroller.scrollLeft = 0
    fireEvent.wheel(scroller, { deltaY: 120, deltaX: 0 })
    expect(scroller.scrollLeft).toBe(120)
    expect(onSelect).not.toHaveBeenCalled()
  })
})
