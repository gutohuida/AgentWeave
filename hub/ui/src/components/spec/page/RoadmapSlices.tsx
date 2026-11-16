import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { formatAgo, formatMoney } from '@/lib/format'
import '@/styles/roadmap.css'

/** Where a slice is, read from its change document, its build and its tasks. "Built" is the
 *  retrospective's rule: every task approved and on the main branch. */
export type SliceState = 'not_drafted' | 'drafting' | 'approved' | 'building' | 'built'

export const SLICE_STATE_LABEL: Record<SliceState, string> = {
  not_drafted: 'Not drafted',
  drafting: 'Drafting',
  approved: 'Approved',
  building: 'Building',
  built: 'Built',
}

export interface RoadmapSliceView {
  key: string
  title: string
  intent: string
  done: string
  buildsAfter: string[]
  state: SliceState
  document?: { path: string; title: string }
  /** Tasks on the main branch, of the slice document's tasks. */
  tasks?: { landed: number; total: number }
  /** What the slice's builds cost (building, review, landing, mend), in dollars. */
  costUsd?: number
  unpriced?: number
  /** When it was built, or when its build started. */
  at?: string
}

/** Which slices "Draft" is offered on. `ready`: every slice whose prerequisites are built.
 *  `first`: only the first of those, in roadmap order. `any`: every undrafted slice, with a warning
 *  on one whose prerequisites are not built yet. */
export type DraftRule = 'ready' | 'first' | 'any'

function unbuiltPrerequisites(slice: RoadmapSliceView, slices: RoadmapSliceView[]): RoadmapSliceView[] {
  return slice.buildsAfter.map((k) => slices.find((s) => s.key === k)).filter((s): s is RoadmapSliceView => !!s && s.state !== 'built')
}

function draftOffers(slices: RoadmapSliceView[], rule: DraftRule): Set<string> {
  const undrafted = slices.filter((s) => s.state === 'not_drafted')
  const ready = undrafted.filter((s) => unbuiltPrerequisites(s, slices).length === 0)
  if (rule === 'first') return new Set(ready.slice(0, 1).map((s) => s.key))
  if (rule === 'ready') return new Set(ready.map((s) => s.key))
  return new Set(undrafted.map((s) => s.key))
}

/** The roadmap's progress in one line: a cell per slice, coloured by its state. */
export function RoadmapProgress({ slices, compact }: { slices: Array<Pick<RoadmapSliceView, 'key' | 'title' | 'state'>>; compact?: boolean }) {
  const built = slices.filter((s) => s.state === 'built').length
  return (
    <span className="aw-rm-progress" data-compact={compact ? 'true' : undefined} title={`${built} of ${slices.length} slices built`}>
      <span className="aw-rm-progress-cells" aria-hidden>
        {slices.map((s) => (
          <span key={s.key} className="aw-rm-progress-cell" data-state={s.state} title={`${s.title}: ${SLICE_STATE_LABEL[s.state]}`} />
        ))}
      </span>
      <span className="aw-rm-progress-text">{compact ? `${built}/${slices.length}` : `${built} of ${slices.length} built`}</span>
    </span>
  )
}

export function SliceStateChip({ state }: { state: SliceState }) {
  return (
    <span className="aw-rm-state" data-state={state}>
      {SLICE_STATE_LABEL[state]}
    </span>
  )
}

export interface RoadmapSlicesProps {
  slices: RoadmapSliceView[]
  draftRule: DraftRule
  editing: boolean
  now: Date
  onEditingChange: (editing: boolean) => void
  onDraft: (key: string) => void
  onOpenDocument: (path: string) => void
  onMove: (key: string, to: number) => void
  /** Opens a conversation with the agent the operator picks, seeded with the roadmap; the agent adds the slice (operator, 2026-11-16: agent only). */
  onAddWithAgent: () => void
}

/** A roadmap's slices as a track: what each slice is, where it is, what it cost, and what to do
 *  next. Replaces the plain Slices list on a roadmap's page. */
