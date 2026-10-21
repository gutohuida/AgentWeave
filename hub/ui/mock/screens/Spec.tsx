import * as React from 'react'
import type { CoverageEntry, SpecDocument } from '@/api/spec'
import { SpecDocumentHeader, type SpecPhase } from '@/components/spec/SpecDocumentHeader'
import { SpecDocumentList } from '@/components/spec/SpecDocumentList'
import { SpecFrame } from '@/components/spec/SpecFrame'
import { SpecHealthLine } from '@/components/spec/SpecHealthLine'
import { toast } from '@/lib/toast'
import '@/styles/spec-header.css'
import { tasks } from '../fixtures'
import coverageJson from '../fixtures/spec_coverage.json'
import documentJson from '../fixtures/spec_document.json'
import documentsJson from '../fixtures/spec_documents.json'
import type { ScreenProps } from '../routes'

interface DocumentRecord {
  id: string
  path: string
  title: string
  kind: string
  phase: SpecPhase
  rigor: string
  updated_at: string
}

const DOCUMENTS = (documentsJson as unknown as { documents: DocumentRecord[] }).documents
const DOC = documentJson as unknown as SpecDocument & {
  approval_outcome?: { created: Array<{ title: string }>; flow?: { messages: string[] } | null }
}
const RECORD = DOCUMENTS.find((d) => d.path === DOC.path)!
const COVERAGE = (coverageJson as unknown as { requirements: CoverageEntry[] }).requirements
const DOC_TASKS = tasks.filter((t) => t.spec_document_id === RECORD.id).map((t) => ({ id: t.id, title: t.title, status: t.status }))

const HISTORY = [
  `Created ${DOC.approval_outcome?.created.length ?? 0} tasks: ${(DOC.approval_outcome?.created ?? []).map((c) => c.title).join(', ')}.`,
  ...(DOC.approval_outcome?.flow?.messages ?? []),
]

function useMode(): 'dark' | 'light' {
  const read = () => (document.documentElement.dataset.mode === 'light' ? 'light' : 'dark')
  const [mode, setMode] = React.useState<'dark' | 'light'>(read)
  React.useEffect(() => {
    const observer = new MutationObserver(() => setMode(read()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-mode'] })
    return () => observer.disconnect()
  }, [])
  return mode
}

const NONE = new Set<string>()

export default function Spec({ go, now }: ScreenProps) {
  const mode = useMode()
  const allDecided = DOC_TASKS.every((t) => t.status === 'approved' || t.status === 'rejected')
  return (
    <div className="aw-spec">
      <SpecDocumentList
        documents={DOCUMENTS}
        active={DOC.path}
        evidenceCount={44}
        onOpen={(path) => path !== DOC.path && toast({ title: 'Opens that document', description: 'The mock holds one document.' })}
        onOpenEvidence={() => toast({ title: 'Opens Evidence', description: 'Unchanged in this mock.' })}
        onNew={() => toast({ title: 'Starts a new change' })}
      />
      <div className="aw-spec-main">
        <SpecDocumentHeader
          path={DOC.path}
          title={RECORD.title}
          kind={RECORD.kind}
          phase={RECORD.phase}
          rigor={RECORD.rigor}
          primary={
            allDecided
              ? {
                  label: 'Fold into capability…',
                  reason: 'Every task is decided. Fold its requirements into the capability they change.',
                  onClick: () => toast({ title: 'Opens the fold dialog', description: 'Unchanged in this mock.' }),
                }
              : null
          }
          onArchive={() => toast({ title: 'Archive is refused while tasks are open', tone: 'error' })}
          onReopen={() => toast({ title: 'Reopened for changes', description: 'Its tasks are kept.', action: { label: 'Undo', onClick: () => undefined } })}
          onDelete={() => toast({ title: 'Delete asks first', description: 'A confirm dialog names the tasks it removes.' })}
          onCopyPath={() => toast({ title: 'Path copied', tone: 'success' })}
          onRigorChange={() => toast({ title: 'Opens the rigor menu' })}
          health={
            <SpecHealthLine
              coverage={COVERAGE}
              driftCount={0}
              lastDriftScan="2026-10-17T09:12:00Z"
              vaultWarnings={0}
              // mock state: the replica's document showed one spec-index (manifest) drift item in
              // today's screenshot; the fixture does not carry the index route, so it is restated.
              indexIssues={1}
              tasks={DOC_TASKS}
              history={HISTORY}
              approvedAt={RECORD.updated_at}
              now={now}
              onScanDrift={() => toast({ title: 'Scanning for drift…' })}
              onCheckVault={() => toast({ title: 'Checking against the vault…' })}
              onOpenTasks={() => go({ kind: 'tab', tab: 'tasks' })}
              onOpenRequirement={(id) => toast({ title: `Scrolls to ${id}` })}
            />
          }
        />
        <div className="aw-spec-body">
          <SpecFrame
            path={DOC.path}
            content={DOC.content}
            mode={mode}
            readablePaths={NONE}
            pendingFragment={null}
            onOutline={() => undefined}
            onActiveSection={() => undefined}
            onNavigate={() => undefined}
            onRejected={() => undefined}
          />
        </div>
      </div>
    </div>
  )
}
