import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { KNOT_GLYPH } from '@/lib/threadKnots'
import { formatDay } from '@/lib/format'
import type { ThreadKnot } from '@/api/thread'
import { weave, type LoomOptions } from './geometry'
import '@/styles/thread-loom.css'

export type LoomStyle = 'wave' | 'rope'
export type LoomOrientation = 'horizontal' | 'vertical'

interface LoomProps {
  knots: readonly ThreadKnot[]
  selected: string | null
  onSelect: (key: string) => void
  now: Date
  orientation: LoomOrientation
  threadStyle: LoomStyle
  /** `surface` is the project's whole thread; `inner` is the smaller one a knot opens into. */
  scale: 'surface' | 'inner'
  /** Changes whenever the thread should draw itself in again (a new level, or a replay). */
  drawKey?: string | number
  /** Number the beads (chapters read as a book's chapters). */
  numbered?: boolean
  label: string
}

const SIZES: Record<'surface' | 'inner', Record<LoomOrientation, Omit<LoomOptions, 'twisted' | 'vertical'>>> = {
  surface: {
    horizontal: { gap: 196, pad: 120, thickness: 312, swing: 34, swell: 26 },
    vertical: { gap: 132, pad: 72, thickness: 548, swing: 30, swell: 22 },
  },
  inner: {
    horizontal: { gap: 150, pad: 90, thickness: 196, swing: 20, swell: 14 },
    vertical: { gap: 92, pad: 56, thickness: 400, swing: 18, swell: 12 },
  },
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
 *  container owns what is selected. Arrow keys along the thread move the selection. */
export function Loom({ knots, selected, onSelect, now, orientation, threadStyle, scale, drawKey, numbered, label }: LoomProps) {
  const vertical = orientation === 'vertical'
  const g = React.useMemo(
    () => weave(knots, { ...SIZES[scale][orientation], twisted: threadStyle === 'rope', vertical }),
    [knots, scale, orientation, threadStyle, vertical],
  )
  const scroller = React.useRef<HTMLDivElement>(null)
  const beads = React.useRef(new Map<string, HTMLButtonElement>())
  const draw = g.beads.length > 0 ? Math.min(1800, 500 + g.beads.length * 70) : 0

  // Bring the selected knot to the middle of the view, gliding rather than jumping.
  React.useEffect(() => {
    const el = scroller.current
    const bead = g.beads.find((b) => b.key === selected)
    if (!el || !bead) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (vertical) el.scrollTo({ top: bead.along - el.clientHeight / 2, behavior: reduce ? 'auto' : 'smooth' })
    else el.scrollTo({ left: bead.along - el.clientWidth / 2, behavior: reduce ? 'auto' : 'smooth' })
  }, [selected, g, vertical])

  // A mouse wheel scrolls a horizontal thread sideways; a press-and-drag pulls it along.
  const onWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (vertical || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return
    event.currentTarget.scrollLeft += event.deltaY
  }
  const drag = React.useRef<{ start: number; scroll: number; moved: boolean } | null>(null)
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !scroller.current) return
    drag.current = {
      start: vertical ? event.clientY : event.clientX,
      scroll: vertical ? scroller.current.scrollTop : scroller.current.scrollLeft,
      moved: false,
    }
  }
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d || !scroller.current) return
    const delta = (vertical ? event.clientY : event.clientX) - d.start
    if (Math.abs(delta) > 4) d.moved = true
    if (!d.moved) return
    scroller.current.dataset.dragging = 'true'
    if (vertical) scroller.current.scrollTop = d.scroll - delta
    else scroller.current.scrollLeft = d.scroll - delta
  }
  const endDrag = () => {
    if (scroller.current) delete scroller.current.dataset.dragging
    window.setTimeout(() => (drag.current = null), 0)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    const back = vertical ? 'ArrowUp' : 'ArrowLeft'
    const on = vertical ? 'ArrowDown' : 'ArrowRight'
    if (event.key !== back && event.key !== on && event.key !== 'Home' && event.key !== 'End') return
    const at = g.beads.findIndex((b) => b.key === selected)
    const next =
      event.key === 'Home' ? 0 : event.key === 'End' ? g.beads.length - 1 : Math.max(0, Math.min(g.beads.length - 1, at + (event.key === on ? 1 : -1)))
    const bead = g.beads[next]
    if (!bead) return
    event.preventDefault()
    onSelect(bead.key)
    beads.current.get(bead.key)?.focus({ preventScroll: true })
  }

  const chosen = g.beads.find((b) => b.key === selected)
  const box = vertical ? { width: g.thickness, height: g.length } : { width: g.length, height: g.thickness }
  const pos = (along: number, across: number): React.CSSProperties =>
    vertical ? { left: across, top: along } : { left: along, top: across }

  return (
    <div
      ref={scroller}
      className="aw-loom"
      data-orientation={orientation}
      data-scale={scale}
      data-style={threadStyle}
      role="listbox"
      aria-label={label}
      aria-orientation={orientation}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerLeave={endDrag}
      onKeyDown={onKeyDown}
      style={{ '--draw': `${draw}ms` } as React.CSSProperties}
    >
      <div className="aw-loom-cloth" style={box} key={`${drawKey ?? ''}|${orientation}|${threadStyle}`}>
        <svg className="aw-loom-svg aw-loom-reveal" width={box.width} height={box.height} aria-hidden="true">
          <g>
            {threadStyle === 'rope' ? (
              <>
                {g.strands.map((s, i) => (
                  <path key={`u${i}`} d={s.under} className="aw-loom-strand" data-madder={s.madder ? 'true' : undefined} data-layer="under" />
                ))}
                {g.strands.map((s, i) => (
                  <path key={`o${i}`} d={s.over} className="aw-loom-strand" data-madder={s.madder ? 'true' : undefined} data-layer="over" />
                ))}
              </>
            ) : (
              <>
                <path d={g.centre} className="aw-loom-halo" />
                <path d={g.centre} className="aw-loom-line" />
              </>
            )}
          </g>
          <path d={g.centre} className="aw-loom-glint" pathLength={1000} />
          {chosen ? (
            <circle
              key={chosen.key}
              className="aw-loom-loop"
              cx={vertical ? chosen.across : chosen.along}
              cy={vertical ? chosen.along : chosen.across}
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
                role="option"
                aria-selected={isSelected}
                tabIndex={isSelected || (!selected && b.index === 0) ? 0 : -1}
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
                  if (!drag.current?.moved) onSelect(b.key)
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
