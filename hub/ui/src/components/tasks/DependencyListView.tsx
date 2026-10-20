import type { CSSProperties } from 'react'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import type { Task } from '@/api/tasks'
import { taskStatusColor } from '@/lib/taskStatusColors'
import '@/styles/board.css'

export interface DependencyDocument {
  id: string
  title: string
  path: string
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pending',
  assigned: 'Assigned',
  in_progress: 'In progress',
  blocked: 'Waiting on you',
  under_review: 'Under review',
  completed: 'Completed',
  approved: 'Approved',
  rejected: 'Rejected',
  revision_needed: 'Needs revision',
}

/** Dependencies, one chain per spec document, every row naming its task.
 *
 *  Today's view drew collapsed rows reading "1 done · 2 links hidden" that named no task, under a
 *  banner telling the operator to edit a `depends_on` field. Here each document is a group in
 *  order of its chain: a row is the task's status and title, then what it waits on (amber while
 *  that is not approved yet) and what it unblocks. Dependencies are set by the document, so the
 *  banner says that in those words and offers the way there. */
export function DependencyListView({
  tasks,
  documents,
  onOpenTask,
  onOpenDocument,
}: {
  tasks: Task[]
  documents: DependencyDocument[]
  onOpenTask: (taskId: string) => void
  onOpenDocument: (path: string) => void
}) {
  const titleOf = new Map(documents.map((d) => [d.id, d.title]))
  // A prerequisite another document declared is named with that document, so a row never points
  // at a title the operator cannot find on this screen (the DAG board's off-board reference).
  const named = (refs: Array<{ title: string; spec_document_id?: string | null }>, home: string | null) =>
    names(
      refs.map((r) =>
        r.spec_document_id && r.spec_document_id !== home && titleOf.has(r.spec_document_id)
          ? { title: `${r.title} (in ${titleOf.get(r.spec_document_id)})` }
          : r,
      ),
    )
  const groups = [
    ...documents.map((doc) => ({ doc, tasks: tasks.filter((t) => t.spec_document_id === doc.id) })),
    { doc: null, tasks: tasks.filter((t) => !t.spec_document_id || !documents.some((d) => d.id === t.spec_document_id)) },
  ].filter((g) => g.tasks.length > 0)

  return (
    <div className="aw-deps">
      <div className="aw-deps-banner" role="note">
        <Icon name="info" size={14} />
        <span>Dependencies come from each spec document. To change one, edit the document that declares it.</span>
      </div>
      {groups.map(({ doc, tasks: groupTasks }) => {
        const ordered = chainOrder(groupTasks)
        const done = groupTasks.filter((t) => t.status === 'approved').length
        return (
          <section key={doc?.id ?? 'hand-made'} className="aw-deps-group" aria-label={doc?.title ?? 'Made by hand'}>
            <header className="aw-deps-group-head">
              <Icon name={doc ? 'description' : 'edit_note'} size={14} className="aw-deps-group-icon" />
              <h3 className="aw-deps-group-title">{doc?.title ?? 'Made by hand'}</h3>
              <span className="aw-deps-group-meta">
                {done} of {groupTasks.length} approved
              </span>
              {doc ? null : (
                <span className="aw-deps-group-meta" title="A hand-made task's dependencies are set from its task story.">
                  · no document declares these; set them from the task
                </span>
              )}
              {doc ? (
                <Button variant="ghost" size="xs" className="ml-auto" onClick={() => onOpenDocument(doc.path)}>
                  Open document
                  <Icon name="arrow_forward" size={12} />
                </Button>
              ) : null}
            </header>
            <ol className="aw-deps-chain">
              {ordered.map((task) => {
                const waitingOn = (task.prerequisites ?? []).filter((p) => p.status !== 'approved')
                const after = (task.prerequisites ?? []).filter((p) => p.status === 'approved')
                const unblocks = task.dependents ?? []
                return (
                  <li
                    key={task.id}
                    className="aw-deps-row"
                    data-testid={`deps-row-${task.id}`}
                    data-status={task.status}
                    data-dependency-state={task.dependency_state ?? undefined}
                    style={{ '--row-tone': taskStatusColor(task.status, 'var(--text-3)') } as CSSProperties}>
                    <span className="aw-deps-node" aria-hidden="true" />
                    <button type="button" data-slot="deps-row" className="aw-deps-row-main" onClick={() => onOpenTask(task.id)}>
                      <span className="aw-deps-row-line">
                        <span className="aw-deps-status">{STATUS_LABEL[task.status] ?? task.status}</span>
                        <span className="aw-deps-title">{task.title}</span>
                        {task.assignee ? <span className="aw-deps-assignee">@{task.assignee}</span> : null}
                      </span>
                      <span className="aw-deps-relations">
                        {waitingOn.length ? (
                          <span className="aw-deps-waits" data-rejected={waitingOn.some((p) => p.status === 'rejected') ? 'true' : undefined}>
                            Waits on {named(waitingOn, task.spec_document_id ?? null)}
                            {waitingOn.some((p) => p.status === 'rejected') ? ' · a prerequisite was rejected' : ''}
                          </span>
                        ) : after.length ? (
                          <span>After {named(after, task.spec_document_id ?? null)}</span>
                        ) : (
                          <span>Starts the chain</span>
                        )}
                        {unblocks.length ? <span> · unblocks {named(unblocks, task.spec_document_id ?? null)}</span> : null}
                        {task.dependency_state === 'running_on_regressed' ? (
                          <span className="aw-deps-waits" data-rejected="true"> · a prerequisite regressed</span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          </section>
        )
      })}
    </div>
  )
}

function names(refs: Array<{ title: string }>): string {
  if (refs.length <= 2) return refs.map((r) => r.title).join(' and ')
  return `${refs[0]!.title} and ${refs.length - 1} more`
}

/** Prerequisites first; ties keep the list's order. Cycles cannot happen (the Hub refuses them),
 *  but a task whose prerequisite is outside the group simply starts its own run of the chain. */
function chainOrder(tasks: Task[]): Task[] {
  const byId = new Map(tasks.map((t) => [t.id, t]))
  const placed = new Set<string>()
  const out: Task[] = []
  const visit = (task: Task, depth = 0) => {
    if (placed.has(task.id) || depth > tasks.length) return
    for (const pre of task.prerequisites ?? []) {
      const inGroup = byId.get(pre.id)
      if (inGroup) visit(inGroup, depth + 1)
    }
    if (!placed.has(task.id)) {
      placed.add(task.id)
      out.push(task)
    }
  }
  for (const task of [...tasks].sort((a, b) => a.created_at.localeCompare(b.created_at))) visit(task)
  return out
}
