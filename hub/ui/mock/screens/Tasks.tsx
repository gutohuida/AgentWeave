import * as React from 'react'
import type { Task } from '@/api/tasks'
import { BoardView, type TasksView } from '@/components/tasks/BoardView'
import { DependencyListView } from '@/components/tasks/DependencyListView'
import type { RequirementTally } from '@/components/tasks/TaskCardCompact'
import { toast } from '@/lib/toast'
import { agents, tasks as fixtureTasks } from '../fixtures'
import coverageJson from '../fixtures/spec_coverage.json'
import documentsJson from '../fixtures/spec_documents.json'
import type { ScreenProps } from '../routes'

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

const DOCUMENTS = (documentsJson as { documents: Array<{ id: string; title: string; path: string }> }).documents

export default function Tasks({ now, go }: ScreenProps) {
  const [view, setView] = React.useState<TasksView>('board')
  const [folds, setFolds] = React.useState<Record<string, boolean>>({})
  const [selected, setSelected] = React.useState<string | null>(null)
  const open = (id: string) => {
    setSelected(id)
    toast({ title: 'Opens the task story', description: 'The task drawer is unchanged in this mock.' })
  }
  return (
    <BoardView
      tasks={TASKS}
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
      <DependencyListView tasks={TASKS} documents={DOCUMENTS} onOpenTask={open} onOpenDocument={() => go({ kind: 'tab', tab: 'spec' })} />
    </BoardView>
  )
}
