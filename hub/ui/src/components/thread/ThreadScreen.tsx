import * as React from 'react'
import { getJson } from '@/api/client'
import { useAgents } from '@/api/agents'
import {
  SURFACE,
  knotUrl,
  threadUrl,
  toLoadedLevel,
  type KnotLink,
  type LoadedLevel,
  type ThreadKnot,
  type ThreadPageResponse,
  type ThreadQuery,
} from '@/api/thread'
import { useSSE } from '@/hooks/useSSE'
import { agentColorVars } from '@/lib/agentColors'
import { joinPage, refreshEnd } from '@/lib/threadKnots'
import { ThreadLoom } from './loom/ThreadLoom'
import { WeaveButton } from './WeaveButton'
import '@/styles/thread-loom.css'

/** Events that can add or change something on the thread. Anything else leaves it alone. */
const THREAD_EVENTS = new Set([
  'task_created',
  'task_updated',
  'spec_updated',
  'run_started',
  'run_completed',
  'run_failed',
  'run_stopped',
  'run_interrupted',
  'message_created',
  'question_asked',
  'question_answered',
  'permission_requested',
  'permission_decided',
  'job_fired',
  'chapters_updated',
  'agent_output',
])
/** Bursts of events (a run streams many) become one refresh. Well inside the five seconds. */
const REFRESH_AFTER_MS = 400

export interface ThreadScreenProps {
  projectId: string
  /** The address in the URL: select it with every knot above it, bring it into view, focus it. */
  knot: string | null
  /** The reader chose a knot: its address belongs in the URL. */
  onAddress: (key: string) => void
  onOpenLink: (link: KnotLink) => void
}

/** The Thread tab: fetches the feed one level at a time and holds what is loaded and which knot is
 *  selected (the path from the surface down to it); `ThreadLoom` draws it. */
