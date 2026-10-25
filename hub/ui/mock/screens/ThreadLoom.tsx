import * as React from 'react'
import type { ThreadKnot } from '@/api/thread'
import { ThreadLoom } from '@/components/thread/loom/ThreadLoom'
import { agentColorVars } from '@/lib/agentColors'
import { LINK_LABEL } from '@/lib/threadKnots'
import recorded from '../thread-chapters-fixture.json'

/** This repository's thread as the operator's own Hub shows it today: its 17 chapters, recorded
 *  read-only from a copy of that Hub's database with the Hub's own code (chapters overlay). */
const levels = (recorded as unknown as { levels: Record<string, { knots: ThreadKnot[] }> }).levels
const surface = levels.surface!.knots
// mock state: a knot whose level was not recorded opens onto nothing rather than loading forever.
const byKey: Record<string, ThreadKnot[]> = new Proxy(
  Object.fromEntries(Object.entries(levels).filter(([k]) => k !== 'surface').map(([k, v]) => [k, v.knots])),
  { get: (target, key: string) => target[key] ?? [] },
)

// mock state: agents take colours by order of first appearance; the app reads each agent's
// registered colour_index instead. People and the manager stay neutral.
const order: string[] = []
for (const level of Object.values(levels)) for (const k of level.knots) for (const a of k.actors) if (!order.includes(a)) order.push(a)
const NEUTRAL = new Set(['Operator', 'manager', 'gutohuida'])
const agents = order.filter((a) => !NEUTRAL.has(a))
const actorColor = (name: string) => agentColorVars(NEUTRAL.has(name) ? null : agents.indexOf(name))

export default function ThreadLoomScreen({ drawKey = 0, now }: { drawKey?: number; now: Date }) {
  // Opens on the newest chapter, the way the thread opens at the present.
  const [path, setPath] = React.useState<string[]>(() => [surface[surface.length - 2]!.key])
  const [followed, setFollowed] = React.useState<string | null>(null)
  return (
    <>
      <ThreadLoom
        surface={surface}
        levels={byKey}
        path={path}
        onPath={setPath}
        now={now}
        drawKey={drawKey}
        actorColor={actorColor}
        onOpenLink={(link) => {
          setFollowed(LINK_LABEL[link.object] ?? 'Open')
          window.setTimeout(() => setFollowed(null), 2200)
        }}
      />
      {followed ? (
        <p className="mock-loom-toast" role="status">
          {followed} (in the app this leaves the thread)
        </p>
      ) : null}
    </>
  )
}
