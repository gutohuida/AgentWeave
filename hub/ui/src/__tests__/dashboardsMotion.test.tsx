import * as React from 'react'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DashboardRun, PanelRun } from '@/api/dashboards'
import { DashboardsView } from '@/components/dashboards/DashboardsView'

// The motion is CSS (styles/dashboards.css, not loaded under jsdom); what these pin is the markup
// and state it hangs off: the real figure in the DOM, the presence marks, the dimming class, the
// tooltip, the skeleton, and the switch-offs under reduced motion.

const panel = (p: Partial<PanelRun> & Pick<PanelRun, 'id' | 'title' | 'kind' | 'columns' | 'rows'>): PanelRun => ({
  query: 'select 1', row_count: p.rows.length, truncated: false, elapsed_ms: 1, error: null, warning: null, ...p,
})
const run = (panels: PanelRun[]): DashboardRun => ({
  id: 'd1', name: 'D', description: '', author: 'Architect', updated_at: null, fetched_at: '2026-11-14T10:00:00Z', panels,
})
const summary = { id: 'd1', name: 'Spend', description: '', author: 'Architect', created_at: null, updated_at: '2026-11-12T10:00:00Z', panel_count: 4 }

const NUMBER = panel({ id: 'n', title: 'Cost', kind: 'number', columns: ['cost'], rows: [[1234.5]] })
const BAR = panel({ id: 'b', title: 'Per spec', kind: 'bar', columns: ['spec', 'cost'], rows: [['a', 1], ['b', 2], ['c', 3], ['d', 4]] })
const STACK = panel({ id: 's', title: 'Mix', kind: 'stacked_bar', columns: ['m', 'ok', 'bad'], rows: [['x', 1, 2], ['y', 3, 1]] })
const LINE = panel({
  id: 'l', title: 'Runs', kind: 'line', columns: ['day', 'runs'],
  rows: [['d1', 1], ['d2', 3], ['d3', 2], ['d4', 5], ['d5', 4], ['d6', 6]],
})

type ViewProps = React.ComponentProps<typeof DashboardsView>
const view = (panels: PanelRun[] | null, extra: Partial<ViewProps> = {}) => (
  <DashboardsView dashboards={[summary]} selectedId="d1" run={panels ? run(panels) : null} refreshing={false}
    onSelect={() => {}} onRefresh={() => {}} onDelete={() => {}} {...extra} />
)

function reduceMotion(on: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: on && query.includes('prefers-reduced-motion'),
    media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

// Vite hands a stylesheet over empty under `css: false`, and the app's tsconfig has no node types,
// so the file is read through a module name the type-checker cannot see.
const readSheet = async (): Promise<string> => {
  const fsName = 'node:fs'
  const fs = (await import(/* @vite-ignore */ fsName)) as { readFileSync: (p: string, enc: string) => string }
  const cwd = (globalThis as unknown as { process: { cwd: () => string } }).process.cwd()
  return fs.readFileSync(`${cwd}/src/styles/dashboards.css`, 'utf8')
}

beforeEach(() => reduceMotion(false))
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('count-up (ac-draw-in)', () => {
  it('holds the real figure in the number element while it counts, and the count is aria-hidden', () => {
    let now = 0
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    const raf: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => raf.push(cb))
    vi.stubGlobal('cancelAnimationFrame', () => {})
    render(view([NUMBER]))
    const el = screen.getByTestId('dashboard-number')
    // Read at every step of the count: always the final figure.
    for (const t of [0, 100, 300, 600, 899]) {
      now = t
      act(() => raf.splice(0).forEach((cb) => cb(now)))
      expect(el.textContent).toBe('1,234.5')
      if (t === 100) {
        // Mid-count the drawn figure is not the final one, and it is hidden from readers.
        const overlay = screen.getByTestId('chart-number').querySelector('[aria-hidden=true]')
        expect(overlay).toBeTruthy()
        expect(overlay?.textContent).not.toBe('1,234.5')
      }
    }
    now = 1000
    act(() => raf.splice(0).forEach((cb) => cb(now)))
    expect(screen.getByTestId('chart-number').querySelector('[aria-hidden=true]')).toBeNull()
    expect(el.textContent).toBe('1,234.5')
  })

  it('draws bars, stacked bars and line marks with their final geometry in the DOM at once', () => {
    render(view([NUMBER, BAR, STACK, LINE]))
    const bars = screen.getByTestId('chart-bar').querySelectorAll('svg.aw-dash-bar')
    expect(bars).toHaveLength(4)
    expect((bars[3] as SVGElement).style.width).toBe('100%')
    expect((bars[1] as SVGElement).style.width).toBe('50%')
    expect(screen.getByTestId('chart-stacked-bar').querySelectorAll('svg.aw-dash-bar')).toHaveLength(2)
    expect(screen.getByTestId('chart-line').querySelectorAll('path.aw-dash-line')).toHaveLength(1)
    expect(screen.getByTestId('chart-line').querySelectorAll('circle.aw-dash-dot')).toHaveLength(6)
  })

  it('staggers the panels: each carries its position as --i', () => {
    render(view([NUMBER, BAR, STACK, LINE]))
    const idx = screen.getAllByTestId('dashboard-panel').map((p) => (p as HTMLElement).style.getPropertyValue('--i'))
    expect(idx).toEqual(['0', '1', '2', '3'])
  })
})

