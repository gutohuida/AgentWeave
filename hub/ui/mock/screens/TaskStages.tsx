import * as React from 'react'
import type { Task } from '@/api/tasks'
import { BuildView } from '@/components/builds/BuildView'
import { NO_ADDRESS, type BuildAddress, type BuildRead } from '@/components/builds/buildViewModel'
import { FlowGraph, type FlowNode } from '@/components/spec/page/threads/FlowMap'
import { TaskCard } from '@/components/tasks/TaskCard'
import { CheckStateMarker } from '@/components/tasks/CheckStateMarker'
import { Icon } from '@/components/common/Icon'
import { CHECK_KIND_WORD, type CheckKind, type CheckRunState, type CheckState } from '@/lib/checkState'
import { TONE_COLOR, stageVisual } from '@/lib/taskStageVisual'
import { toast } from '@/lib/toast'
import { buildFor, colorIndexer, nowFor, RECORDED_BUILDS } from '../buildsMock'
import '@/styles/board.css'

/** Every task surface shows the Hub's stage and the task's latest check (spec
 *  `task-stages-in-the-build-view-and-dependency-map`). One page: a key of every stage and check
 *  state, the board's cards, a recorded build's view and a dependency map, all through the
 *  components the app ships. */

// mock state: hand-written tasks, one per stage the Hub reports plus the new pre_review_checks, and
// every check state where it can occur (FR-1, FR-3, FR-13).

