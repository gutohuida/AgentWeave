import * as React from 'react'
import type { Task } from '@/api/tasks'
import { BoardView, type TasksView } from '@/components/tasks/BoardView'
import { DependencyListView } from '@/components/tasks/DependencyListView'
import { DependencyMapView } from '@/components/tasks/DependencyMapView'
import type { RequirementTally } from '@/components/tasks/TaskCardCompact'
import { toast } from '@/lib/toast'
import { agents, tasks as fixtureTasks } from '../fixtures'
import coverageJson from '../fixtures/spec_coverage.json'
import documentsJson from '../fixtures/spec_documents.json'
import type { ScreenProps } from '../routes'
import { useTasksMockControls } from '../tasksMock'

// mock state: every task on the replica is approved, so four are re-labelled to show the columns
// and card states a working board has. Nothing else about them is altered.
const RELABEL: Record<string, Partial<Task>> = {
  'task-8ff5baf4880c': { status: 'in_progress' }, // QA1 working
  'task-8d40a4124f40': {
    status: 'in_progress',
    awaiting_answer_reason: 'May search answer from a 30-second cache?',
  },
  'task-5333463eb03d': { status: 'under_review' },
  'task-e7d814d6bb2e': { status: 'revision_needed' },
}
const WORKING = new Set(['task-8ff5baf4880c'])

const TASKS: Task[] = fixtureTasks.map((t) => {
  const own = RELABEL[t.id] ?? {}
  const relabelRef = <R extends { id: string; status: string }>(r: R): R => ({ ...r, status: RELABEL[r.id]?.status ?? r.status })
  return {
    ...t,
    ...own,
    prerequisites: t.prerequisites?.map(relabelRef),
    dependents: t.dependents?.map(relabelRef),
  }
})

const coverage = coverageJson as { requirements: Array<{ requirement_id: string; state: string }> }
const coverageState = new Map(coverage.requirements.map((r) => [r.requirement_id, r.state]))

// The container derives tallies from useSpecCoverage per document. The fixture holds coverage for
// one document; for the others an approved task's requirements count as verified (// mock state).
const TALLIES: Record<string, RequirementTally> = Object.fromEntries(
  TASKS.map((task) => {
    const links = task.requirement_links ?? []
    let verified = 0
    let rejected = 0
    for (const link of links) {
      const state = coverageState.get(link.requirement_id) ?? (task.status === 'approved' ? 'verified' : 'in_progress')
      if (state === 'verified') verified += 1
      if (state === 'rejected' || link.has_rejected_evidence) rejected += 1
    }
    return [task.id, { verified, rejected, total: links.length }]
  }),
)

const RECORDED_DOCUMENTS = (documentsJson as { documents: Array<{ id: string; title: string; path: string }> }).documents

// mock state: a wider build than any recorded one, so fan-out, fan-in, a sent-back task, a question
// waiting on the operator and a prerequisite from another document all show on the map.
const VAULT = { id: 'spdoc-mock-vault', title: 'Knowledge vault: sources, facts and search', path: 'spec/changes/knowledge-vault/spec.json' }
const DESKTOP = TASKS.find((t) => t.id === 'task-0f11a1306866')!
function wideBuild(): Task[] {
  const made: Array<[string, string, string, string | null, string[], Partial<Task>?]> = [
    ['v1', 'Acceptance drive, failing first', 'approved', 'DeveloperSonnet2', []],
    ['v2', 'Docs page for the vault', 'assigned', 'Developer', []],
    ['v3', 'Vault stores sources per project', 'approved', 'DeveloperOpus', ['v1']],
    ['v4', 'Manager distils a source into facts', 'in_progress', 'DeveloperOpus2', ['v3'], { awaiting_answer_reason: 'Distil a PDF page by page or whole?' }],
    ['v5', 'Search across facts and sources', 'revision_needed', 'Developer', ['v3']],
    ['v6', 'Vault map ordered by reads', 'under_review', 'QA2', ['v3']],
    ['v7', 'Agents cite a fact in their turn', 'pending', null, ['v4', 'v5']],
    ['v8', 'Report a wrong entry', 'pending', null, ['v4']],
    ['v9', 'Vault screen', 'pending', null, ['v6', 'v5', DESKTOP.id]],
    ['v10', 'Drive runs green end to end', 'pending', null, ['v7', 'v8', 'v9']],
  ]
  const ref = (id: string) => {
    if (id === DESKTOP.id) return { id, title: DESKTOP.title, status: DESKTOP.status, readable_id: DESKTOP.readable_id, spec_document_id: DESKTOP.spec_document_id }
    const m = made.find((x) => x[0] === id)!
    return { id: `task-mock-${id}`, title: m[1], status: m[2], readable_id: `KV-${id.slice(1)}`, spec_document_id: VAULT.id }
  }
  return made.map(([id, title, status, assignee, deps, extra], i) => ({
    ...fixtureTasks[0]!,
    id: `task-mock-${id}`,
    readable_id: `KV-${id.slice(1)}`,
    title,
    status,
    assignee: assignee ?? undefined,
    spec_document_id: VAULT.id,
    created_at: new Date(Date.UTC(2026, 10, 14, 9, i)).toISOString(),
    awaiting_answer_reason: null,
    prerequisites: deps.map(ref),
    dependents: made.filter((m) => m[4].includes(id)).map((m) => ref(m[0])),
    requirement_links: [],
    ...extra,
  }) as Task)
}
const WIDE = wideBuild()

export default function Tasks({ now, go }: ScreenProps) {
  const { deps, wide } = useTasksMockControls()
  const [view, setView] = React.useState<TasksView>(() => (window.location.hash.includes('deps=') ? 'dependencies' : 'board'))
  const tasks = wide ? [...TASKS, ...WIDE] : TASKS
  const documents = wide ? [...RECORDED_DOCUMENTS, VAULT] : RECORDED_DOCUMENTS
  const [folds, setFolds] = React.useState<Record<string, boolean>>({})
  const [selected, setSelected] = React.useState<string | null>(null)
  const open = (id: string) => {
    setSelected(id)
    toast({ title: 'Opens the task story', description: 'The task drawer is unchanged in this mock.' })
  }
  return (
    <BoardView
      tasks={tasks}
      agents={agents}
      tallies={TALLIES}
      workingTaskIds={WORKING}
      view={view}
      onViewChange={setView}
      folds={folds}
      onFoldsChange={setFolds}
      selectedTaskId={selected}
      onOpenTask={open}
      onRetryIntegration={() => toast({ title: 'Merging again…', description: 'If it fails again, commit or stash the checkout’s changes first.' })}
      now={now}
    >
      {deps === 'map' ? (
        <DependencyMapView tasks={tasks} documents={documents} onOpenTask={open} onOpenDocument={() => go({ kind: 'tab', tab: 'spec' })} />
      ) : (
        <DependencyListView tasks={tasks} documents={documents} onOpenTask={open} onOpenDocument={() => go({ kind: 'tab', tab: 'spec' })} />
      )}
    </BoardView>
  )
}
