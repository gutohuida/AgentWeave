import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import type { Task } from '@/api/tasks'
import { FlowGraph, type FlowNode } from '@/components/spec/page/threads/FlowMap'
import { THREAD_STATES, stageThreadState, threadState } from '@/components/spec/page/threads/threadModel'
import { ThreadLegend } from '@/components/spec/page/threads/shared'
import '@/styles/board.css'

export interface DependencyDocument {
  id: string
  title: string
  path: string
}

/** Dependencies as a map, one per spec document: tasks in columns by when they can start, left to
 *  right, with each thread coloured by its prerequisite's state. Each node, a prerequisite from
 *  another document included, words its Hub stage and check state and is coloured by the stage
 *  (`task-stages-in-the-build-view-and-dependency-map` FR-9). Hovering a task lights its chain;
 *  clicking it opens the task, as a row of the list did. A prerequisite another document declares
 *  is drawn faint at the map's left edge, named with its document, so no thread starts nowhere. */
export function DependencyMapView({
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
  const groups = [
    ...documents.map((doc) => ({ doc, tasks: tasks.filter((t) => t.spec_document_id === doc.id) })),
    { doc: null, tasks: tasks.filter((t) => !t.spec_document_id || !documents.some((d) => d.id === t.spec_document_id)) },
  ].filter((g) => g.tasks.length > 0)

  const nodesFor = (group: Task[]): FlowNode[] => {
    const inGroup = new Set(group.map((t) => t.id))
    const outside = new Map<string, FlowNode>()
    for (const t of group)
      for (const p of t.prerequisites ?? [])
        if (!inGroup.has(p.id) && !outside.has(p.id))
          outside.set(p.id, {
            key: p.id,
            title: p.title,
            status: p.status,
            stage: p.stage ?? null,
            check: p.check_state ?? null,
            ref: p.readable_id,
            dependsOn: [],
            outside: (p.spec_document_id && titleOf.get(p.spec_document_id)) || 'another document',
          })
    return [
      ...outside.values(),
      ...group.map((t) => ({
        key: t.id,
        title: t.title,
        status: t.status,
        stage: t.stage ?? null,
        check: t.check_state ?? null,
        agent: t.assignee ?? null,
        ref: t.readable_id,
        dependsOn: (t.prerequisites ?? []).map((p) => p.id),
        flag: t.awaiting_answer_reason ? 'Waiting on you' : null,
      })),
    ]
  }

  const present = new Set(
    tasks.flatMap((t) => (t.prerequisites ?? []).map((p) => (p.stage ? stageThreadState(p.stage) : threadState(p.status)))),
  )

  return (
    <div className="aw-deps" data-layout="map">
      <div className="aw-deps-banner" role="note">
        <Icon name="info" size={14} />
        <span>Dependencies come from each spec document. To change one, edit the document that declares it.</span>
      </div>
      <div className="aw-deps-legend">
        <ThreadLegend states={THREAD_STATES.filter((s) => present.has(s))} />
      </div>
      {groups.map(({ doc, tasks: groupTasks }) => {
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
            <div className="aw-deps-map">
              <FlowGraph nodes={nodesFor(groupTasks)} onSelect={onOpenTask} nodeWidth={208} columnGap={48} legend={false} />
            </div>
          </section>
        )
      })}
    </div>
  )
}
