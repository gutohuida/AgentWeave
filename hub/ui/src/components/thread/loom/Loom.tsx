import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { KNOT_GLYPH } from '@/lib/threadKnots'
import { formatDay } from '@/lib/format'
import type { ThreadKnot } from '@/api/thread'
import { weave, type LoomOptions } from './geometry'
import '@/styles/thread-loom.css'

/** How a knot came to be chosen: the keyboard moves focus with it, a pointer does not need to. */
export type LoomHow = 'pointer' | 'key'

interface LoomProps {
  knots: readonly ThreadKnot[]
  selected: string | null
  onSelect: (key: string, how: LoomHow) => void
  now: Date
  /** `surface` is the project's whole thread; `inner` is the smaller one a knot opens into. */
  scale: 'surface' | 'inner'
  /** Changes whenever the thread should draw itself in again (a new level, or a replay). */
  drawKey?: string | number
  /** Changes whenever the selected knot should be brought into view again. */
  reveal?: number
  /** Number the beads (chapters read as a book's chapters). */
  numbered?: boolean
  label: string
  /** More knots lie beyond the loaded ones on that side. */
  hasBefore?: boolean
  hasAfter?: boolean
  /** The reader came within one screen width of an end that has more beyond it. */
  onMore?: (side: 'before' | 'after') => void
  /** Enter on a bead. */
  onEnter?: (key: string) => void
}

const SIZES: Record<'surface' | 'inner', Omit<LoomOptions, 'phase'>> = {
  surface: { gap: 196, pad: 120, thickness: 312, swing: 34, swell: 26 },
  inner: { gap: 150, pad: 90, thickness: 196, swing: 20, swell: 14 },
}

function span(knot: ThreadKnot, now: Date): string {
  // A chapter spans whole days as the manager wrote them; read them as calendar days.
  const day = (v: string) => (knot.kind === 'chapter' ? v.slice(0, 10) : v)
  const a = formatDay(day(knot.start), now)
  const b = formatDay(day(knot.end), now)
  return a === b ? a : `${a} – ${b}`
}

/** A project's thread laid as a loom lays one: a wave that crests and troughs at each knot, drawn
 *  in from the beginning, with a glint that passes along it like a shuttle. Presentational: the
 *  container owns what is selected and what is loaded. Arrow keys along the thread move the
 *  selection; nearing an end that has more beyond it asks for the next page. */
