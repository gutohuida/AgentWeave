import * as React from 'react'
import { SURFACE, type KnotLink, type ThreadKnot, type ThreadLevelData } from '@/api/thread'
import { Thread } from '@/components/thread/Thread'
import { LINK_LABEL } from '@/lib/threadKnots'
import recorded from '../thread-fixture.json'
import type { ScreenProps } from '../routes'

/** The trial Hub's feed for this repository's project, recorded by mock/record_thread.py: every
 *  level the mock can open, as `GET /thread` returns its knots. */
const levels = (recorded as unknown as { levels: Record<string, { knots: ThreadKnot[] }> }).levels
const PAGE = 20

/** Thread tab. A container such as the app's will be holds what is loaded and what is open; here
 *  the recording answers, paged the way the route pages (newest first, "Earlier" walks back). */
export default function ThreadScreen({ now }: ScreenProps) {
  const surface = levels[SURFACE]!.knots
  const [from, setFrom] = React.useState(Math.max(0, surface.length - PAGE))
  const [to, setTo] = React.useState(surface.length)
  const [open, setOpen] = React.useState<ReadonlySet<string>>(() => new Set())
  const [current, setCurrent] = React.useState<string | null>(surface[surface.length - 1]?.key ?? null)
  const [reveal, setReveal] = React.useState(0)
  const [followed, setFollowed] = React.useState<string | null>(null)

  const loaded = React.useMemo(() => {
    const out: Record<string, ThreadLevelData | undefined> = {
      [SURFACE]: { knots: surface.slice(from, to), hasBefore: from > 0, hasAfter: to < surface.length },
    }
    for (const [key, level] of Object.entries(levels)) if (key !== SURFACE) out[key] = { knots: level.knots, hasBefore: false, hasAfter: false }
    return out
  }, [surface, from, to])

  // mock state: a knot whose level was not recorded opens onto nothing rather than loading forever.
  const levelsFor = React.useMemo(
    () =>
      new Proxy(loaded, {
        get: (target, key: string) => target[key] ?? { knots: [], hasBefore: false, hasAfter: false },
      }),
    [loaded],
  )

  const toggle = (key: string) => {
    const closing = open.has(key)
    setOpen((prev) => {
      const next = new Set(prev)
      if (closing) next.delete(key)
      else next.add(key)
      return next
    })
    setCurrent(key)
    // Closing brings the closed knot back into view: the reader is not left where its children were.
    if (closing) setReveal((n) => n + 1)
  }
  const more = (under: string, direction: 'before' | 'after') => {
    if (under !== SURFACE) return
    if (direction === 'before') setFrom((f) => Math.max(0, f - PAGE))
    else setTo((t) => Math.min(surface.length, t + PAGE))
  }
  const toBeginning = () => {
    setFrom(0)
    setTo(Math.min(surface.length, PAGE))
    setCurrent(surface[0]?.key ?? null)
    setReveal((n) => n + 1)
  }
  const toPresent = () => {
    setFrom(Math.max(0, surface.length - PAGE))
    setTo(surface.length)
    setCurrent(surface[surface.length - 1]?.key ?? null)
    setReveal((n) => n + 1)
  }
  const follow = (link: KnotLink) => setFollowed(LINK_LABEL[link.object] ?? 'Open')

  return (
    <>
      <Thread
        levels={levelsFor}
        open={open}
        current={current}
        reveal={reveal}
        now={now}
        atBeginning={current === surface[0]?.key}
        atPresent={current === surface[surface.length - 1]?.key}
        onToggle={toggle}
        onMore={more}
        onJumpToBeginning={toBeginning}
        onBackToPresent={toPresent}
        onOpenLink={follow}
      />
      {followed ? (
        <p className="aw-thread-note" role="status" style={{ position: 'fixed', bottom: 56, right: 24, margin: 0 }}>
          {followed} (in the app this leaves the thread)
        </p>
      ) : null}
    </>
  )
}