const ROSTER = ['Architect', 'Developer', 'QA', 'mender']
const colorOf = (agent: string) => {
  const index = ROSTER.indexOf(agent)
  return index < 0 ? null : index
}
const ago = (now: Date, minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString()
const pre = (state: CheckRunState): CheckState => ({ kind: 'pre_review', state })
const land = (state: CheckRunState): CheckState => ({ kind: 'landing', state })

interface Row {
  ref: string
  title: string
  status: string
  stage: string
  check?: CheckState
  note: string
  fields?: Partial<Task>
}

const ROWS: Row[] = [
  { ref: 'TSIB-1', title: 'Write the stage acceptance drive', status: 'pending', stage: 'not_started', note: 'No check yet: nothing shows.' },
  { ref: 'CNCC-1', title: 'Capability page header', status: 'assigned', stage: 'preparing_checkout', note: 'Its checkout is being written.' },
  { ref: 'TSIB-2', title: 'Hub: pre-review stage, check state, start event', status: 'in_progress', stage: 'working', note: 'Building.' },
  { ref: 'CNCC-2', title: 'Capability page asks which order to use', status: 'in_progress', stage: 'waiting_for_answer', note: 'Needs your answer.', fields: { stage_waits_on: 'Developer', awaiting_answer_reason: 'Order by first or last approval?' } },
  { ref: 'TSIB-3', title: 'Board and build view show stage and check', status: 'completed', stage: 'pre_review_checks', check: pre('waiting'), note: 'New stage. Finished; checks queued for a slot.' },
  { ref: 'TSIB-4', title: 'Map, drawer, spec page, panel, Loop tab, Overview', status: 'completed', stage: 'pre_review_checks', check: pre('running'), note: 'New stage. Finished; checks running.' },
  { ref: 'TSIB-5', title: 'Run the stage acceptance drive', status: 'completed', stage: 'pre_review_checks', check: pre('could_not_run'), note: 'New stage. A check could not run: the review stays held.' },
  { ref: 'SPUWH-2', title: 'Possible facts beside each requirement', status: 'completed', stage: 'waiting_for_review', check: pre('could_not_run'), note: 'The run itself errored: the review may proceed.' },
  { ref: 'SPUWH-3', title: 'Pre-mortem answered on the page', status: 'revision_needed', stage: 'sent_back', check: pre('failed'), note: 'Sent back by its own failing check.' },
  { ref: 'SPUWH-4', title: 'Document tab ends with the pre-mortem', status: 'under_review', stage: 'under_review', check: pre('failed'), note: 'Already in review when a later run failed.' },
  { ref: 'SPUWH-5', title: 'Section titles keep their counts', status: 'under_review', stage: 'under_review', note: 'In review; checks passed, so nothing shows.' },
  { ref: 'SPUWH-6', title: 'Live possible-fact shots', status: 'approved', stage: 'approved_waiting', check: land('waiting'), note: 'Approved; its landing is queued.' },
  { ref: 'CNCC-3', title: 'Capability page shows when a change was built', status: 'approved', stage: 'checking', check: land('running'), note: 'Landing checks running (was "Checking").' },
  { ref: 'CNCC-4', title: 'Waiting changes are ordered by first approval', status: 'approved', stage: 'checking', check: land('waiting'), note: 'Batch formed, run not started.' },
  { ref: 'CNCC-5', title: 'Capability list filters by area', status: 'approved', stage: 'landing', note: 'Checks passed; merging.' },
  { ref: 'CNCC-6', title: 'Capability page links its changes', status: 'approved', stage: 'landing_held', check: land('failed'), note: 'Its batch failed its landing checks; every task of the batch shows it.', fields: { stage_waits_on: 'CNCC-3' } },
  { ref: 'CNCC-7', title: 'Capability empty state', status: 'approved', stage: 'did_not_land', check: land('could_not_run'), note: 'Landing checks could not run.', fields: { stage_detail: 'the landing checks could not start' } },
  { ref: 'GLANCE-1', title: 'Every card shows its real stage', status: 'approved', stage: 'on_main', note: 'On main.', fields: { stage_detail: 'd4c8a34' } },
  { ref: 'TOFMF-5', title: 'Bulk close from the board', status: 'rejected', stage: 'closed', note: 'Closed without landing.' },
]

function taskOf(row: Row, i: number, now: Date): Task {
  return {
    id: `t-${i}`,
    readable_id: row.ref,
    project_id: 'proj-mock',
    title: row.title,
    status: row.status,
    priority: 'medium',
    created_at: ago(now, 600),
    updated: ago(now, 5),
    divergence_policy: 'surface',
    has_open_divergence: false,
    stage: row.stage,
    stage_since: ago(now, 3 + i * 4),
    builder: 'Developer',
    assignee: row.stage === 'under_review' ? 'QA' : 'Developer',
    checker: 'QA',
    ...row.fields,
  } as Task
}

const STAGE_ORDER = [
  'not_started', 'preparing_checkout', 'working', 'waiting_for_answer', 'pre_review_checks', 'waiting_for_review',
  'under_review', 'sent_back', 'approved_waiting', 'checking', 'landing', 'landing_held', 'did_not_land', 'on_main', 'closed',
]
const CHECK_STATES: CheckRunState[] = ['waiting', 'running', 'failed', 'could_not_run']

function Key() {
  return (
    <div className="mock-ts-key">
      <div>
        <h3 className="mock-ts-h">Every stage</h3>
        <ul className="mock-ts-stages">
          {STAGE_ORDER.map((stage) => {
            const v = stageVisual(stage)
            return (
              <li key={stage}>
                <Icon name={v.glyph} size={13} style={{ color: TONE_COLOR[v.tone] }} />
                <span>{v.word}</span>
                {stage === 'pre_review_checks' ? <em>new</em> : stage === 'checking' ? <em>was "Checking"</em> : null}
              </li>
            )
          })}
        </ul>
      </div>
      <div>
        <h3 className="mock-ts-h">Every check state</h3>
        <table className="mock-ts-checks">
          <thead>
            <tr>
              <th />
              <th>Beside its own check stage</th>
              <th>Beside any other stage</th>
            </tr>
          </thead>
          <tbody>
            {(['pre_review', 'landing'] as CheckKind[]).flatMap((kind) =>
              CHECK_STATES.map((state) => (
                <tr key={`${kind}-${state}`}>
                  <th>{CHECK_KIND_WORD[kind]}</th>
                  <td>
                    <CheckStateMarker check={{ kind, state }} stage={kind === 'pre_review' ? 'pre_review_checks' : 'checking'} />
                  </td>
                  <td>
                    <CheckStateMarker check={{ kind, state }} stage={kind === 'pre_review' ? 'sent_back' : 'did_not_land'} />
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
        <p className="mock-ts-note">A check that passed shows nothing: only a check that holds a task or broke is news.</p>
      </div>
    </div>
  )
}

const BUILD_ID = 'build-aba36d302a01'
// mock state: the recorded build's eight tasks, each moved to a stage and check this slice shows.
const BUILD_OVERLAY: Array<{ stage: string; check?: CheckState; status: string }> = [
  { stage: 'on_main', status: 'approved' },
  { stage: 'landing', status: 'approved' },
  { stage: 'checking', check: land('running'), status: 'approved' },
  { stage: 'under_review', status: 'under_review' },
  { stage: 'pre_review_checks', check: pre('running'), status: 'completed' },
  { stage: 'pre_review_checks', check: pre('could_not_run'), status: 'completed' },
  { stage: 'sent_back', check: pre('failed'), status: 'revision_needed' },
  { stage: 'not_started', status: 'pending' },
]

function buildRead(): BuildRead | null {
  const read = buildFor(BUILD_ID, 'recorded')
  if (!read) return null
  read.build = { ...read.build, state: 'running', stopped_at: null }
  read.tasks = read.tasks.map((t, i) => {
    const o = BUILD_OVERLAY[i % BUILD_OVERLAY.length]
    return { ...t, status: o.status as typeof t.status, stage: o.stage, check_state: o.check ?? null }
  })
  return read
}

// mock state: a small chain, each node at a stage with its check.
const MAP_NODES: FlowNode[] = [
  { key: 'a', ref: 'TSIB-1', title: 'Write the stage acceptance drive', stage: 'on_main', agent: 'Developer', dependsOn: [] },
  { key: 'b', ref: 'TSIB-2', title: 'Hub: pre-review stage, check state', stage: 'checking', check: land('running'), agent: 'QA', dependsOn: ['a'] },
  { key: 'c', ref: 'TSIB-3', title: 'Board and build view', stage: 'pre_review_checks', check: pre('could_not_run'), agent: 'Developer', dependsOn: ['b'] },
  { key: 'd', ref: 'TSIB-4', title: 'Map and other surfaces', stage: 'sent_back', check: pre('failed'), agent: 'Developer', dependsOn: ['b'] },
  { key: 'e', ref: 'TSIB-5', title: 'Run the stage acceptance drive', stage: 'not_started', agent: null, dependsOn: ['c', 'd'] },
]

export default function TaskStagesScreen() {
  const now = React.useMemo(() => new Date(), [])
  const read = React.useMemo(buildRead, [])
  const [address, setAddress] = React.useState<BuildAddress>(NO_ADDRESS)
  const buildColor = React.useMemo(() => colorIndexer(RECORDED_BUILDS), [])
  return (
    <div className="mock-ts">
      <section aria-label="Key">
        <Key />
      </section>

      <section aria-label="Board cards">
        <h3 className="mock-ts-h">Board cards</h3>
        <div className="mock-ts-cards">
          {ROWS.map((row, i) => (
            <figure key={row.ref} className="mock-ts-card">
              <TaskCard task={taskOf(row, i, now)} colorOf={colorOf} specTag={row.ref.split('-')[0]} checkState={row.check ?? null} failedChecks={0} now={now} onOpen={() => toast({ title: 'Opens the task' })} />
              <figcaption>{row.note}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section aria-label="Build view">
        <h3 className="mock-ts-h">Build view</h3>
        <div className="mock-ts-frame">
          <BuildView
            read={read}
            status="ready"
            now={nowFor(read)}
            address={address}
            onAddressChange={setAddress}
            onRetry={() => toast({ title: 'Reads the build again' })}
            onOpenDocument={() => toast({ title: 'Opens the spec' })}
            onOpenConversation={() => toast({ title: 'Opens the conversation' })}
            colorIndexOf={buildColor}
          />
        </div>
      </section>

      <section aria-label="Dependency map">
        <h3 className="mock-ts-h">Dependency map</h3>
        <div className="mock-ts-frame aw-deps">
          <div className="aw-deps-map">
            <FlowGraph nodes={MAP_NODES} onSelect={() => toast({ title: 'Opens the task' })} nodeWidth={208} columnGap={48} legend={false} />
          </div>
        </div>
      </section>
    </div>
  )
}