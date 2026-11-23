import * as React from 'react'
import { useCharters } from '@/api/charters'
import { useManagerJobs } from '@/api/manager'
import { useProjects, useProjectSettings } from '@/api/projects'
import { useTraceSettings } from '@/api/traces'
import { projectChangedSections } from '@/lib/settingsChanged'
import type { EnvironmentSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { SettingsNavLayout } from './SettingsNavLayout'
import { BudgetsSection } from './sections/BudgetsSection'
import { ChartersSection } from './sections/ChartersSection'
import { DiagnosticsSection } from './sections/DiagnosticsSection'
import { GeneralSection } from './sections/GeneralSection'
import { InstructionsSection } from './sections/InstructionsSection'
import { ManagerSection } from './sections/ManagerSection'
import { SpecStepsSection } from './sections/SpecStepsSection'
import { TracesSection } from './sections/TracesSection'
import { WorktreesSection } from './sections/WorktreesSection'
import { ProjectSetupList } from '@/components/overview/ProjectSetupList'
import { JobsScreen } from '@/components/jobs/JobsScreen'
import { LogsView } from '@/components/logs/LogsView'
import { TracesBrowser } from '@/components/traces/TracesBrowser'
import { ProjectLedger } from '@/components/activity/ProjectLedger'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/** The section list, grouped as the operator approved it (`settings-in-the-app-s-style-where-you-expect-them`).
 *  General is gone: its groups are sections of their own, and its old id lands on Project. */
const SECTIONS: ReadonlyArray<{ id: EnvironmentSection; label: string; icon: string; group: string }> = [
  { id: 'general', label: 'Project', icon: 'folder', group: 'Project' },
  { id: 'collaboration', label: 'Collaboration', icon: 'forum', group: 'Project' },
  { id: 'permissions', label: 'Permissions', icon: 'lock', group: 'Project' },
  { id: 'budgets', label: 'Budgets', icon: 'bar_chart', group: 'Project' },
  { id: 'instructions', label: 'Instructions', icon: 'description', group: 'Profiles' },
  { id: 'charters', label: 'Charters', icon: 'menu_book', group: 'Profiles' },
  { id: 'checkpoints', label: 'Checkpoints', icon: 'book_marked', group: 'Profiles' },
  { id: 'manager', label: 'Manager', icon: 'memory', group: 'Profiles' },
  { id: 'jobs', label: 'Jobs', icon: 'schedule', group: 'Profiles' },
  { id: 'checks', label: 'Checks', icon: 'verified_user', group: 'Landing work' },
  { id: 'landing', label: 'Landing', icon: 'git_merge', group: 'Landing work' },
  { id: 'worktrees', label: 'Worktrees', icon: 'call_split', group: 'Landing work' },
  { id: 'spec-steps', label: 'Spec steps', icon: 'list_tree', group: 'Specs and records' },
  { id: 'traces', label: 'Traces', icon: 'timeline', group: 'Specs and records' },
  { id: 'logs', label: 'Logs', icon: 'description', group: 'Specs and records' },
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
  onOpenTask,
  setting,
  focus = null,
}: {
  section: EnvironmentSection
  onSelectSection: (section: EnvironmentSection) => void
  /** A section pointing elsewhere (a loop's open tasks → Tasks). */
  onNavigate?: (value: string) => void
  /** A ledger row opening its task. */
  onOpenTask?: (taskId: string) => void
  /** Where sound, notifications, appearance and the Hub connection are: the operator's own. */
  onOpenAppSettings?: () => void
  /** The setting the location names, to land on. */
  setting?: string | null
  /** The item the section opens (URL `focus`): a job id in Jobs, a run list in Traces. */
  focus?: string | null
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const project = projects.find((item) => item.id === projectId)
  const { data: charters } = useCharters()
  const { data: jobs } = useManagerJobs()
  const { data: stored, isError: storedFailed } = useProjectSettings(projectId ?? null)
  const { data: traces, isError: tracesFailed } = useTraceSettings()
  const changedUnavailable = storedFailed || tracesFailed
  const changed = React.useMemo(() => (changedUnavailable ? undefined : projectChangedSections(stored, traces)), [changedUnavailable, stored, traces])

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
      // Spend sits beside the limits that govern it (leaner-navigation FR-15).
      body = (
        <>
          <BudgetsSection />
          <div className="aw-settings-embed" data-testid="budgets-ledger">
            <ProjectLedger onOpenTask={(taskId) => onOpenTask?.(taskId)} />
          </div>
        </>
      )
      break
    case 'spec-steps':
      body = <SpecStepsSection />
      break
    case 'traces':
      // The settings, then the project-wide Traces view itself, so no 'Browse traces' button
      // (leaner-navigation FR-14).
      body = (
        <>
          <TracesSection />
          <div className="aw-settings-embed" data-testid="settings-traces-view">
            <TracesBrowser key={focus ?? ''} focus={focus} />
          </div>
        </>
      )
      break
    case 'manager':
      body = <ManagerSection />
      break
    // The Jobs and Logs views, hosted as they were on their retired tabs (leaner-navigation D3).
    case 'jobs':
      body = (
        <JobsScreen
          focus={focus}
          onOpenTasks={(taskIds) => {
            useTaskFilterStore.getState().setActiveTaskIds(taskIds)
            onNavigate?.('tasks')
          }}
        />
      )
      break
    case 'logs':
      body = (
        <div className="aw-settings-logs" style={{ height: 'min(640px, 70vh)', minHeight: 360, border: '1px solid var(--border)', borderRadius: 10, overflow: 'auto' }}>
          <LogsView />
        </div>
      )
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
        landing={setting}
        changed={changed}
        changedUnavailable={changedUnavailable}
        onSelect={onSelectSection}
        footer={onOpenAppSettings ? { label: 'App settings', icon: 'settings', onClick: onOpenAppSettings } : undefined}
      >
        <ProjectSetupList place="settings" showDismissed={section === 'general'} />
        {body}
      </SettingsNavLayout>
    </div>
  )
}
