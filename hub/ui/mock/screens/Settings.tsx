import * as React from 'react'
import { SettingsNavLayout } from '@/components/settings/SettingsNavLayout'
import { GeneralSettings } from '@/components/settings/GeneralSettings'
import { ManagerSettings } from '@/components/settings/ManagerSettings'
import { RunnersSettings } from '@/components/settings/RunnersSettings'
import { ChartersSettings } from '@/components/settings/ChartersSettings'
import { BudgetsSettings } from '@/components/settings/BudgetsSettings'
import { DiagnosticsSettings, InstructionsSettings, WorktreesSettings } from '@/components/settings/OtherSettings'
import { toast } from '@/lib/toast'
import type { ProjectSettings } from '@/api/projects'
import type { Runner } from '@/api/runners'
import type { Charter } from '@/api/charters'
import type { ManagerFiring, ManagerJob } from '@/api/manager'
import type { AccountingSnapshot } from '@/api/accounting'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import { formatCount } from '@/lib/format'
import { catalogModelOptions, runnerChoiceOptions } from '@/components/settings/settingsOptions'
import { agents, conversations, project } from '../fixtures'
import type { ScreenProps, SettingsSection } from '../routes'
import settingsJson from '../fixtures/settings.json'
import runnersJson from '../fixtures/runners.json'
import chartersJson from '../fixtures/charters.json'
import managerJobsJson from '../fixtures/manager_jobs.json'
import managerActivityJson from '../fixtures/manager_activity.json'
import accountingJson from '../fixtures/accounting.json'
import catalogJson from '../fixtures/model_catalog.json'
import instructionsJson from '../fixtures/instructions.json'
import statusJson from '../fixtures/status.json'
import worktreesJson from '../fixtures/worktrees.json'

const runners = runnersJson as unknown as Runner[]
const charters = chartersJson as unknown as Charter[]
const catalog = catalogJson as unknown as ModelCatalogResponse
const firings = (managerActivityJson as unknown as { firings: ManagerFiring[] }).firings
const instructions = instructionsJson as unknown as { content: string; max_chars?: number }
const status = statusJson as unknown as {
  message_counts: { pending: number; total: number }
  task_counts: Record<string, number>
  question_counts: { unanswered: number; total: number }
  agents_active: string[]
}

const permissionModes = catalog.providers.find((p) => p.provider === 'claude')?.controls?.find((c) => c.id === 'permission_mode')?.values ?? []
const modelsFor = (runner: Runner | undefined) => catalog.providers.find((p) => p.provider === (runner?.cli ?? 'claude'))?.models ?? []

const SECTIONS: Array<{ id: SettingsSection; label: string; icon: string }> = [
  { id: 'general', label: 'General', icon: 'settings' },
  { id: 'manager', label: 'Manager', icon: 'memory' },
  { id: 'runners', label: 'Runners', icon: 'terminal' },
  { id: 'charters', label: 'Charters', icon: 'menu_book' },
  { id: 'instructions', label: 'Instructions', icon: 'description' },
  { id: 'budgets', label: 'Budgets', icon: 'bar_chart' },
  { id: 'worktrees', label: 'Worktrees', icon: 'call_split' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'monitoring' },
]

/** The container a real Project settings route would be: it holds the fetched values, applies a
 *  patch (here to local state, in the app through the settings mutation) and says so in a toast. */
