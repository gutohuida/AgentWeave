import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { formatAgo, formatMoney } from '@/lib/format'
import '@/styles/spec-home.css'

/** The Spec tab's home (`spec-home-shows-what-is-being-built-what-was-built-and-how-it-relates`):
 *  what is being built, what was built, and how each relates to its roadmap and capabilities.
 *  Presentational: rows in, `onOpen` out. `relations` picks one of the three ways of showing how
 *  documents relate that the operator is choosing between (2026-11-17). */

export interface HomeDocRef {
  path: string
  title: string
}

export interface HomeBuild {
  id: string
  state: 'running' | 'finished'
  document: HomeDocRef
  roadmap: { document: HomeDocRef; slice: { key: string; title: string } } | null
  capabilities: HomeDocRef[]
  tasksDone: number
  tasksTotal: number
  /** Approved tasks whose work has not landed yet. */
  tasksLanding: number
  startedAt: string
  finishedAt: string | null
  /** Null when no run of it was priced. */
  spentUsd: number | null
}

export interface HomeCapability extends HomeDocRef {
  waiting: number
}

export type RelationsView = 'links' | 'tree' | 'map'

export function SpecHome({
  builds,
  capabilities,
  relations,
  now,
  onOpen,
}: {
  /** As `GET /project/builds` returns them: newest build first. */
  builds: HomeBuild[]
  capabilities: HomeCapability[]
  relations: RelationsView
  now: Date
  onOpen: (path: string, anchor?: string) => void
}) {
  const running = builds.filter((b) => b.state === 'running')
  const recent = latestFinished(builds, 10)
  const [focus, setFocus] = React.useState<string | null>(null)
  const shown = [...running, ...recent]

  return (
    <div className="aw-home" data-testid="spec-home" data-relations={relations}>
      <section className="aw-home-section" data-testid="spec-home-building">
        <h2 className="aw-home-h">
          Building now <span className="aw-home-count">{running.length}</span>
        </h2>
        {running.length === 0 ? (
          <p className="aw-home-empty">Nothing is being built.</p>
        ) : (
          <ul className="aw-home-rows">
            {running.map((b) => (
              <BuildRow key={b.id} build={b} now={now} relations={relations} focus={focus} onFocus={setFocus} onOpen={onOpen} />
            ))}
          </ul>
        )}
      </section>

      <section className="aw-home-section" data-testid="spec-home-recent">
        <h2 className="aw-home-h">Recently built</h2>
        {recent.length === 0 ? (
          <p className="aw-home-empty">Nothing has been built yet.</p>
        ) : (
          <ul className="aw-home-rows">
            {recent.map((b) => (
              <BuildRow key={b.id} build={b} now={now} relations={relations} focus={focus} onFocus={setFocus} onOpen={onOpen} />
            ))}
          </ul>
        )}
      </section>

      {relations === 'tree' ? <RelationTree builds={shown} focus={focus} onFocus={setFocus} onOpen={onOpen} /> : null}
      {relations === 'map' ? <RelationMap builds={shown} focus={focus} onFocus={setFocus} onOpen={onOpen} /> : null}

      {relations !== 'map' ? (
        <section className="aw-home-section" data-testid="spec-home-capabilities">
          <h2 className="aw-home-h">
            Capabilities <span className="aw-home-count">{capabilities.length}</span>
          </h2>
          <ul className="aw-home-caps">
            {capabilities.map((c) => (
              <li key={c.path}>
                <button
                  data-slot="home-capability"
                  type="button"
                  className="aw-home-cap"
                  data-testid="spec-home-capability-row"
                  data-path={c.path}
                  data-lit={focus ? litBy(shown, focus).has(c.path) || undefined : undefined}
                  onClick={() => onOpen(c.path)}
                >
                  <span className="aw-home-cap-title">{c.title}</span>
                  {c.waiting ? <span className="aw-home-cap-waiting">{c.waiting} waiting</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

/** The `limit` most recently finished builds, one per document at its latest finish. A stopped
 *  build is not built. */
export function latestFinished(builds: HomeBuild[], limit: number): HomeBuild[] {
  const seen = new Set<string>()
  return builds
    .filter((b) => b.state === 'finished' && b.finishedAt)
    .sort((a, b) => (b.finishedAt! < a.finishedAt! ? -1 : 1))
    .filter((b) => (seen.has(b.document.path) ? false : (seen.add(b.document.path), true)))
    .slice(0, limit)
}

/** Every path one focused document connects to, itself included. */
function litBy(builds: HomeBuild[], focus: string): Set<string> {
  const lit = new Set<string>([focus])
  for (const b of builds) {
    const paths = [b.document.path, ...(b.roadmap ? [b.roadmap.document.path] : []), ...b.capabilities.map((c) => c.path)]
    if (paths.includes(focus)) paths.forEach((p) => lit.add(p))
  }
  return lit
}

function BuildRow({
  build,
  now,
  relations,
  focus,
  onFocus,
  onOpen,
}: {
  build: HomeBuild
  now: Date
  relations: RelationsView
  focus: string | null
  onFocus: (path: string | null) => void
  onOpen: (path: string, anchor?: string) => void
}) {
  const running = build.state === 'running'
  const lit = focus ? litBy([build], focus).has(focus) && [build.document.path, build.roadmap?.document.path, ...build.capabilities.map((c) => c.path)].includes(focus) : false
  return (
    <li
      className="aw-home-row"
      data-testid={running ? 'spec-home-build-row' : 'spec-home-recent-row'}
      data-document={build.document.path}
      data-build={build.id}
      data-finished-at={build.finishedAt ?? undefined}
      data-state={build.state}
      data-lit={focus ? (lit ? 'true' : 'false') : undefined}
      onMouseEnter={() => onFocus(build.document.path)}
      onMouseLeave={() => onFocus(null)}
    >
      <span className="aw-home-dot" data-state={build.state} aria-hidden />
      <div className="aw-home-main">
        <button data-slot="home-open" type="button" className="aw-home-title" onClick={() => onOpen(build.document.path)}>
          {build.document.title}
        </button>
        {relations === 'links' ? <RelationLinks build={build} onOpen={onOpen} /> : null}
      </div>
      <div className="aw-home-facts">
        {running ? (
          <>
            <span>
              {build.tasksDone} of {build.tasksTotal} done
            </span>
            {build.tasksLanding ? <span className="aw-home-landing">{build.tasksLanding} landing</span> : null}
            <span className="aw-home-muted">started {formatAgo(build.startedAt, now)}</span>
          </>
        ) : (
          <>
            <span className="aw-home-muted">{formatAgo(build.finishedAt!, now)}</span>
            <span className="aw-home-cost">{build.spentUsd === null ? 'unpriced' : formatMoney(build.spentUsd)}</span>
          </>
        )}
      </div>
    </li>
  )
}

/** Option A: each row names its roadmap, slice and capabilities as links. */
function RelationLinks({ build, onOpen }: { build: HomeBuild; onOpen: (path: string, anchor?: string) => void }) {
  return (
    <div className="aw-home-rel">
      {build.roadmap ? (
        <span className="aw-home-crumb">
          <Icon name="route" size={12} />
          <button data-slot="home-link" type="button" className="aw-home-link" data-testid="spec-home-link" data-rel="roadmap" data-path={build.roadmap.document.path} onClick={() => onOpen(build.roadmap!.document.path)}>
            {build.roadmap.document.title}
          </button>
          <span className="aw-home-sep">›</span>
          <button data-slot="home-link" type="button" className="aw-home-link" data-testid="spec-home-link" data-rel="slice" data-path={build.roadmap.document.path} onClick={() => onOpen(build.roadmap!.document.path, `slice-${build.roadmap!.slice.key}`)}>
            {build.roadmap.slice.title}
          </button>
        </span>
      ) : (
        <span className="aw-home-muted">Not in a roadmap</span>
      )}
      {build.capabilities.map((c) => (
        <button key={c.path} data-slot="home-link" type="button" className="aw-home-chip" data-testid="spec-home-link" data-rel="capability" data-path={c.path} onClick={() => onOpen(c.path)}>
          <Icon name="layers" size={11} />
          {c.title}
        </button>
      ))}
    </div>
  )
}

/** Option B: one outline, roadmap › slice › change › capabilities, for the shown builds. */
function RelationTree({
  builds,
  focus,
  onFocus,
  onOpen,
}: {
  builds: HomeBuild[]
  focus: string | null
  onFocus: (path: string | null) => void
  onOpen: (path: string, anchor?: string) => void
}) {
  const groups = new Map<string, { roadmap: HomeDocRef | null; builds: HomeBuild[] }>()
  for (const b of builds) {
    const key = b.roadmap?.document.path ?? ''
    if (!groups.has(key)) groups.set(key, { roadmap: b.roadmap?.document ?? null, builds: [] })
    groups.get(key)!.builds.push(b)
  }
  const ordered = [...groups.values()].sort((a, b) => (a.roadmap ? 0 : 1) - (b.roadmap ? 0 : 1))
  const lit = focus ? litBy(builds, focus) : null
  return (
    <section className="aw-home-section" data-testid="spec-home-relations">
      <h2 className="aw-home-h">How it relates</h2>
      <ul className="aw-tree">
        {ordered.map((g) => (
          <li key={g.roadmap?.path ?? 'none'} className="aw-tree-group">
            {g.roadmap ? (
              <button data-slot="home-link" type="button" className="aw-tree-node" data-kind="roadmap" data-lit={lit ? String(lit.has(g.roadmap.path)) : undefined} onClick={() => onOpen(g.roadmap!.path)} onMouseEnter={() => onFocus(g.roadmap!.path)} onMouseLeave={() => onFocus(null)}>
                <Icon name="route" size={13} />
                {g.roadmap.title}
              </button>
            ) : (
              <span className="aw-tree-node" data-kind="none">Not in a roadmap</span>
            )}
            <ul className="aw-tree-children">
              {g.builds.map((b) => (
                <li key={b.id} className="aw-tree-item">
                  {b.roadmap ? <span className="aw-tree-slice">{b.roadmap.slice.title}</span> : null}
                  <button data-slot="home-link" type="button" className="aw-tree-node" data-kind="change" data-state={b.state} data-lit={lit ? String(lit.has(b.document.path)) : undefined} onClick={() => onOpen(b.document.path)} onMouseEnter={() => onFocus(b.document.path)} onMouseLeave={() => onFocus(null)}>
                    <span className="aw-home-dot" data-state={b.state} aria-hidden />
                    {b.document.title}
                  </button>
                  <ul className="aw-tree-caps">
                    {b.capabilities.map((c) => (
                      <li key={c.path}>
                        <button data-slot="home-link" type="button" className="aw-home-chip" data-lit={lit ? String(lit.has(c.path)) : undefined} onClick={() => onOpen(c.path)} onMouseEnter={() => onFocus(c.path)} onMouseLeave={() => onFocus(null)}>
                          <Icon name="layers" size={11} />
                          {c.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  )
}

const ROW = 40
const NODE_H = 30

/** Option C: a drawn map. Roadmaps, the shown changes and their capabilities in three columns,
 *  joined by threads; hovering anything lights what it connects to. */
function RelationMap({
  builds,
  focus,
  onFocus,
  onOpen,
}: {
  builds: HomeBuild[]
  focus: string | null
  onFocus: (path: string | null) => void
  onOpen: (path: string, anchor?: string) => void
}) {
  const roadmaps = uniq(builds.flatMap((b) => (b.roadmap ? [b.roadmap.document] : [])))
  const caps = uniq(builds.flatMap((b) => b.capabilities))
  // Changes ordered by roadmap, so threads from one roadmap stay together and cross less.
  const changes = [...builds].sort((a, b) => order(roadmaps, a) - order(roadmaps, b))
  const rows = Math.max(roadmaps.length, changes.length, caps.length)
  const height = rows * ROW
  const y = (i: number, n: number) => (height - n * ROW) / 2 + i * ROW + NODE_H / 2
  const yR = new Map(roadmaps.map((r, i) => [r.path, y(i, roadmaps.length)]))
  const yC = new Map(changes.map((b, i) => [b.document.path, y(i, changes.length)]))
  const yK = new Map(caps.map((c, i) => [c.path, y(i, caps.length)]))
  const lit = focus ? litBy(builds, focus) : null
  const on = (...paths: string[]) => (lit ? String(paths.every((p) => lit.has(p))) : undefined)

  // Column x, as a share of the drawing's width; the SVG is stretched to the grid.
  const X = { r1: 23, c0: 31, c1: 69, k0: 77 }
  return (
    <section className="aw-home-section" data-testid="spec-home-relations">
      <h2 className="aw-home-h">How it relates</h2>
      <div className="aw-map-heads">
        <span>Roadmaps</span>
        <span>Changes</span>
        <span>Capabilities</span>
      </div>
      <div className="aw-map" style={{ height }}>
        <svg className="aw-map-threads" viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" aria-hidden>
          {changes.map((b) =>
            b.roadmap ? (
              <path key={`r-${b.id}`} className="aw-map-thread" data-lit={on(b.roadmap.document.path, b.document.path)} d={curve(X.r1, yR.get(b.roadmap.document.path)!, X.c0, yC.get(b.document.path)!)} />
            ) : null,
          )}
          {changes.flatMap((b) =>
            b.capabilities.map((c) => (
              <path key={`k-${b.id}-${c.path}`} className="aw-map-thread" data-state={b.state} data-lit={on(b.document.path, c.path)} d={curve(X.c1, yC.get(b.document.path)!, X.k0, yK.get(c.path)!)} />
            )),
          )}
        </svg>
        {roadmaps.map((r) => (
          <MapNode key={r.path} col="roadmap" top={yR.get(r.path)!} lit={lit ? lit.has(r.path) : null} onEnter={() => onFocus(r.path)} onLeave={() => onFocus(null)} onClick={() => onOpen(r.path)}>
            <Icon name="route" size={12} />
            {r.title}
          </MapNode>
        ))}
        {changes.map((b) => (
          <MapNode key={b.id} col="change" top={yC.get(b.document.path)!} state={b.state} lit={lit ? lit.has(b.document.path) : null} onEnter={() => onFocus(b.document.path)} onLeave={() => onFocus(null)} onClick={() => onOpen(b.document.path)} title={b.roadmap ? `Slice: ${b.roadmap.slice.title}` : 'Not in a roadmap'}>
            <span className="aw-home-dot" data-state={b.state} aria-hidden />
            {b.document.title}
          </MapNode>
        ))}
        {caps.map((c) => (
          <MapNode key={c.path} col="capability" top={yK.get(c.path)!} lit={lit ? lit.has(c.path) : null} onEnter={() => onFocus(c.path)} onLeave={() => onFocus(null)} onClick={() => onOpen(c.path)}>
            <Icon name="layers" size={12} />
            {c.title}
          </MapNode>
        ))}
      </div>
    </section>
  )
}

function MapNode({
  col,
  top,
  state,
  lit,
  title,
  onEnter,
  onLeave,
  onClick,
  children,
}: {
  col: 'roadmap' | 'change' | 'capability'
  top: number
  state?: string
  lit: boolean | null
  title?: string
  onEnter: () => void
  onLeave: () => void
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      data-slot="map-node"
      type="button"
      className="aw-map-node"
      data-col={col}
      data-state={state}
      data-lit={lit === null ? undefined : String(lit)}
      style={{ top: top - NODE_H / 2 }}
      title={title}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onFocus={onEnter}
      onBlur={onLeave}
      onClick={onClick}
    >
      <span className="aw-map-node-text">{children}</span>
    </button>
  )
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  const mid = (x1 + x2) / 2
  return `M${x1} ${y1} C${mid} ${y1} ${mid} ${y2} ${x2} ${y2}`
}

function uniq(refs: HomeDocRef[]): HomeDocRef[] {
  const seen = new Map<string, HomeDocRef>()
  refs.forEach((r) => seen.set(r.path, seen.get(r.path) ?? r))
  return [...seen.values()]
}

function order(roadmaps: HomeDocRef[], b: HomeBuild): number {
  const i = b.roadmap ? roadmaps.findIndex((r) => r.path === b.roadmap!.document.path) : roadmaps.length
  return i
}