export function ThreadScreen({ projectId, knot, onAddress, onOpenLink }: ThreadScreenProps) {
  const [levels, setLevels] = React.useState<Record<string, LoadedLevel | undefined>>({})
  const [path, setPath] = React.useState<string[]>([])
  const [surfaceTotal, setSurfaceTotal] = React.useState<number | undefined>(undefined)
  // A new surface drawn afresh (opening, a jump to either end): the thread draws itself in again.
  const [drawKey, setDrawKey] = React.useState(0)
  // An address opened: the knot it names takes keyboard focus and is brought into view.
  const [focusTick, setFocusTick] = React.useState(0)
  const [failed, setFailed] = React.useState(false)
  const [canWeave, setCanWeave] = React.useState(false)
  const [now] = React.useState(() => new Date())

  // Each agent's registered colour, as everywhere else in the app; people and the manager are neutral.
  // A roster that cannot be read leaves every chip neutral and says so (the notice below).
  const agents = useAgents()
  const actorColor = React.useMemo(() => {
    const byName = new Map<string, number | null | undefined>()
    for (const a of Array.isArray(agents.data) ? agents.data : []) byName.set(a.name, a.color_index)
    return (name: string) => agentColorVars(byName.get(name))
  }, [agents.data])

  const levelsRef = React.useRef(levels)
  levelsRef.current = levels
  const pathRef = React.useRef(path)
  pathRef.current = path
  const alive = React.useRef(true)
  React.useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  // The address this screen itself put in the URL, so the effect below does not answer its own write.
  const written = React.useRef<string | null>(null)
  // Pages asked for and not yet answered, so scrolling near an end asks once.
  const asking = React.useRef(new Set<string>())

  const fetchLevel = React.useCallback(
    async (query: ThreadQuery): Promise<LoadedLevel> => {
      const page = await getJson<ThreadPageResponse>(threadUrl(projectId, query))
      if (alive.current) {
        // Every page says whether the chapters job is on; a Hub that predates the job omits it.
        setCanWeave(page.can_weave === true)
        if (!query.under || query.under === SURFACE) setSurfaceTotal(page.total)
      }
      return toLoadedLevel(page)
    },
    [projectId],
  )
  const store = React.useCallback((under: string, level: LoadedLevel) => {
    if (alive.current) setLevels((prev) => ({ ...prev, [under]: level }))
  }, [])

  const lookup = (key: string): ThreadKnot | undefined => {
    for (const level of Object.values(levelsRef.current)) {
      const found = level?.knots.find((k) => k.key === key)
      if (found) return found
    }
    return undefined
  }
  /** What a selected knot holds, read once: the panel draws it as the smaller thread. */
  const readInside = React.useCallback(
    (held: ThreadKnot | undefined) => {
      if (!held || held.child_count === 0 || levelsRef.current[held.key]) return
      fetchLevel({ under: held.key, first: true }).then(
        (level) => store(held.key, level),
        () => alive.current && setFailed(true),
      )
    },
    [fetchLevel, store],
  )

  // Opening the tab: the newest page, with the newest surface knot selected at the right.
  const addressed = knot !== null
  React.useEffect(() => {
    if (addressed) return
    let cancelled = false
    setFailed(false)
    fetchLevel({})
      .then((level) => {
        if (cancelled) return
        store(SURFACE, level)
        const newest = level.knots[level.knots.length - 1]
        setPath(newest ? [newest.key] : [])
        setDrawKey((n) => n + 1)
        readInside(newest)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [addressed, fetchLevel, store, readInside])

  // An address: read every level on the way down at the page that holds it, and what the knot itself
  // holds, then select it with every knot above it and give it focus.
  React.useEffect(() => {
    if (!knot || knot === written.current) return
    let cancelled = false
    setFailed(false)
    ;(async () => {
      const found = await getJson<{ knot: ThreadKnot; ancestors: string[] }>(knotUrl(projectId, knot))
      const under = [SURFACE, ...found.ancestors]
      const targets = [...found.ancestors, found.knot.key]
      const holds = found.knot.child_count > 0
      const [loaded, own] = await Promise.all([
        Promise.all(under.map((u, i) => fetchLevel({ under: u, around: targets[i] }))),
        holds ? fetchLevel({ under: found.knot.key, first: true }) : Promise.resolve(undefined),
      ])
      if (cancelled || !alive.current) return
      setLevels((prev) => {
        const next = { ...prev }
        under.forEach((u, i) => {
          next[u] = loaded[i]
        })
        if (own) next[found.knot.key] = own
        return next
      })
      setPath(targets)
      setDrawKey((n) => n + 1)
      setFocusTick((n) => n + 1)
    })().catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [knot, projectId, fetchLevel])

  const choose = (next: string[]) => {
    const key = next[next.length - 1]
    setPath(next)
    if (!key) return
    written.current = key
    onAddress(key)
    readInside(lookup(key))
  }

  const more = (under: string, direction: 'before' | 'after') => {
    const held = levelsRef.current[under]
    const cursor = direction === 'before' ? held?.beforeCursor : held?.afterCursor
    const ask = `${under}|${direction}|${cursor}`
    if (!held || !cursor || asking.current.has(ask)) return
    asking.current.add(ask)
    const query: ThreadQuery = { under, ...(direction === 'before' ? { before: cursor } : { after: cursor }) }
    fetchLevel(query)
      .then(
        (page) => {
          if (!alive.current) return
          setLevels((prev) => {
            const base = prev[under]
            return base ? { ...prev, [under]: joinPage(base, page, direction) } : prev
          })
        },
        () => alive.current && setFailed(true),
      )
      .finally(() => asking.current.delete(ask))
  }
  const hasMore = (under: string, direction: 'before' | 'after') => {
    const held = levels[under]
    return !!held && (direction === 'before' ? held.hasBefore : held.hasAfter)
  }

  // Either end of the surface: selected at once when it is loaded, read afresh when it is not.
  const jump = (end: 'beginning' | 'present') => {
    const surface = levelsRef.current[SURFACE]
    if (!surface) return
    const loadedEnd = end === 'beginning' ? !surface.hasBefore : !surface.hasAfter
    const pick = (knots: ThreadKnot[]) => (end === 'beginning' ? knots[0] : knots[knots.length - 1])
    if (loadedEnd) {
      const target = pick(surface.knots)
      if (target) choose([target.key])
      return
    }
    fetchLevel(end === 'beginning' ? { first: true } : {}).then(
      (level) => {
        store(SURFACE, level)
        setDrawKey((n) => n + 1)
        const target = pick(level.knots)
        if (target) choose([target.key])
      },
      () => alive.current && setFailed(true),
    )
  }

  // Live: a level that reaches the present end takes the newest page; a level the reader has
  // scrolled away from is not touched, so their view does not move.
  const refresh = React.useCallback(() => {
    const reaching = Object.entries(levelsRef.current).filter(
      ([under, level]) => level && !level.hasAfter && (under === SURFACE || pathRef.current.includes(under)),
    )
    for (const [under] of reaching) {
      fetchLevel({ under }).then(
        (newest) => {
          if (!alive.current) return
          setLevels((prev) => {
            const base = prev[under]
            // Gone from the present end while the request was out: leave it as the reader has it.
            if (!base || base.hasAfter) return prev
            return { ...prev, [under]: refreshEnd(base, newest) }
          })
        },
        () => undefined,
      )
    }
  }, [fetchLevel])
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  React.useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )
  useSSE((event) => {
    const owner = (event.data as { project_id?: string } | null)?.project_id
    if (owner !== projectId || !THREAD_EVENTS.has(event.type)) return
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(refresh, REFRESH_AFTER_MS)
  })

  const inner = React.useMemo(() => {
    const out: Record<string, readonly ThreadKnot[] | undefined> = {}
    for (const [under, level] of Object.entries(levels)) if (under !== SURFACE) out[under] = level?.knots
    return out
  }, [levels])

  const surface = levels[SURFACE]
  if (!surface) {
    return (
      <p className="aw-thread-note aw-delayed" role={failed ? 'alert' : 'status'}>
        {failed ? 'The thread could not be read. Reload to try again.' : 'Unspooling…'}
      </p>
    )
  }
  const first = surface.knots[0]
  const last = surface.knots[surface.knots.length - 1]
  return (
    <ThreadLoom
      surface={surface.knots}
      levels={inner}
      path={path}
      onPath={choose}
      now={now}
      drawKey={drawKey}
      focusTick={focusTick}
      actorColor={actorColor}
      onOpenLink={onOpenLink}
      surfaceTotal={surfaceTotal}
      surfaceSummary={surface.summary}
      hasMore={hasMore}
      onMore={more}
      onBeginning={() => jump('beginning')}
      onPresent={() => jump('present')}
      atBeginning={!surface.hasBefore && path[0] === first?.key}
      atPresent={!surface.hasAfter && path[0] === last?.key}
      notice={
        failed || agents.isError ? (
          <>
            {failed ? (
              <p className="aw-thread-note" role="alert">
                Part of the thread could not be read.
              </p>
            ) : null}
            {agents.isError ? (
              <p className="aw-thread-note" role="status">
                The agents could not be read, so they are shown without their colours.
              </p>
            ) : null}
          </>
        ) : null
      }
      actions={canWeave ? <WeaveButton /> : null}
    />
  )
}
