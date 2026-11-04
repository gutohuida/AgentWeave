import type { CoverageEntry } from '@/api/spec'
import { SpecHealthLine } from '@/components/spec/SpecHealthLine'
import { toast } from '@/lib/toast'
import type { NoticeLevel } from './specBanner'

/** The health facts, as the compact header draws them beside the phase. */
export function MockHealth({ level, coverage, tasks }: { level: NoticeLevel; coverage: CoverageEntry[]; tasks: Array<{ id: string; title: string; status: string }> }) {
  return (
    <SpecHealthLine
      coverage={coverage}
      driftCount={0}
      vaultWarnings={level === 'many' ? 2 : 0}
      indexIssues={0}
      tasks={tasks}
      history={[]}
      now={new Date('2026-10-17T12:10:00Z')}
      onScanDrift={() => toast({ title: 'Scans for drift' })}
      onCheckVault={() => toast({ title: 'Checks against the vault' })}
      onOpenTasks={() => toast({ title: 'Opens the tasks' })}
      onOpenRequirement={() => undefined}
    />
  )
}
