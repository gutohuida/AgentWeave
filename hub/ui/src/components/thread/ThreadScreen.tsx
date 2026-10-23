import * as React from 'react'
import { getJson } from '@/api/client'
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
import { joinPage, refreshEnd } from '@/lib/threadKnots'
import { Thread } from './Thread'

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
  'agent_output',
])
/** Bursts of events (a run streams many) become one refresh. Well inside the five seconds. */
const REFRESH_AFTER_MS = 400

export interface ThreadScreenProps {
  projectId: string
  /** The address in the URL: open its ancestors, bring it into view, focus it. */
  knot: string | null
  /** The reader touched a knot: its address belongs in the URL. */
  onAddress: (key: string) => void
  onOpenLink: (link: KnotLink) => void
}

/** The Thread tab: fetches the feed one level at a time and holds what is loaded and what is open. */
export function ThreadScreen({ projectId, knot, onAddress, onOpenLink }: ThreadScreenProps) {
  const [levels, setLevels] = React.useState<Record<string, LoadedLevel | undefined>>({})
  const [open, setOpen] = React.useState<ReadonlySet<string>>(() => new Set())
  const [current, setCurrent] = React.useState<string | null>(null)
  const [reveal, setReveal] = React.useState(0)
  const [failed, setFailed] = React.useState(false)
  const [now] = React.useState(() => new Date())

  const levelsRef = React.useRef(levels)
  levelsRef.current = levels
  const openRef = React.useRef(open)
  openRef.current = open
  const alive = React.useRef(true)
  React.useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  // The address this screen itself put in the URL, so the effect below does not answer its own write.
  const written = React.useRef<string | null>(null)

  const fetchLevel = React.useCallback(
    async (query: ThreadQuery): Promise<LoadedLevel> =>
      toLoadedLevel(await getJson<ThreadPageResponse>(threadUrl(projectId, query))),
    [projectId],
  )
  const store = React.useCallback((under: string, level: LoadedLevel) => {
    if (alive.current) setLevels((prev) => ({ ...prev, [under]: level }))
  }, [])

  // Opening the tab: the newest page, so the present end is what is in view.
  const addressed = knot !== null
  React.useEffect(() => {
    if (addressed) return
    let cancelled = false
    setFailed(false)
    fetchLevel({})
      .then((level) => {
        if (cancelled) return
        store(SURFACE, level)
        setCurrent(level.knots[level.knots.length - 1]?.key ?? null)
        setReveal((n) => n + 1)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [addressed, fetchLevel, store])

  // An address: open every ancestor at the page that holds the way down, then land on the knot,
  // itself opened when it holds knots, as clicking it would have.
  React.useEffect(() => {
    if (!knot || knot === written.current) return
    let cancelled = false
    setFailed(false)
    ;(async () => {
      const found = await getJson<{ knot: ThreadKnot; ancestors: string[] }>(knotUrl(projectId, knot))
      const path = [SURFACE, ...found.ancestors]
      const targets = [...found.ancestors, found.knot.key]
      const holds = found.knot.child_count > 0
      const [loaded, own] = await Promise.all([
        Promise.all(path.map((under, i) => fetchLevel({ under, around: targets[i] }))),
        holds ? fetchLevel({ under: found.knot.key, first: true }) : Promise.resolve(undefined),
      ])
      if (cancelled || !alive.current) return
      setLevels((prev) => {
        const next = { ...prev }
        path.forEach((under, i) => {
          next[under] = loaded[i]
        })
        if (own) next[found.knot.key] = own
        return next
      })
      setOpen(new Set(holds ? targets : found.ancestors))
      setCurrent(found.knot.key)
      setReveal((n) => n + 1)
    })().catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [knot, projectId, fetchLevel])

  const toggle = (key: string) => {
    const closing = openRef.current.has(key)
    setOpen((prev) => {
      const next = new Set(prev)
      if (closing) next.delete(key)
      else next.add(key)
      return next
    })
    setCurrent(key)
    written.current = key
    onAddress(key)
    // Closing brings the closed knot back into view: the reader is not left where its children were.
    if (closing) setReveal((n) => n + 1)
    // Opening always asks again: what a knot holds may have grown since it was last open.
    else fetchLevel({ under: key, first: true }).then((level) => store(key, level), () => setFailed(true))
  }

  const more = (under: string, direction: 'before' | 'after') => {
    const held = levelsRef.current[under]
    const cursor = direction === 'before' ? held?.beforeCursor : held?.afterCursor
    if (!held || !cursor) return
    const query: ThreadQuery = { under, ...(direction === 'before' ? { before: cursor } : { after: cursor }) }
    fetchLevel(query).then(
      (page) => {
        if (!alive.current) return
        setLevels((prev) => {
          const base = prev[under]
          return base ? { ...prev, [under]: joinPage(base, page, direction) } : prev
        })
      },
      () => setFailed(true),
    )
  }

  const jump = (query: ThreadQuery, pick: (knots: ThreadKnot[]) => ThreadKnot | undefined) => {
    fetchLevel(query).then(
      (level) => {
        store(SURFACE, level)
        setCurrent(pick(level.knots)?.key ?? null)
        setReveal((n) => n + 1)
      },
      () => setFailed(true),
    )
  }
  const toBeginning = () => jump({ first: true }, (knots) => knots[0])
  const toPresent = () => jump({}, (knots) => knots[knots.length - 1])

  // Live: a level that reaches the present end takes the newest page; a level the reader has
  // scrolled away from is not touched, so their view does not move.
  const refresh = React.useCallback(() => {
    const reaching = Object.entries(levelsRef.current).filter(
      ([under, level]) => level && !level.hasAfter && (under === SURFACE || openRef.current.has(under)),
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

  const surface = levels[SURFACE]
  if (!surface) {
    return (
      <p className="aw-thread-note aw-delayed" role={failed ? 'alert' : 'status'}>
        {failed ? 'The thread could not be read. Reload to try again.' : 'Unspooling…'}
      </p>
    )
  }
  return (
    <>
      {failed ? (
        <p className="aw-thread-note" role="alert">
          Part of the thread could not be read.
        </p>
      ) : null}
      <Thread
        levels={levels}
        open={open}
        current={current}
        reveal={reveal}
        now={now}
        atBeginning={!surface.hasBefore}
        atPresent={!surface.hasAfter}
        onToggle={toggle}
        onMore={more}
        onJumpToBeginning={toBeginning}
        onBackToPresent={toPresent}
        onOpenLink={onOpenLink}
      />
    </>
  )
}
