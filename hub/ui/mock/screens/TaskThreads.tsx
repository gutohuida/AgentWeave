import * as React from 'react'
import { Segmented } from '@/components/ui/segmented'
import { TaskList } from '@/components/spec/page/SpecDocumentBody'
import { orderTasks, type DocumentFilters, type SpecTaskView, type TaskStatus } from '@/components/spec/page/model'
import { toast } from '@/lib/toast'
import '@/styles/spec-page.css'

// mock state: three task shapes. The first two are real documents as they stood mid-build (Cairn's
// five-task chain; this repository's "Remembered spec, readable task threads" fork); the third is a
// wider build written by hand so fan-out, fan-in, a sent-back task and a loose task all show.

const t = (key: string, title: string, status: TaskStatus | null, agent: string | null, dependsOn: string[], requirementIds: string[], description = ''): SpecTaskView => ({
  key,
  title,
  status,
  agent,
  dependsOn,
  requirementIds,
  description: description || `What ${title.toLowerCase()} builds, as its spec states it.`,
  taskId: `task-${key}`,
})

const SHAPES = {
  chain: [
    t('drive', 'Acceptance drive, chain format and reading', 'approved', 'Builder', [], ['FR-4', 'FR-5', 'FR-10', 'FR-13', 'FR-17', 'FR-1', 'FR-2']),
    t('create', 'Create command', 'under_review', 'Builder', ['drive'], ['FR-1', 'FR-2', 'FR-3', 'FR-4', 'FR-8']),
    t('resume', 'Resume command', 'in_progress', 'QA2', ['create'], ['FR-6', 'FR-7', 'FR-9', 'FR-14']),
    t('installer', 'Skill installer', 'pending', null, ['resume'], ['FR-18']),
    t('green', 'Installable command and green drive', 'pending', null, ['installer'], ['FR-12', 'FR-7']),
  ],
  fork: [
    t('acceptance-drive', 'Acceptance drive, failing first', 'approved', 'DeveloperSonnet2', [], ['FR-1', 'FR-2', 'FR-4', 'FR-5', 'FR-6', 'FR-8']),
    t('retro-after-landing', 'Retrospective fires after landing', 'in_progress', 'DeveloperSonnet2', ['acceptance-drive'], ['FR-8', 'FR-9', 'FR-10', 'FR-11']),
    t('reopen-last-spec', 'Spec tab reopens the last document', 'under_review', 'Developer', ['acceptance-drive'], ['FR-1', 'FR-2', 'FR-3', 'FR-4']),
    t('readable-threads', 'Readable, coloured task threads', 'pending', 'Developer', ['reopen-last-spec'], ['FR-5', 'FR-6', 'FR-7']),
  ],
  wide: [
    t('drive', 'Acceptance drive, failing first', 'approved', 'DeveloperSonnet2', [], ['FR-1', 'FR-3', 'FR-5', 'FR-7', 'FR-9']),
    t('docs', 'Docs page for the vault', 'assigned', 'Developer', [], ['FR-12']),
    t('store', 'Vault stores sources per project', 'approved', 'DeveloperOpus', ['drive'], ['FR-1', 'FR-2']),
    t('distil', 'Manager distils a source into facts', 'in_progress', 'DeveloperOpus2', ['store'], ['FR-3', 'FR-4']),
    t('search', 'Search across facts and sources', 'revision_needed', 'Developer', ['store'], ['FR-5']),
    t('map', 'Vault map ordered by reads', 'under_review', 'DeveloperSonnet2', ['store'], ['FR-6']),
    t('cite', 'Agents cite a fact in their turn', 'pending', null, ['distil', 'search'], ['FR-7', 'FR-8']),
    t('report', 'Report a wrong entry', 'pending', null, ['distil'], ['FR-9']),
    t('screen', 'Vault screen', 'pending', null, ['map', 'search'], ['FR-10', 'FR-11']),
    t('end', 'Drive runs green end to end', 'pending', null, ['cite', 'report', 'screen'], ['FR-1', 'FR-3', 'FR-5', 'FR-7', 'FR-9']),
  ],
} satisfies Record<string, SpecTaskView[]>

type Shape = keyof typeof SHAPES
const FILTERS: DocumentFilters = { evidence: 'any', task: 'any', status: 'any', agent: 'any', order: 'build' }

/** The spec page's task threads, three ways, for the operator to choose (2026-11-16). */
export default function TaskThreads() {
  const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const [shape, setShape] = React.useState<Shape>((params.get('shape') as Shape) || 'wide')
  // The document column beside the spec list and the contents is about 620px; without the list, wider.
  const [width, setWidth] = React.useState<'page' | 'wide'>((params.get('width') as 'page' | 'wide') || 'page')
  const tasks = React.useMemo(() => orderTasks(SHAPES[shape], FILTERS), [shape])

  return (
    <div className="mock-threads">
      <div className="mock-threads-bar">
        <Segmented
          label="Tasks"
          value={shape}
          onChange={setShape}
          options={[
            { value: 'chain', label: 'A chain of 5' },
            { value: 'fork', label: 'A fork of 4' },
            { value: 'wide', label: 'A wide build of 10' },
          ]}
        />
        <Segmented
          label="Width"
          value={width}
          onChange={setWidth}
          options={[
            { value: 'page', label: 'As on the Spec page' },
            { value: 'wide', label: 'Full width' },
          ]}
        />
      </div>
      <p className="mock-threads-note">The spec page's build order, as the app draws it: a chain is one straight thread, a fork curves into a free lane.</p>
      <section className="aw-sp-section mock-threads-section" data-width={width}>
        <h2 className="aw-sp-section-title">Tasks</h2>
        <TaskList
          key={shape}
          tasks={tasks}
          all={tasks}
          order="build"
          findingsFor={() => []}
          flash={null}
          onJump={() => toast({ title: 'Jumps to that requirement' })}
          onCopyLink={() => toast({ title: 'Link copied' })}
        />
      </section>
    </div>
  )
}
