import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { KNOT_GLYPH, LINK_LABEL } from '@/lib/threadKnots'
import { formatCount, formatDateTime, formatDay, formatDuration } from '@/lib/format'
import type { AgentColorVars } from '@/lib/agentColors'
import type { KnotLink, ThreadKnot } from '@/api/thread'
import { Loom, type LoomHow } from './Loom'
import '@/styles/thread-loom.css'

export interface ThreadLoomProps {
  surface: readonly ThreadKnot[]
  /** The knots under each opened knot, by its key; undefined while that level is still loading. */
  levels: Record<string, readonly ThreadKnot[] | undefined>
  /** The selected knot and the knots it lies under, surface first. */
  path: readonly string[]
  onPath: (path: string[]) => void
  now: Date
  drawKey?: number
  actorColor: (name: string) => AgentColorVars
  onOpenLink: (link: KnotLink) => void
  /** How many surface knots there are in all, loaded or not; the header counts them when the
   *  project has no chapters. Defaults to the loaded ones. */
  surfaceTotal?: number
  /** More knots lie beyond the loaded ones of a level (`SURFACE_LEVEL` for the surface). */
  hasMore?: (under: string, side: 'before' | 'after') => boolean
  onMore?: (under: string, side: 'before' | 'after') => void
  /** The header's two controls; without them they select among the loaded surface knots. */
  onBeginning?: () => void
  onPresent?: () => void
  atBeginning?: boolean
  atPresent?: boolean
  /** Changes whenever the selected knot should take keyboard focus (an address was opened). */
  focusTick?: number
  /** Changes whenever the selected knot should be brought into view again. */
  reveal?: number
  /** Shown above the thread: what could not be read. */
  notice?: React.ReactNode
  /** Offered in the header beside the two controls. */
  actions?: React.ReactNode
}

/** The key `hasMore` and `onMore` name the surface by. */
export const SURFACE_LEVEL = 'surface'

const DAY = 86_400

function lasted(knot: ThreadKnot): string | null {
  const seconds = (Date.parse(knot.end) - Date.parse(knot.start)) / 1000
  if (!(seconds > 0)) return null
  if (seconds < DAY && knot.kind !== 'chapter') return formatDuration(seconds)
  const days = Math.round(seconds / DAY)
  return days === 1 ? '1 day' : `${days} days`
}

function plural(word: string, n: number): string {
  const lower = word.toLowerCase()
  if (n === 1 || lower.endsWith('s')) return lower
  return lower.endsWith('y') ? `${lower.slice(0, -1)}ies` : `${lower}s`
}

/** A chapter spans whole days, as the manager wrote them: read as calendar days, not instants, so
 *  no time zone moves a chapter onto the day after. */
function chapterDays(knot: ThreadKnot, now: Date): string {
  const a = formatDay(knot.start.slice(0, 10), now)
  const b = formatDay(knot.end.slice(0, 10), now)
  return a === b ? a : `${a} – ${b}`
}

/** The day a knot starts or ends on, as `formatDay` takes it: a chapter's as the manager wrote it. */
function dayOf(knot: ThreadKnot, edge: 'start' | 'end'): string {
  return knot.kind === 'chapter' ? knot[edge].slice(0, 10) : knot[edge]
}

function when(knot: ThreadKnot, now: Date): string {
  const sameDay = formatDay(knot.start, now) === formatDay(knot.end, now)
  if (knot.kind === 'chapter') return chapterDays(knot, now)
  const a = formatDateTime(knot.start, now)
  const b = formatDateTime(knot.end, now)
  return a === b ? a : `${a} – ${sameDay ? b.split(', ')[1] : b}`
}

function ActorChip({ name, color }: { name: string; color: AgentColorVars }) {
  return (
    <span className="aw-loom-actor" style={{ '--actor': color.accent, '--actor-tint': color.tint } as React.CSSProperties}>
      <span className="aw-loom-actor-dot" aria-hidden="true" />
      {name}
    </span>
  )
}

/** The Thread page laid left to right, with what the selected knot holds beneath it: its story, its
 *  span, who was in it, what it is made of, and the thread it opens into, which can be followed all
 *  the way down. Presentational: the container owns the path and what is loaded. */