export function RoadmapSlices(props: RoadmapSlicesProps) {
  const { slices, now } = props
  const offers = draftOffers(slices, props.draftRule)
  const cost = slices.reduce((sum, s) => sum + (s.costUsd ?? 0), 0)
  const unpriced = slices.reduce((sum, s) => sum + (s.unpriced ?? 0), 0)

  return (
    <section className="aw-rm" aria-label="Slices">
      <header className="aw-rm-head">
        <RoadmapProgress slices={slices} />
        <span className="aw-rm-head-cost" title="What this roadmap's builds have cost so far: building, review, landing and mending">
          <Icon name="coins" size={13} />
          {formatMoney(cost)} so far
          {unpriced ? <span className="aw-rm-muted"> · {unpriced} unpriced turns</span> : null}
        </span>
        <span className="aw-rm-head-actions">
          <Button variant={props.editing ? 'primary' : 'ghost'} size="xs" onClick={() => props.onEditingChange(!props.editing)}>
            <Icon name={props.editing ? 'check' : 'pencil'} size={12} />
            {props.editing ? 'Done' : 'Edit slices'}
          </Button>
        </span>
      </header>

      <ol className="aw-rm-track">
        {slices.map((slice, i) => {
          const waiting = unbuiltPrerequisites(slice, slices)
          const offered = offers.has(slice.key)
          const early = offered && waiting.length > 0
          const movable = slice.state === 'not_drafted' || slice.state === 'drafting'
          const ahead = slices.slice(0, i).length
          // Warn, don't refuse: a slice moved ahead of one it builds after keeps its link, and says so.
          const outOfOrder = slice.buildsAfter.filter((k) => slices.findIndex((s) => s.key === k) > i)
          return (
            <li key={slice.key} className="aw-rm-slice" data-state={slice.state} id={`slice-${slice.key}`}>
              <span className="aw-rm-node" data-state={slice.state} aria-hidden>
                {slice.state === 'built' ? <Icon name="check" size={12} /> : i + 1}
              </span>
              <div className="aw-rm-card" data-offered={offered && !early ? 'true' : undefined}>
                <div className="aw-rm-card-head">
                  <strong className="aw-rm-title">{slice.title}</strong>
                  <SliceStateChip state={slice.state} />
                  {props.editing && movable ? (
                    <span className="aw-rm-move">
                      <button data-slot="rm-move" type="button" className="aw-rm-iconbtn" disabled={ahead === 0} onClick={() => props.onMove(slice.key, i - 1)} aria-label="Move up">
                        <Icon name="arrow_upward" size={12} />
                      </button>
                      <button data-slot="rm-move" type="button" className="aw-rm-iconbtn" disabled={i === slices.length - 1} onClick={() => props.onMove(slice.key, i + 1)} aria-label="Move down">
                        <Icon name="arrow_downward" size={12} />
                      </button>
                    </span>
                  ) : null}
                </div>
                {slice.intent ? <p className="aw-rm-intent">{slice.intent}</p> : null}
                <dl className="aw-rm-facts">
                  {slice.done ? (
                    <div>
                      <dt>Done when</dt>
                      <dd>{slice.done}</dd>
                    </div>
                  ) : null}
                  {slice.buildsAfter.length ? (
                    <div>
                      <dt>Builds after</dt>
                      <dd>{slice.buildsAfter.map((k) => slices.find((s) => s.key === k)?.title ?? k).join(', ')}</dd>
                    </div>
                  ) : null}
                </dl>
                {props.editing && outOfOrder.length ? (
                  <p className="aw-rm-warn">
                    <Icon name="alert_triangle" size={12} />
                    Now ahead of {outOfOrder.map((k) => slices.find((s) => s.key === k)?.title ?? k).join(', ')}, which it builds after.
                  </p>
                ) : null}
                <div className="aw-rm-foot">
                  {slice.document ? (
                    <button data-slot="link-button" type="button" className="aw-sp-textbutton" onClick={() => props.onOpenDocument(slice.document!.path)}>
                      <Icon name="article" size={12} />
                      {slice.document.title}
                      <Icon name="arrow_forward" size={11} />
                    </button>
                  ) : null}
                  {slice.tasks ? (
                    <span className="aw-rm-stat">
                      <Icon name="task_alt" size={12} />
                      {slice.tasks.landed} of {slice.tasks.total} tasks on main
                    </span>
                  ) : null}
                  {slice.costUsd !== undefined ? (
                    <span className="aw-rm-stat" title="Building, review, landing and mending">
                      <Icon name="coins" size={12} />
                      {formatMoney(slice.costUsd)}
                    </span>
                  ) : null}
                  {slice.at ? (
                    <span className="aw-rm-stat aw-rm-muted">
                      {slice.state === 'built' ? 'built' : 'started'} {formatAgo(slice.at, now)}
                    </span>
                  ) : null}
                  {offered ? (
                    <span className="aw-rm-draft">
                      {early ? (
                        <span className="aw-rm-warn" data-inline="true">
                          <Icon name="alert_triangle" size={12} />
                          {waiting.map((s) => s.title).join(', ')} not built yet
                        </span>
                      ) : null}
                      <Button variant={early ? 'outline' : 'primary'} size="xs" onClick={() => props.onDraft(slice.key)}>
                        <Icon name="sparkles" size={12} />
                        {early ? 'Draft early' : 'Draft this slice'}
                      </Button>
                    </span>
                  ) : slice.state === 'not_drafted' && waiting.length ? (
                    <span className="aw-rm-stat aw-rm-muted aw-rm-draft">Waits for {waiting.map((s) => s.title).join(', ')}</span>
                  ) : null}
                </div>
              </div>
            </li>
          )
        })}
        {props.editing ? (
          <li className="aw-rm-slice" data-state="new">
            <span className="aw-rm-node" data-state="new" aria-hidden>
              <Icon name="add" size={12} />
            </span>
            <button data-slot="rm-add" type="button" className="aw-rm-add" onClick={props.onAddWithAgent}>
              <Icon name="sparkles" size={12} /> Add a slice with an agent
            </button>
          </li>
        ) : null}
      </ol>
    </section>
  )
}
