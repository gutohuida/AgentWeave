import * as React from 'react'
import { useCharters } from '@/api/charters'
import { useManagerJobs } from '@/api/manager'
import { useProjects } from '@/api/projects'
import { useRunners } from '@/api/runners'
import { SpecStepsSection } from '@/components/environment/SpecStepsSection'
import { TracesSection } from '@/components/environment/TracesSection'
import { QualityHealthPanel } from '@/components/quality/QualityHealthPanel'
import type { EnvironmentSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { SettingsNavLayout } from './SettingsNavLayout'
import { BudgetsSection } from './sections/BudgetsSection'
import { ChartersSection } from './sections/ChartersSection'
import { DiagnosticsSection } from './sections/DiagnosticsSection'
import { GeneralSection } from './sections/GeneralSection'
import { InstructionsSection } from './sections/InstructionsSection'
import { ManagerSection } from './sections/ManagerSection'
import { RunnersSection } from './sections/RunnersSection'
import { WorktreesSection } from './sections/WorktreesSection'

/** The section list, in the order an operator reaches for them. `settings` is the General page
 *  (its id is the route's, kept so existing links still land). */
const SECTIONS: ReadonlyArray<{ id: EnvironmentSection; label: string; icon: string }> = [
  { id: 'settings', label: 'General', icon: 'settings' },
  { id: 'manager', label: 'Manager', icon: 'memory' },
  { id: 'runners', label: 'Runners', icon: 'terminal' },
  { id: 'charters', label: 'Charters', icon: 'menu_book' },
  { id: 'instructions', label: 'Instructions', icon: 'description' },
  { id: 'budgets', label: 'Budgets', icon: 'bar_chart' },
  { id: 'quality', label: 'Quality', icon: 'verified_user' },
  { id: 'worktrees', label: 'Worktrees', icon: 'call_split' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'monitoring' },
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
  /** A section pointing elsewhere (General's token limit → Budgets). */
  onNavigate?: (value: string) => void
  /** Where sound, notifications, appearance and the Hub connection are: the operator's own. */
  onOpenAppSettings?: () => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const project = projects.find((item) => item.id === projectId)
  const { data: runners } = useRunners()
  const { data: charters } = useCharters()
  const { data: jobs } = useManagerJobs()

  const meta: Partial<Record<EnvironmentSection, React.ReactNode>> = {
    manager: jobs ? `${jobs.filter((job) => job.enabled).length} on` : undefined,
    runners: runners?.length,
    charters: charters?.length,
  }

  let body: React.ReactNode
  switch (section) {
    case 'settings':
      body = (
        <>
          <GeneralSection onNavigate={onNavigate ?? ((value) => onSelectSection(value as EnvironmentSection))} />
          <SpecStepsSection />
          <TracesSection />
        </>
      )
      break
    case 'manager':
      body = <ManagerSection />
      break
    case 'runners':
      body = <RunnersSection />
      break
    case 'charters':
      body = <ChartersSection />
      break
    case 'instructions':
      body = <InstructionsSection />
      break
    case 'budgets':
      body = <BudgetsSection />
      break
    case 'quality':
      body = <QualityHealthPanel />
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