describe('values move (ac-values-move)', () => {
  it('keeps the same bar elements and changes their widths when the data changes; dims while refreshing', () => {
    const { rerender } = render(view([BAR]))
    const before = [...screen.getByTestId('chart-bar').querySelectorAll('svg.aw-dash-bar')] as SVGElement[]
    expect(before.map((b) => b.style.width)).toEqual(['25%', '50%', '75%', '100%'])
    expect(document.querySelector('.aw-dash-panels')?.classList.contains('is-refreshing')).toBe(false)

    rerender(view([BAR], { refreshing: true }))
    expect(document.querySelector('.aw-dash-panels')?.classList.contains('is-refreshing')).toBe(true)

    const next = panel({ ...BAR, rows: [['a', 4], ['b', 2], ['c', 3], ['d', 1]] })
    rerender(view([next], { refreshing: false }))
    const after = [...screen.getByTestId('chart-bar').querySelectorAll('svg.aw-dash-bar')] as SVGElement[]
    expect(after).toHaveLength(4)
    after.forEach((el, i) => expect(el).toBe(before[i]))
    expect(after.map((b) => b.style.width)).toEqual(['100%', '50%', '75%', '25%'])
    expect(document.querySelector('.aw-dash-panels')?.classList.contains('is-refreshing')).toBe(false)
  })

  it('does not remount a panel when its values change', () => {
    const { rerender } = render(view([NUMBER, LINE]))
    const section = screen.getAllByTestId('dashboard-panel')[1]
    rerender(view([NUMBER, panel({ ...LINE, rows: [['d1', 6], ['d2', 1]] })]))
    expect(screen.getAllByTestId('dashboard-panel')[1]).toBe(section)
  })
})

describe('presence (ac-edit-visible)', () => {
  const states = () =>
    screen.queryAllByTestId(/^dashboard-panel(-leaving)?$/).map((s) => [s.getAttribute('data-panel-id'), s.getAttribute('data-state')])
  const added = panel({ id: 'x', title: 'Added', kind: 'number', columns: ['c'], rows: [[3]] })

  it('marks nothing new on first open', () => {
    render(view([NUMBER, BAR, STACK, LINE]))
    expect(states().every(([, s]) => s === 'shown')).toBe(true)
    expect(document.querySelector('.is-new')).toBeNull()
  })

  it('marks an added panel new, keeps a removed one leaving, then drops it', () => {
    vi.useFakeTimers()
    const { rerender } = render(view([NUMBER, BAR, STACK, LINE]))
    rerender(view([NUMBER, BAR, STACK, added]))
    const leaving = screen.getByTestId('dashboard-panel-leaving')
    expect(leaving.getAttribute('data-panel-id')).toBe('l')
    expect(leaving.classList.contains('is-leaving')).toBe(true)
    const fresh = screen.getAllByTestId('dashboard-panel').find((p) => p.getAttribute('data-panel-id') === 'x')
    expect(fresh?.getAttribute('data-state')).toBe('new')
    expect(fresh?.classList.contains('is-new')).toBe(true)
    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(screen.queryByTestId('dashboard-panel-leaving')).toBeNull()
    expect(screen.getAllByTestId('dashboard-panel')).toHaveLength(4)
  })

  it('keeps the leaving panel where it was', () => {
    const { rerender } = render(view([NUMBER, BAR, STACK, LINE]))
    rerender(view([NUMBER, STACK, LINE]))
    expect(states().map(([id]) => id)).toEqual(['n', 'b', 's', 'l'])
    expect(states()[1][1]).toBe('leaving')
  })

  it('on reopening the dashboard nothing is new', () => {
    const { rerender } = render(view([NUMBER, BAR]))
    rerender(view([NUMBER, BAR, added]))
    expect(document.querySelectorAll('.is-new')).toHaveLength(1)
    // Back to the list, then open it again.
    rerender(view(null, { selectedId: null }))
    rerender(view([NUMBER, BAR, added]))
    expect(document.querySelector('.is-new')).toBeNull()
    expect(states().every(([, s]) => s === 'shown')).toBe(true)
  })
})