export default function Settings({ route, go, now }: ScreenProps) {
  const section: SettingsSection = route.kind === 'settings' && SECTIONS.some((s) => s.id === route.section) ? route.section : 'general'
  const [settings, setSettings] = React.useState<ProjectSettings>(settingsJson as unknown as ProjectSettings)
  const [jobs, setJobs] = React.useState<ManagerJob[]>((managerJobsJson as unknown as { jobs: ManagerJob[] }).jobs)
  const [accounting, setAccounting] = React.useState<AccountingSnapshot>(accountingJson as unknown as AccountingSnapshot)
  const [instructionText, setInstructionText] = React.useState(instructions.content)

  const say = (title: string) => toast({ title, tone: 'success' })
  const conversationTitle = (id?: string) => conversations.find((c) => c.id === id)?.title ?? null

  const counts: Partial<Record<SettingsSection, React.ReactNode>> = {
    manager: `${jobs.filter((j) => j.enabled).length} on`,
    runners: runners.length,
    charters: charters.length,
  }

  let body: React.ReactNode
  switch (section) {
    case 'general':
      body = (
        <GeneralSettings
          settings={settings}
          runnerOptions={runnerChoiceOptions(runners, { label: 'None', detail: 'Checkpointing stays off until a runner is chosen' }, (r) => modelsFor(r).find((m) => m.id === (settings.checkpoint_model || r.model))?.label ?? 'Provider default')}
          modelOptions={catalogModelOptions(modelsFor(runners.find((r) => r.id === settings.checkpoint_runner_id)), { stored: settings.checkpoint_model })}
          permissionModes={permissionModes}
          mainBranch={{ is_repository: true, suggestion: 'main' }}
          folder={project.working_directory}
          folderAvailable
          onChange={(patch, said) => {
            setSettings((s) => ({ ...s, ...patch }))
            say(said)
          }}
          onOpenBudgets={() => go({ kind: 'settings', section: 'budgets' })}
          onDeleteProject={() => toast({ title: 'Delete project', description: 'Opens the type-to-confirm dialog (unchanged in this mock).' })}
        />
      )
      break
    case 'manager':
      body = (
        <ManagerSettings
          jobs={jobs}
          firings={firings}
          runners={runners}
          modelsFor={modelsFor}
          now={now}
          subjectLabel={(f) => conversationTitle(f.subject.conversation_id) ?? f.detail}
          onChange={(key, input, said) => {
            setJobs((js) => js.map((j) => (j.key === key ? { ...j, ...input } : j)))
            say(said)
          }}
        />
      )
      break
    case 'runners':
      body = (
        <RunnersSettings
          runners={runners}
          modelLabel={(r) => modelsFor(r).find((m) => m.id === r.model)?.label ?? null}
          usedBy={(r) => agents.filter((a) => a.runner_id === r.id).length + jobs.filter((j) => j.runner_id === r.id).length}
          onNew={() => toast({ title: 'New runner', description: 'Opens the runner dialog (unchanged in this mock).' })}
          onEdit={(r) => toast({ title: `Edit ${r.name}`, description: 'Opens the runner dialog (unchanged in this mock).' })}
          onDelete={(r) => toast({ title: `${r.name} deleted`, action: { label: 'Undo', onClick: () => say(`${r.name} restored`) } })}
        />
      )
      break
    case 'charters':
      body = (
        <ChartersSettings
          charters={charters}
          boundTo={(c) => agents.filter((a) => a.charter_id === c.id).map((a) => a.name)}
          onNew={() => toast({ title: 'New charter', description: 'Opens the charter editor (unchanged in this mock).' })}
          onEdit={(c) => toast({ title: `Edit ${c.name}`, description: 'Opens the charter editor (unchanged in this mock).' })}
          onDelete={(c) => toast({ title: `${c.name} deleted`, action: { label: 'Undo', onClick: () => say(`${c.name} restored`) } })}
        />
      )
      break
    case 'instructions':
      body = (
        <InstructionsSettings
          content={instructionText}
          maxChars={instructions.max_chars ?? 40000}
          onSave={(text) => {
            setInstructionText(text)
            say('Instructions saved. New sessions read them.')
          }}
        />
      )
      break
    case 'budgets':
      body = (
        <BudgetsSettings
          accounting={accounting}
          agentColor={(name) => agents.find((a) => a.name === name)?.color_index}
          onSetLimit={(tokens, said) => {
            setAccounting((a) => ({ ...a, budget: { ...a.budget, limit_tokens: tokens } }))
            say(said)
          }}
        />
      )
      break
    case 'worktrees':
      body = <WorktreesSettings listing={{ repository: (worktreesJson as { repository: boolean }).repository, worktrees: [] }} conflicts={[]} />
      break
    case 'diagnostics':
      body = (
        <DiagnosticsSettings
          rawStatus={JSON.stringify(statusJson, null, 2)}
          onCopy={(text) => {
            void navigator.clipboard?.writeText(text)
            say('Status copied')
          }}
          groups={[
            {
              title: 'Project',
              lines: [
                { label: 'Name', value: project.name },
                { label: 'Project id', value: <span className="font-mono text-[12px]">{project.id}</span> },
                { label: 'Agents working now', value: status.agents_active.length ? status.agents_active.join(', ') : 'None' },
              ],
            },
            {
              title: 'Work',
              lines: [
                ...Object.entries(status.task_counts).map(([state, n]) => ({ label: `Tasks ${state.replace('_', ' ')}`, value: formatCount(n) })),
                { label: 'Messages waiting to be delivered', value: formatCount(status.message_counts.pending) },
                { label: 'Messages, all time', value: formatCount(status.message_counts.total) },
                { label: 'Questions waiting for you', value: formatCount(status.question_counts.unanswered) },
              ],
            },
          ]}
        />
      )
      break
  }

  return (
    <SettingsNavLayout
      title="Project settings"
      subtitle={project.name}
      items={SECTIONS.map((s) => ({ ...s, meta: counts[s.id] }))}
      active={section}
      onSelect={(id) => go({ kind: 'settings', section: id })}
    >
      {body}
    </SettingsNavLayout>
  )
}