export function ThreadLoom({
  surface,
  levels,
  path,
  onPath,
  now,
  drawKey,
  actorColor,
  onOpenLink,
  surfaceTotal,
  hasMore,
  onMore,
  onBeginning,
  onPresent,
  atBeginning,
  atPresent,
  focusTick = 0,
  reveal = 0,
  notice,
  actions,
}: ThreadLoomProps) {
  const find = React.useMemo(() => {
    const all = new Map<string, ThreadKnot>()
    for (const k of surface) all.set(k.key, k)
    for (const level of Object.values(levels)) for (const k of level ?? []) all.set(k.key, k)
    return all
  }, [surface, levels])

  const focusKey = path[path.length - 1] ?? null
  const focus = focusKey ? find.get(focusKey) ?? null : null
  const parentKey = path.length > 1 ? path[path.length - 2]! : null
  const siblings: readonly ThreadKnot[] = parentKey ? levels[parentKey] ?? [] : surface
  const index = focus ? siblings.findIndex((k) => k.key === focus.key) : -1
  // "Chapter 17 of 17": counted among its own kind, so a loose knot beside the chapters is not one.
  const ofKind = focus ? siblings.filter((k) => k.kind === focus.kind) : []

  // The thread beneath: what the knot holds, or, for a knot that holds nothing, the thread it lies on.
  const holds = !!focus && focus.child_count > 0
  const innerKey = holds ? focusKey : focus ? parentKey ?? SURFACE_LEVEL : null
  const inner = innerKey === SURFACE_LEVEL ? surface : innerKey ? levels[innerKey] : undefined
  const innerSelected = holds ? null : focusKey
  // The knots above whatever the inner thread holds.
  const innerPrefix = holds ? path : path.slice(0, -1)

  // A choice made from the keyboard takes focus with it, wherever the chosen knot is now drawn.
  const [keyTick, setKeyTick] = React.useState(0)
  const go = React.useCallback(
    (next: string[], how: LoomHow = 'pointer') => {
      onPath(next)
      if (how === 'key') setKeyTick((n) => n + 1)
    },
    [onPath],
  )
  const pickInner = (key: string, how: LoomHow) => go([...innerPrefix, key], how)

  // Enter on a knot that holds others selects the first it holds, once that has been read.
  const descending = React.useRef<string | null>(null)
  const enter = (prefix: readonly string[], key: string) => {
    const knot = find.get(key)
    if (!knot || knot.child_count === 0) return
    const first = levels[key]?.[0]
    if (first) {
      descending.current = null
      go([...prefix, key, first.key], 'key')
    } else {
      descending.current = key
      go([...prefix, key], 'key')
    }
  }
  React.useEffect(() => {
    const key = descending.current
    const first = key ? levels[key]?.[0] : undefined
    if (!key || !first) return
    descending.current = null
    if (path[path.length - 1] === key) go([...path, first.key], 'key')
  }, [levels, path, go])

  const root = React.useRef<HTMLDivElement>(null)
  const focusing = React.useRef(false)
  React.useEffect(() => {
    if (focusTick || keyTick) focusing.current = true
  }, [focusTick, keyTick])
  React.useEffect(() => {
    if (!focusing.current || !root.current || !focusKey) return
    // A knot is drawn on the surface, or beside its siblings on the inner thread; a knot that holds
    // others below the surface shows its own knots there instead, so its heading takes focus.
    const where = path.length === 1 ? '.aw-loom-main' : !holds ? '.aw-loom-inner' : null
    const target = where
      ? Array.from(root.current.querySelectorAll<HTMLElement>(`${where} [data-slot="loom-bead"]`)).find((el) => el.dataset.key === focusKey)
      : root.current.querySelector<HTMLElement>('.aw-loom-detail-title')
    if (!target) return
    focusing.current = false
    target.focus({ preventScroll: true })
  })

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== 'Escape' || path.length < 2) return
    event.preventDefault()
    go(path.slice(0, -1), 'key')
  }

  const kinds = React.useMemo(() => {
    if (!holds || !inner) return []
    const counts = new Map<string, { word: string; glyph: string; n: number }>()
    for (const k of inner) {
      const word = k.kind === 'fold' ? 'group' : k.word
      const entry = counts.get(word) ?? { word, glyph: KNOT_GLYPH[k.kind], n: 0 }
      entry.n += 1
      counts.set(word, entry)
    }
    return [...counts.values()].sort((a, b) => b.n - a.n)
  }, [holds, inner])

  const people = React.useMemo(() => {
    const names = new Set(focus?.actors ?? [])
    if (holds) for (const k of inner ?? []) for (const a of k.actors) names.add(a)
    return [...names]
  }, [focus, holds, inner])

  const surfaceSelected = path[0] ?? null
  const chapters = surface.filter((k) => k.kind === 'chapter').length
  const loose = surface.length - chapters
  const total = surfaceTotal ?? surface.length
  const step = (by: 1 | -1) => {
    const next = siblings[index + by]
    if (next) go([...path.slice(0, -1), next.key])
  }
  const first = surface[0]
  const last = surface[surface.length - 1]
  const beginningOff = atBeginning ?? surfaceSelected === first?.key
  const presentOff = atPresent ?? surfaceSelected === last?.key

  return (
    <div className="aw-loom-page" ref={root} onKeyDown={onKeyDown}>
      {notice}
      <header className="aw-loom-bar">
        <div className="aw-loom-bar-title">
          <span className="aw-loom-bar-count">
            {chapters > 0
              ? `${formatCount(chapters)} ${chapters === 1 ? 'chapter' : 'chapters'}`
              : `${formatCount(total)} ${total === 1 ? 'knot' : 'knots'}`}
          </span>
          {first && last ? (
            <span className="aw-loom-bar-span">
              {formatDay(dayOf(first, 'start'), now)} to {formatDay(dayOf(last, 'end'), now)}
              {chapters > 0 && loose > 0 ? ` · ${formatCount(loose)} newer ${loose === 1 ? 'knot' : 'knots'} not in a chapter yet` : ''}
            </span>
          ) : null}
        </div>
        <div className="aw-loom-bar-actions" role="group" aria-label="Move along the thread">
          {actions}
          <Button variant="ghost" size="sm" data-slot="loom-jump" disabled={beginningOff} onClick={() => (onBeginning ? onBeginning() : first && go([first.key]))}>
            <Icon name="arrow_left" size={14} /> The beginning
          </Button>
          <Button variant="ghost" size="sm" data-slot="loom-jump" disabled={presentOff} onClick={() => (onPresent ? onPresent() : last && go([last.key]))}>
            The present <Icon name="arrow_forward" size={14} />
          </Button>
        </div>
      </header>

      <div className="aw-loom-stage">
        <div className="aw-loom-main">
          <Loom
            knots={surface}
            selected={surfaceSelected}
            onSelect={(key, how) => go([key], how)}
            now={now}
            scale="surface"
            drawKey={drawKey}
            reveal={reveal + focusTick}
            hasBefore={hasMore?.(SURFACE_LEVEL, 'before')}
            hasAfter={hasMore?.(SURFACE_LEVEL, 'after')}
            onMore={onMore ? (side) => onMore(SURFACE_LEVEL, side) : undefined}
            onEnter={(key) => enter([], key)}
            numbered
            label="The project's thread"
          />
        </div>

        <section className="aw-loom-detail" aria-live="polite" aria-label="The selected knot">
          {focus ? (
            <div className="aw-loom-detail-card" key={focus.key}>
              {path.length > 1 ? (
                <nav className="aw-loom-crumbs" aria-label="Where this knot lies">
                  {path.slice(0, -1).map((key, i) => {
                    const k = find.get(key)
                    return (
                      <React.Fragment key={key}>
                        <button type="button" data-slot="loom-crumb" className="aw-loom-crumb" onClick={() => go(path.slice(0, i + 1) as string[])}>
                          <Icon name={k ? KNOT_GLYPH[k.kind] : 'more_horiz'} size={12} />
                          <span>{k?.title ?? 'Knot'}</span>
                        </button>
                        <Icon name="chevron_right" size={12} className="aw-loom-crumb-sep" />
                      </React.Fragment>
                    )
                  })}
                </nav>
              ) : null}

              <div className="aw-loom-detail-head">
                <span className="aw-loom-detail-kind">
                  <Icon name={KNOT_GLYPH[focus.kind]} size={14} />
                  {focus.word}
                  {index >= 0 ? (
                    <span className="aw-loom-detail-of">
                      {formatCount(ofKind.indexOf(focus) + 1)} of {formatCount(ofKind.length)}
                    </span>
                  ) : null}
                </span>
                <div className="aw-loom-detail-nav">
                  <button type="button" data-slot="loom-step" className="aw-loom-step" disabled={index <= 0} onClick={() => step(-1)} aria-label="The knot before">
                    <Icon name="arrow_left" size={14} />
                  </button>
                  <button type="button" data-slot="loom-step" className="aw-loom-step" disabled={index < 0 || index >= siblings.length - 1} onClick={() => step(1)} aria-label="The knot after">
                    <Icon name="arrow_forward" size={14} />
                  </button>
                </div>
              </div>

              <h2 className="aw-loom-detail-title" tabIndex={-1}>{focus.title}</h2>
              {focus.summary ? <p className="aw-loom-detail-summary">{focus.summary}</p> : null}

              <dl className="aw-loom-facts">
                <div className="aw-loom-fact">
                  <dt>When</dt>
                  <dd>
                    {when(focus, now)}
                    {lasted(focus) ? <span className="aw-loom-fact-sub"> · {lasted(focus)}</span> : null}
                  </dd>
                </div>
                {focus.child_count > 0 ? (
                  <div className="aw-loom-fact">
                    <dt>Holds</dt>
                    <dd>
                      {formatCount(focus.child_count)} {focus.child_count === 1 ? 'knot' : 'knots'}
                      {focus.descendant_count > focus.child_count ? (
                        <span className="aw-loom-fact-sub"> · {formatCount(focus.descendant_count)} all the way down</span>
                      ) : null}
                    </dd>
                  </div>
                ) : null}
                {people.length > 0 ? (
                  <div className="aw-loom-fact aw-loom-fact-wide">
                    <dt>{holds ? 'Who was in it' : 'Who'}</dt>
                    <dd className="aw-loom-actors">
                      {people.map((name) => (
                        <ActorChip key={name} name={name} color={actorColor(name)} />
                      ))}
                    </dd>
                  </div>
                ) : null}
                {kinds.length > 0 ? (
                  <div className="aw-loom-fact aw-loom-fact-wide">
                    <dt>Made of</dt>
                    <dd className="aw-loom-kinds">
                      {kinds.map((k) => (
                        <span key={k.word} className="aw-loom-kindchip">
                          <Icon name={k.glyph} size={12} />
                          {formatCount(k.n)} {plural(k.word, k.n)}
                        </span>
                      ))}
                    </dd>
                  </div>
                ) : null}
              </dl>

              {focus.link ? (
                <div className="aw-loom-detail-actions">
                  <Button variant="outline" size="sm" data-slot="loom-open" onClick={() => onOpenLink(focus.link!)} title={focus.address}>
                    <Icon name="move_up" size={14} /> {LINK_LABEL[focus.link.object] ?? 'Open'}
                  </Button>
                </div>
              ) : null}

              {innerKey ? (
                <div className="aw-loom-inner">
                  <div className="aw-loom-inner-head">
                    {holds ? 'Inside' : 'Beside it on the thread'}
                    <span className="aw-loom-inner-hint">Drag or scroll along it</span>
                  </div>
                  {inner ? (
                    <Loom
                      knots={inner}
                      selected={innerSelected}
                      onSelect={pickInner}
                      now={now}
                      scale="inner"
                      drawKey={`${innerKey}|${drawKey ?? ''}`}
                      reveal={reveal + focusTick}
                      hasBefore={hasMore?.(innerKey, 'before')}
                      hasAfter={hasMore?.(innerKey, 'after')}
                      onMore={onMore ? (side) => onMore(innerKey, side) : undefined}
                      onEnter={(key) => enter(innerPrefix, key)}
                      label={holds ? `Inside: ${focus.title}` : 'The thread this knot lies on'}
                    />
                  ) : (
                    <p className="aw-loom-unspool aw-delayed" role="status">
                      Unspooling…
                    </p>
                  )}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="aw-loom-empty">Choose a knot on the thread to see what it holds.</p>
          )}
        </section>
      </div>
    </div>
  )
}