describe('tooltip and dimming (ac-tooltip)', () => {
  it('hovering a bar, then a line point, shows label, series and value, and leaving removes it', () => {
    render(view([BAR, LINE]))
    const barMarks = screen.getByTestId('chart-bar').querySelectorAll('rect.aw-dash-mark')
    expect(barMarks).toHaveLength(4)
    fireEvent.mouseMove(barMarks[1], { clientX: 10, clientY: 10 })
    const tip = within(screen.getByTestId('chart-bar')).getByTestId('dashboard-tooltip')
    expect(tip.textContent).toContain('b')
    expect(tip.textContent).toContain('cost')
    expect(tip.textContent).toContain('2')
    fireEvent.mouseLeave(barMarks[1])
    expect(screen.queryByTestId('dashboard-tooltip')).toBeNull()

    const dots = screen.getByTestId('chart-line').querySelectorAll('circle.aw-dash-mark')
    expect(dots).toHaveLength(6)
    fireEvent.mouseMove(dots[3], { clientX: 20, clientY: 20 })
    const tip2 = within(screen.getByTestId('chart-line')).getByTestId('dashboard-tooltip')
    expect(tip2.textContent).toContain('d4')
    expect(tip2.textContent).toContain('runs')
    expect(tip2.textContent).toContain('5')
    expect(screen.getAllByRole('tooltip')).toHaveLength(1)
    fireEvent.mouseLeave(dots[3])
    expect(screen.queryByTestId('dashboard-tooltip')).toBeNull()
  })

  it('names the segment of a stacked bar', () => {
    render(view([STACK]))
    const marks = screen.getByTestId('chart-stacked-bar').querySelectorAll('rect.aw-dash-mark')
    fireEvent.mouseMove(marks[1], { clientX: 5, clientY: 5 })
    const tip = screen.getByTestId('dashboard-tooltip')
    expect(tip.textContent).toContain('x')
    expect(tip.textContent).toContain('bad')
    expect(tip.textContent).toContain('2')
  })

  it('marks every mark of a chart as dimmable, so the stylesheet can dim the others', () => {
    render(view([BAR, LINE]))
    const chart = screen.getByTestId('chart-bar')
    expect(chart.classList.contains('aw-dash-chart')).toBe(true)
    expect(chart.querySelectorAll('rect').length).toBe(chart.querySelectorAll('rect.aw-dash-mark').length)
    const line = screen.getByTestId('chart-line')
    expect(line.querySelectorAll('circle').length).toBe(line.querySelectorAll('circle.aw-dash-mark').length)
  })
})

describe('placeholders (ac-skeleton)', () => {
  it('shows placeholders while the run is being fetched, and none once it arrives', () => {
    const { rerender } = render(view(null))
    expect(screen.getByTestId('dashboard-placeholders')).toBeTruthy()
    expect(document.querySelectorAll('.aw-dash-placeholder').length).toBeGreaterThan(0)
    // The brand's thread, once, not a grey shimmer per bar.
    expect(screen.getByTestId('dashboard-placeholders').querySelectorAll('.aw-loading-thread')).toHaveLength(1)
    expect(screen.queryAllByTestId('dashboard-panel')).toHaveLength(0)
    rerender(view([NUMBER, BAR]))
    expect(screen.queryByTestId('dashboard-placeholders')).toBeNull()
    expect(document.querySelector('.aw-dash-placeholder')).toBeNull()
    expect(screen.getAllByTestId('dashboard-panel')).toHaveLength(2)
  })

  it('shows no placeholders when the run failed', () => {
    render(view(null, { error: 'boom' }))
    expect(screen.queryByTestId('dashboard-placeholders')).toBeNull()
  })
})

describe('reduced motion (ac-reduced-motion)', () => {
  it('shows the final figure at once, with no count overlay, and the tooltip still works', () => {
    reduceMotion(true)
    vi.stubGlobal('requestAnimationFrame', () => {
      throw new Error('nothing may animate')
    })
    render(view([NUMBER, BAR]))
    expect(screen.getByTestId('dashboard-number').textContent).toBe('1,234.5')
    expect(screen.getByTestId('chart-number').querySelector('[aria-hidden=true]')).toBeNull()
    const mark = screen.getByTestId('chart-bar').querySelector('rect.aw-dash-mark') as Element
    fireEvent.mouseMove(mark, { clientX: 1, clientY: 1 })
    expect(screen.getByTestId('dashboard-tooltip').textContent).toContain('cost')
    fireEvent.mouseLeave(mark)
    expect(screen.queryByTestId('dashboard-tooltip')).toBeNull()
  })

  it('the stylesheet switches every dashboards animation and transition off, and leaves dimming on', async () => {
    const css = await readSheet()
    const block = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(block).toContain('animation: none !important')
    expect(block).toContain('transition: none !important')
    const animated = ['.aw-dash-panel', '.aw-dash-panel.is-new', '.aw-dash-panel.is-leaving', '.aw-dash-bar',
      '.aw-dash-bar rect', '.aw-dash-line', '.aw-dash-dot', '.aw-dash-mark', '.aw-dash-tip', '.aw-dash-chart']
    for (const sel of animated) expect(block).toContain(sel)
    // The dimming rules sit outside the block, so they still apply.
    expect(block).not.toContain('opacity: 0.35')
    expect(css).toContain('opacity: 0.35')
  })
})
