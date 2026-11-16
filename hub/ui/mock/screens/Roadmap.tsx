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
import { ScopeList, Section } from '@/components/spec/page/SpecDocumentBody'
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


// The roadmap's other sections, as its document holds them (spec.json, 2026-11-16).
const PROBLEM: string = "Operator, 2026-11-15, with AgentWeave about to be released for other people:\n1. A roadmap reads like any other spec, though it never builds and has its own job: nothing on its page shows slice progress, and drafting the next slice is only offered on Overview.\n2. The corpus is hard to navigate: filters help, but reaching capabilities, seeing what is being built or was built recently, and how documents relate is hard. No view shows roadmap → slice → change → capability relations.\n3. The spec page's task threads are drawn in 14px lanes per dependency depth with every edge from one task sharing one column (SpecDocumentBody.tsx:440-468), so edges sit on top of each other.\n4. The Spec tab forgets the last document opened: only list filters are stored (aw.spec.list.<project>).\n5. A project with no specs is shown \"No documents match.\" and nothing offers to start a corpus; baseline/system-map kinds exist but nothing creates them.\n6. The build retrospective fires when the last task is approved (task_transition_service.py:1333-1344), before its work has landed on main.\n7. An authoring agent reports a document ready to approve while the operator's Check shows many warnings. Three different readiness computations disagree: the save's ready_to_approve counts only three warning codes (agent_actions.py:3016, spec_completeness.py:364-366) and never computes steps_skipped, amendments_unreviewed or vault_warning; Check (spec_service.py:1590-1623) adds those and is clean only with no warnings; Approve (spec_service.py:1554-1587) uses a third list. The BUILD step text says the document \"is then ready for the operator to approve\" unconditionally (spec_journey.py:602). A warning the author judged acceptable leaves no trace on the document. The operator names steps_skipped as the noisiest."
const SCOPE = {
  "in_scope": [
    "The Spec tab and spec page in the app",
    "One readiness verdict shared by the author's save, the operator's Check and Approve, and explicit acknowledgement of warnings",
    "The roadmap document's page and its marker in the spec list",
    "A corpus view of what is building, recently built, and how documents relate",
    "Offering a spec start to a project whose corpus is empty, for existing code and for greenfield",
    "The automatic build retrospective's trigger"
  ],
  "non_goals": [
    "Changing the spec document format or lifecycle phases",
    "Removing the operator's 'approve anyway'",
    "Detecting deploys outside AgentWeave: 'done' means approved and landed on the main branch",
    "Migrating this repository's own corpus (already imported)",
    "The Tasks screen's dependency list view, beyond sharing the thread colours"
  ]
}
const QUESTIONS = [
  {
    "question": "Slice 4 (empty-corpus start) is independent of the visual slices and the largest; should it stay in this roadmap or become its own? Operator, 2026-11-15: it stays in this roadmap.",
    "resolved": true
  },
  {
    "question": "May an author acknowledge a warning instead of fixing it? Operator, 2026-11-15: yes, and the spec must state explicitly that it was acknowledged.",
    "resolved": true
  }
]
const RESTS_ON = {
  "checked": [
    "hub/ui/src/components/spec/page/SpecDocumentBody.tsx:88-121 (roadmap slices section), :440-468 (task threads)",
    "hub/ui/src/components/spec/useSpecPhaseControls.tsx:467 (build controls only for change-spec)",
    "hub/ui/src/components/spec/page/hooks.ts:7-22 (only list prefs persisted)",
    "hub/hub/task_transition_service.py:1311-1344 and hub/hub/chapters_job.py:585-599 (retrospective at last approval)",
    "hub/hub/spec_adoption.py (only adoption of on-disk files exists)",
    "hub/hub/api/v1/agent_actions.py:3009-3020, hub/hub/spec_service.py:413-448, 1554-1623, hub/hub/spec_completeness.py:43-51, 364-366, hub/hub/spec_journey.py:602 (three readiness computations)"
  ],
  "limits": [
    "The UI was not run for this roadmap; findings come from reading the code"
  ]
}

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
          <RoadmapSections />
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

/** Everything else a roadmap holds, below its track, in the page's own sections. The problem's
 *  numbered points are shown as a list (today the page runs them into one paragraph). */
function RoadmapSections() {
  const [lead, ...rest] = PROBLEM.split('\n')
  const points = rest.map((line) => line.replace(/^\d+\.\s*/, '')).filter(Boolean)
  const noop = () => toast({ title: 'Link copied' })
  return (
    <>
      <Section id="problem" title="Problem" findings={[]} flash={null} onCopyLink={noop}>
        <p className="aw-sp-prose">{lead}</p>
        <ol className="mock-rm-points">
          {points.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ol>
      </Section>
      <Section id="scope" title="Scope" findings={[]} flash={null} onCopyLink={noop}>
        <div className="aw-sp-scope">
          <ScopeList title="In scope" icon="check" items={SCOPE.in_scope} />
          <ScopeList title="Not in this roadmap" icon="remove_circle" items={SCOPE.non_goals} />
        </div>
      </Section>
      <Section id="questions" title="Decisions and open questions" findings={[]} flash={null} onCopyLink={noop}>
        <ul className="aw-sp-questions">
          {QUESTIONS.map((q) => (
            <li key={q.question} data-resolved={q.resolved ? 'true' : 'false'}>
              <Icon name={q.resolved ? 'check_circle' : 'help_circle'} size={14} />
              <span>{q.question}</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section id="rests-on" title="What this rests on" findings={[]} flash={null} onCopyLink={noop}>
        <p className="aw-sp-prose">What the author read to write it, and where it stops.</p>
        <ul className="mock-rm-points" data-plain="true">
          {RESTS_ON.checked.map((c) => (
            <li key={c}><code>{c}</code></li>
          ))}
        </ul>
        {RESTS_ON.limits.map((l) => (
          <p key={l} className="aw-rm-warn" data-inline="true"><Icon name="alert_triangle" size={12} />{l}</p>
        ))}
      </Section>
    </>
  )
}
