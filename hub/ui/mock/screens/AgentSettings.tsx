import * as React from 'react'
import { SettingsNavLayout } from '@/components/settings/SettingsNavLayout'
import { AgentAccessSettings, AgentExecutionSettings, AgentIdentitySettings, type AgentPatch } from '@/components/agents/settings/AgentSettingsSections'
import { SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import type { AgentSummary } from '@/api/agents'
import type { Runner } from '@/api/runners'
import type { ProjectSettings } from '@/api/projects'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import { agents } from '../fixtures'
import type { AgentSettingsSection, ScreenProps } from '../routes'
import runnersJson from '../fixtures/runners.json'
import settingsJson from '../fixtures/settings.json'
import catalogJson from '../fixtures/model_catalog.json'

const runners = runnersJson as unknown as Runner[]
const projectSettings = settingsJson as unknown as ProjectSettings
const catalog = catalogJson as unknown as ModelCatalogResponse
const permissionModes = catalog.providers.find((p) => p.provider === 'claude')?.controls?.find((c) => c.id === 'permission_mode')?.values ?? []

const SECTIONS: Array<{ id: AgentSettingsSection; label: string; icon: string }> = [
  { id: 'identity', label: 'Identity', icon: 'badge' },
  { id: 'execution', label: 'Execution', icon: 'terminal' },
  { id: 'charter', label: 'Charter', icon: 'menu_book' },
  { id: 'interaction', label: 'Interaction', icon: 'chat' },
  { id: 'context', label: 'Context', icon: 'memory' },
  { id: 'access', label: 'Access', icon: 'lock' },
  { id: 'workspace', label: 'Workspace', icon: 'folder' },
]

/** The container an agent's settings route would be: the agent from the roster, a patch applied
 *  (here locally, in the app through the agent mutation) and confirmed in a toast. */
export default function AgentSettings({ route, go, now }: ScreenProps) {
  const name = route.kind === 'agent-settings' ? route.agent : 'Builder'
  const section: AgentSettingsSection = route.kind === 'agent-settings' ? route.section : 'execution'
  const initial = agents.find((a) => a.name === name) ?? agents[0]!
  const [agent, setAgent] = React.useState<AgentSummary>(initial)
  React.useEffect(() => setAgent(initial), [initial])

  const apply = (patch: AgentPatch, said: string) => {
    setAgent((a) => ({ ...a, ...patch }))
    toast({ title: said, tone: 'success' })
  }

  let body: React.ReactNode
  if (section === 'identity') {
    body = (
      <AgentIdentitySettings
        agent={agent}
        now={now}
        onChange={apply}
        onArchive={() => toast({ title: `${agent.name} archived`, tone: 'success' })}
        onUnarchive={() => toast({ title: `${agent.name} is back`, tone: 'success' })}
      />
    )
  } else if (section === 'execution') {
    body = <AgentExecutionSettings agent={agent} runners={runners} permissionModes={permissionModes} projectGrants={projectSettings.reach_grants ?? null} onChange={apply} />
  } else if (section === 'access') {
    body = <AgentAccessSettings agent={agent} onChange={apply} />
  } else {
    const label = SECTIONS.find((s) => s.id === section)?.label ?? section
    body = (
      <SettingsPage icon={SECTIONS.find((s) => s.id === section)?.icon ?? 'settings'} title={label} description="Unchanged in this mock: these rows move onto the same grid and switches as the sections beside it.">
        <span />
      </SettingsPage>
    )
  }

  return (
    <SettingsNavLayout
      title={`${agent.name} settings`}
      subtitle={agent.runner_id ? runners.find((r) => r.id === agent.runner_id)?.name : 'No runner'}
      back={{ label: `Back to ${agent.name}`, onClick: () => go({ kind: 'conversation', agent: agent.name, conversationId: null }) }}
      items={SECTIONS}
      active={section}
      onSelect={(id) => go({ kind: 'agent-settings', agent: agent.name, section: id })}
    >
      {body}
    </SettingsNavLayout>
  )
}
