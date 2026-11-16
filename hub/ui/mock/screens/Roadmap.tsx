import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Segmented } from '@/components/ui/segmented'
import {
  RoadmapProgress,
  RoadmapSlices,
  SliceStateChip,
  type AddMode,
  type DraftRule,
  type RoadmapSliceView,
} from '@/components/spec/page/RoadmapSlices'
import { toast } from '@/lib/toast'
import '@/styles/spec-page.css'

// mock state: "Today" is this repository's "Spec visuals and navigability" roadmap as it stands on
// 2026-11-16 (slices 1 and 2 built, their real build costs); "Mid-flight" is the same roadmap
// written forward by hand so every slice state shows at once.

const NOW = new Date('2026-11-16T23:00:00Z')

const BASE: Array<Omit<RoadmapSliceView, 'state'>> = [
  {
    key: 'quick-wins',
    title: 'Remembered spec, readable task threads, retrospective after landing',
    intent: 'Opening the Spec tab returns to the last document; task threads in build order are distinct, coloured by state and highlight a chain on hover; the automatic retrospective fires only once every task has landed.',
    done: 'On a live Hub, reopening the Spec tab after an app restart shows the last document, a fan-out of three dependants shows three separate coloured threads, and a retrospective fires after its last landing.',
    buildsAfter: [],
  },
  {
    key: 'one-readiness',
    title: 'Ready means the same thing to the author and the operator',
    intent: "The author's save, the operator's Check and Approve report one list and one verdict. The author may acknowledge a warning with a reason, and the document shows it.",
    done: 'An author’s save that reports ready is followed by a Check with no unacknowledged warnings and an Approve that does not stop.',
    buildsAfter: ['quick-wins'],
  },
  {
    key: 'roadmap-page',
    title: 'A roadmap that is recognisably a roadmap',
    intent: 'A roadmap has its own page layout and controls: each slice’s state at a glance, drafting the next slice, reordering and adding slices, and cost so far; and a distinct marker in the spec list.',
    done: 'An operator can tell a roadmap from a change at a glance, and can draft the next slice, reorder or add a slice and read each slice’s state and cost from the roadmap page alone.',
    buildsAfter: ['quick-wins'],
  },
  {
    key: 'corpus-view',
    title: 'What is being built, what was built, and how it relates',
    intent: 'A corpus view answering what is being built now, what was built most recently, and how each relates to its roadmap, its slice and the capabilities it changes.',
    done: 'From the Spec tab, the operator sees every running build and the latest finished ones, and follows any of them to its roadmap and capabilities and back in one click each.',
    buildsAfter: ['roadmap-page'],
  },
  {
    key: 'empty-corpus-start',
    title: 'A project with no specs is offered a start',
    intent: 'When a project’s corpus is empty the app offers to start one: a system map and capabilities proposed from existing code, or a roadmap interview for a greenfield project.',
    done: 'Registering a project with code and no spec/ shows the offer; each path produces something reviewable.',
    buildsAfter: [],
  },
]

type Scenario = 'today' | 'mid'
const SCENARIOS: Record<Scenario, Record<string, Partial<RoadmapSliceView> & Pick<RoadmapSliceView, 'state'>>> = {
  today: {
    'quick-wins': { state: 'built', document: { path: 'spec/changes/spec-page-remembers', title: 'Spec page remembers, readable task threads' }, tasks: { landed: 4, total: 4 }, costUsd: 11.96, at: '2026-11-16T00:30:34Z' },
    'one-readiness': { state: 'built', document: { path: 'spec/changes/ready-means', title: 'Ready means the same thing to the author and the operator' }, tasks: { landed: 5, total: 5 }, costUsd: 24.42, at: '2026-11-16T16:22:44Z' },
    'roadmap-page': { state: 'not_drafted' },
    'corpus-view': { state: 'not_drafted' },
    'empty-corpus-start': { state: 'not_drafted' },
  },
  mid: {
    'quick-wins': { state: 'built', document: { path: 'a', title: 'Spec page remembers, readable task threads' }, tasks: { landed: 4, total: 4 }, costUsd: 11.96, at: '2026-11-16T00:30:34Z' },
    'one-readiness': { state: 'building', document: { path: 'b', title: 'Ready means the same thing to the author and the operator' }, tasks: { landed: 2, total: 5 }, costUsd: 9.31, unpriced: 2, at: '2026-11-16T19:40:00Z' },
    'roadmap-page': { state: 'approved', document: { path: 'c', title: 'A roadmap that is recognisably a roadmap' } },
    'corpus-view': { state: 'drafting', document: { path: 'd', title: 'What is being built, and how it relates' } },
    'empty-corpus-start': { state: 'not_drafted' },
  },
}