export function Loom({
  knots,
  selected,
  onSelect,
  now,
  scale,
  drawKey,
  reveal = 0,
  numbered,
  label,
  hasBefore = false,
  hasAfter = false,
  onMore,
  onEnter,
}: LoomProps) {
  // Which side the first knot swings to. An older page joined on the left shifts every index by its
  // length; the phase shifts with it, so no knot already drawn changes side.
  const phased = React.useRef<{ knots: readonly ThreadKnot[]; phase: number }>({ knots, phase: 0 })
  const phase = React.useMemo(() => {
    const prev = phased.current
    if (prev.knots !== knots) {
      const at = prev.knots[0] ? knots.findIndex((k) => k.key === prev.knots[0]!.key) : -1
      phased.current = { knots, phase: at < 0 ? 0 : (prev.phase + at) % 2 }
    }
    return phased.current.phase
  }, [knots])
  const g = React.useMemo(() => weave(knots, { ...SIZES[scale], phase }), [knots, scale, phase])
  const scroller = React.useRef<HTMLDivElement>(null)
  const beads = React.useRef(new Map<string, HTMLButtonElement>())
  const draw = g.beads.length > 0 ? Math.min(1800, 500 + g.beads.length * 70) : 0

  const nearEnds = React.useCallback(() => {
    const el = scroller.current
    if (!el || !onMore || el.clientWidth === 0) return
    if (hasBefore && el.scrollLeft < el.clientWidth) onMore('before')
    if (hasAfter && el.scrollWidth - el.scrollLeft - el.clientWidth < el.clientWidth) onMore('after')
  }, [onMore, hasBefore, hasAfter])

  // Knots joined on the left push the ones already drawn to the right: scroll by as much, before the
  // browser paints, so what the reader was looking at stays where it was on screen. Then bring the
  // selected knot to the middle of the view, once per selection, so a page arriving does not move
  // it: gliding when the reader chose it, simply there on a thread just drawn. Only then is it known
  // whether the view is near an end.
  const laid = React.useRef<{ key: string; along: number } | null>(null)
  const brought = React.useRef<string | null>(null)
  const drawn = React.useRef<string | number | null>(null)
  React.useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    const was = laid.current
    if (was) {
      const moved = g.beads.find((b) => b.key === was.key)
      if (moved && moved.along !== was.along) el.scrollLeft += moved.along - was.along
    }
    const first = g.beads[0]
    laid.current = first ? { key: first.key, along: first.along } : null

    const bead = g.beads.find((b) => b.key === selected)
    const ask = `${selected}|${reveal}|${drawKey ?? ''}`
    if (bead && brought.current !== ask) {
      brought.current = ask
      const fresh = drawn.current !== (drawKey ?? '')
      drawn.current = drawKey ?? ''
      const left = bead.along - el.clientWidth / 2
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
      if (reduce || fresh || !el.scrollTo) el.scrollLeft = left
      else el.scrollTo({ left, behavior: 'smooth' })
    }
    nearEnds()
  }, [g, nearEnds, selected, reveal, drawKey])

  // A mouse wheel scrolls the thread sideways; a press-and-drag pulls it along.
  const onWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) return
    event.currentTarget.scrollLeft += event.deltaY
  }
  const drag = React.useRef<{ start: number; scroll: number; moved: boolean } | null>(null)
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !scroller.current) return
    drag.current = { start: event.clientX, scroll: scroller.current.scrollLeft, moved: false }
  }
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d || !scroller.current) return
    const delta = event.clientX - d.start
    if (Math.abs(delta) > 4) d.moved = true
    if (!d.moved) return
    scroller.current.dataset.dragging = 'true'
    scroller.current.scrollLeft = d.scroll - delta
  }
  const endDrag = () => {
    if (scroller.current) delete scroller.current.dataset.dragging
    window.setTimeout(() => (drag.current = null), 0)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    const from = (event.target as HTMLElement).dataset?.key ?? selected
    if (event.key === 'Enter') {
      if (!onEnter || !from) return
      event.preventDefault()
      onEnter(from)
      return
    }
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight' && event.key !== 'Home' && event.key !== 'End') return
    const at = g.beads.findIndex((b) => b.key === from)
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? g.beads.length - 1
          : Math.max(0, Math.min(g.beads.length - 1, at + (event.key === 'ArrowRight' ? 1 : -1)))
    const bead = g.beads[next]
    if (!bead) return
    event.preventDefault()
    onSelect(bead.key, 'key')
    beads.current.get(bead.key)?.focus({ preventScroll: true })
  }

  const chosen = g.beads.find((b) => b.key === selected)
  const box = { width: g.length, height: g.thickness }
  const pos = (along: number, across: number): React.CSSProperties => ({ left: along, top: across })

  return (
    <div
      ref={scroller}
      className="aw-loom"
      data-scale={scale}
      role="listbox"
      aria-label={label}
      aria-orientation="horizontal"
      onWheel={onWheel}
      onScroll={nearEnds}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerLeave={endDrag}
      onKeyDown={onKeyDown}
      style={{ '--draw': `${draw}ms` } as React.CSSProperties}
    >
      <div className="aw-loom-cloth" style={box} key={`${drawKey ?? ''}`}>
        <svg className="aw-loom-svg aw-loom-reveal" width={box.width} height={box.height} aria-hidden="true">
          <g>
            <path d={g.centre} className="aw-loom-halo" />
            <path d={g.centre} className="aw-loom-line" />
          </g>
          <path d={g.centre} className="aw-loom-glint" pathLength={1000} />
          {chosen ? (
            <circle
              key={chosen.key}
              className="aw-loom-loop"
              cx={chosen.along}
              cy={chosen.across}
              r={scale === 'surface' ? 21 : 15}
              pathLength={1}
            />
          ) : null}
        </svg>

        {g.gaps.map((gap) => (
          <span key={gap.along} className="aw-loom-gap" style={pos(gap.along, gap.across)}>
            {gap.label}
          </span>
        ))}

        {g.beads.map((b) => {
          const knot = knots[b.index]!
          const isSelected = b.key === selected
          const delay = draw * (b.along / g.length)
          return (
            <React.Fragment key={b.key}>
              <button
                type="button"
                data-slot="loom-bead"
                data-key={b.key}
                role="option"
                aria-selected={isSelected}
                tabIndex={isSelected || (!chosen && b.index === 0) ? 0 : -1}
                ref={(el) => {
                  if (el) beads.current.set(b.key, el)
                  else beads.current.delete(b.key)
                }}
                className="aw-loom-bead"
                data-kind={knot.kind}
                data-selected={isSelected ? 'true' : undefined}
                data-holds={knot.child_count > 0 ? 'true' : undefined}
                style={{ ...pos(b.along, b.across), '--delay': `${delay}ms`, '--weight': b.weight } as React.CSSProperties}
                onClick={() => {
                  if (!drag.current?.moved) onSelect(b.key, 'pointer')
                }}
                title={knot.title}
                aria-label={`${knot.word}: ${knot.title}, ${span(knot, now)}`}
              >
                {numbered && knot.kind === 'chapter' ? (
                  <span className="aw-loom-bead-n">{b.index + 1}</span>
                ) : (
                  <Icon name={KNOT_GLYPH[knot.kind]} size={scale === 'surface' ? 13 : 11} />
                )}
              </button>
              <span
                className="aw-loom-label"
                data-side={b.side === -1 ? 'before' : 'after'}
                data-selected={isSelected ? 'true' : undefined}
                style={{ ...pos(b.along, b.across), '--delay': `${delay + 90}ms` } as React.CSSProperties}
                aria-hidden="true"
              >
                <span className="aw-loom-label-when">{span(knot, now)}</span>
                <span className="aw-loom-label-title">{knot.title}</span>
              </span>
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
