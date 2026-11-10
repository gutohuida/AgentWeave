import * as React from 'react'
import { useCharters } from '@/api/charters'
import { useManagerJobs } from '@/api/manager'
import { useProjects } from '@/api/projects'
import { SpecStepsSection } from '@/components/environment/SpecStepsSection'
import { TracesSection } from '@/components/environment/TracesSection'
import type { EnvironmentSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { SettingsNavLayout } from './SettingsNavLayout'
import { BudgetsSection } from './sections/BudgetsSection'
import { ChartersSection } from './sections/ChartersSection'
import { DiagnosticsSection } from './sections/DiagnosticsSection'
import { GeneralSection } from './sections/GeneralSection'
import { InstructionsSection } from './sections/InstructionsSection'
import { ManagerSection } from './sections/ManagerSection'
import { WorktreesSection } from './sections/WorktreesSection'

/** The section list, grouped as the operator approved it (`settings-in-the-app-s-style-where-you-expect-them`).
 *  General is gone: its groups are sections of their own, and its old id lands on Project. */
const SECTIONS: ReadonlyArray<{ id: EnvironmentSection; label: string; icon: string; group: string }> = [
  { id: 'general', label: 'Project', icon: 'folder', group: 'Project' },
  { id: 'collaboration', label: 'Collaboration', icon: 'forum', group: 'Project' },
  { id: 'permissions', label: 'Permissions', icon: 'lock', group: 'Project' },
  { id: 'budgets', label: 'Budgets', icon: 'bar_chart', group: 'Project' },
  { id: 'instructions', label: 'Instructions', icon: 'description', group: 'Agents' },
  { id: 'charters', label: 'Charters', icon: 'menu_book', group: 'Agents' },
  { id: 'checkpoints', label: 'Checkpoints', icon: 'book_marked', group: 'Agents' },
  { id: 'manager', label: 'Manager', icon: 'memory', group: 'Agents' },
  { id: 'checks', label: 'Checks', icon: 'verified_user', group: 'Landing work' },
  { id: 'landing', label: 'Landing', icon: 'git_merge', group: 'Landing work' },
  { id: 'worktrees', label: 'Worktrees', icon: 'call_split', group: 'Landing work' },
  { id: 'spec-steps', label: 'Spec steps', icon: 'list_tree', group: 'Specs and records' },
  { id: 'traces', label: 'Traces', icon: 'timeline', group: 'Specs and records' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'monitoring', group: 'Specs and records' },
]

/**
 * Project settings: one page, one name, its own section list (the app's rail stays put).
 *
 * Replaces the rail swapping itself for a configuration menu under three names ("Environment"
 * back link, "Configuration" heading, "Settings" item). Each section is a container on the Hub's
 * hooks; every row applies on change and says so in a toast, except Instructions, a text body,
 * which has the one Save.
 */
export function ProjectSettingsScreen({
  section,
  onSelectSection,
  onNavigate,
  onOpenAppSettings,
}: {
  section: EnvironmentSection
  onSelectSection: (section: EnvironmentSection) => void
  /** A section pointing elsewhere (Traces → the Activity traces view). */
  onNavigate?: (value: string) => void
  /** Where sound, notifications, appearance and the Hub connection are: the operator's own. */
  onOpenAppSettings?: () => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const project = projects.find((item) => item.id === projectId)
  const { data: charters } = useCharters()
  const { data: jobs } = useManagerJobs()

  const meta: Partial<Record<EnvironmentSection, React.ReactNode>> = {
    manager: jobs ? `${jobs.filter((job) => job.enabled).length} on` : undefined,
    charters: charters?.length,
  }

  let body: React.ReactNode
  switch (section) {
    case 'general':
    case 'collaboration':
    case 'permissions':
    case 'checks':
    case 'landing':
    case 'checkpoints':
      body = <GeneralSection part={section} />
      break
    case 'budgets':
      body = <BudgetsSection />
      break
    case 'spec-steps':
      body = <SpecStepsSection />
      break
    case 'traces':
      body = <TracesSection onOpenTraces={() => onNavigate?.('traces')} />
      break
    case 'manager':
      body = <ManagerSection />
      break
    case 'charters':
      body = <ChartersSection />
      break
    case 'instructions':
      body = <InstructionsSection />
      break
    case 'worktrees':
      body = <WorktreesSection />
      break
    case 'diagnostics':
      body = <DiagnosticsSection />
      break
  }

  return (
    <div className="h-full min-h-0" data-testid={`project-settings-${section}`}>
      <SettingsNavLayout
        title="Project settings"
        subtitle={project?.name}
        items={SECTIONS.map((item) => ({ ...item, meta: meta[item.id] }))}
        active={section}
        onSelect={onSelectSection}
        footer={onOpenAppSettings ? { label: 'App settings', icon: 'settings', onClick: onOpenAppSettings } : undefined}
      >
        {body}
      </SettingsNavLayout>
    </div>
  )
}