function slicesFor(scenario: Scenario): RoadmapSliceView[] {
  return BASE.map((s) => ({ ...s, ...SCENARIOS[scenario][s.key]! }))
}

/** The roadmap page, with the choices still open (operator, 2026-11-16). */
export default function Roadmap() {
  const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const [scenario, setScenario] = React.useState<Scenario>((params.get('scenario') as Scenario) || 'today')
  const [rule, setRule] = React.useState<DraftRule>((params.get('draft') as DraftRule) || 'ready')
  const [addMode, setAddMode] = React.useState<AddMode>((params.get('add') as AddMode) || 'form')
  const [editing, setEditing] = React.useState(params.get('edit') === '1')
  const [slices, setSlices] = React.useState(() => slicesFor(scenario))
  React.useEffect(() => setSlices(slicesFor(scenario)), [scenario])

  const move = (key: string, to: number) =>
    setSlices((all) => {
      const from = all.findIndex((s) => s.key === key)
      const next = all.slice()
      const [item] = next.splice(from, 1)
      next.splice(to, 0, item!)
      return next
    })

  return (
    <div className="mock-threads">
      <div className="mock-threads-bar">
        <Segmented label="State" value={scenario} onChange={setScenario} options={[{ value: 'today', label: 'Today' }, { value: 'mid', label: 'Mid-flight' }]} />
        <Segmented
          label="Draft offered on"
          value={rule}
          onChange={setRule}
          options={[
            { value: 'ready', label: 'Every ready slice (recommended)' },
            { value: 'first', label: 'Only the next in order' },
            { value: 'any', label: 'Any, warn if early' },
          ]}
        />
        <Segmented label="Add a slice" value={addMode} onChange={setAddMode} options={[{ value: 'form', label: 'Write it myself (recommended)' }, { value: 'agent', label: 'Ask an agent' }]} />
      </div>
      <p className="mock-threads-note">
        The roadmap&apos;s page with its own layout: progress and cost at the top, then each slice on a track with its state, its document, its tasks on
        main and what it cost. &ldquo;Edit slices&rdquo; turns on reordering and adding; a move ahead of a slice it builds after is warned about, not refused.
      </p>

      <div className="mock-rm-page">
        <div className="mock-rm-doc">
          <div className="mock-rm-kind">
            <Icon name="list_tree" size={13} /> Roadmap · approved
          </div>
          <h1 className="mock-rm-h1">Spec visuals and navigability</h1>
          <p className="aw-sp-lede">
            Make the spec corpus easy to read and move through: the Spec tab remembers where you were, task threads are legible, &ldquo;ready to
            approve&rdquo; means the same to the author and the operator, a roadmap looks and acts like a roadmap, and more.
          </p>
          <RoadmapSlices
            slices={slices}
            draftRule={rule}
            addMode={addMode}
            editing={editing}
            now={NOW}
            onEditingChange={setEditing}
            onDraft={(key) => toast({ title: 'Starts drafting this slice', description: `Picks the agent, then opens its conversation on “${slices.find((s) => s.key === key)?.title}”.` })}
            onOpenDocument={() => toast({ title: 'Opens the slice’s change document' })}
            onMove={move}
            onAdd={() => toast({ title: 'Slice added', description: 'Saved to the roadmap at once and listed in its history.' })}
          />
          <p className="mock-threads-note">Below the track the page keeps Summary, Problem and Scope, folded, as on any document.</p>
        </div>

        <aside className="mock-rm-list">
          <div className="mock-rm-kind">In the spec list</div>
          <p className="mock-rm-caption">Today</p>
          <div className="aw-sp-list-row" data-roadmap="true">
            <Icon name="list_tree" size={13} className="aw-sp-list-icon" />
            <span className="aw-sp-list-name">Spec visuals and navigability</span>
            <span className="aw-sp-list-meta">5</span>
          </div>
          <p className="mock-rm-caption">Proposed: progress in the row, state on each slice</p>
          <div className="aw-sp-list-row" data-roadmap="true">
            <Icon name="list_tree" size={13} className="aw-sp-list-icon" />
            <span className="aw-sp-list-name">Spec visuals and navigability</span>
            <RoadmapProgress slices={slices} compact />
          </div>
          {slices.map((s, i) => (
            <div key={s.key} className="aw-sp-list-row mock-rm-sub">
              <span className="aw-sp-list-pos">{i + 1}</span>
              <span className="aw-sp-list-name">{s.title}</span>
              <SliceStateChip state={s.state} />
            </div>
          ))}
        </aside>
      </div>
    </div>
  )
}
