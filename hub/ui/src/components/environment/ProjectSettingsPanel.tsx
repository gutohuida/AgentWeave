import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '@/api/client'
import { useProjects, useRelocateProject, useUpdateProjectSettings } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { useConfigStore } from '@/store/configStore'

const inputClass = 'block w-48 rounded px-2 py-1.5 text-xs'

export function ProjectSettingsPanel() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const project = projects.find((item) => item.id === projectId)
  const update = useUpdateProjectSettings(projectId ?? '')
  const relocate = useRelocateProject(projectId ?? '')
  const [name, setName] = useState('')
  const [hopBudget, setHopBudget] = useState('')
  const [deliveryCap, setDeliveryCap] = useState('')
  const [agentBudget, setAgentBudget] = useState('')
  const [tokenBudget, setTokenBudget] = useState('')
  const [allowAgentJobs, setAllowAgentJobs] = useState(false)
  const [newPath, setNewPath] = useState('')

  useEffect(() => {
    if (!project) return
    setName(project.name)
    setHopBudget(String(project.hop_budget))
    setDeliveryCap(String(project.turn_delivery_cap))
    setAgentBudget(String(project.agent_budget))
    setTokenBudget(project.token_budget === null ? '' : String(project.token_budget))
    setAllowAgentJobs(project.allow_agent_jobs)
  }, [project])

  if (!project) return null
  const fieldStyle = { background: 'var(--surface-2)', border: '1px solid var(--border)' }
  const error = update.error ?? relocate.error

  const handleSave = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    update.mutate({
      name: name.trim(), hop_budget: Number(hopBudget), turn_delivery_cap: Number(deliveryCap),
      agent_budget: Number(agentBudget), token_budget: tokenBudget ? Number(tokenBudget) : null,
      allow_agent_jobs: allowAgentJobs,
    })
  }

  return (
    <SettingsSection
      title="Settings"
      description="Identity, collaboration limits, and where this project lives on disk."
      actions={(
        <Button
          type="submit"
          form="project-settings-form"
          variant="primary"
          size="sm"
          disabled={update.isPending || !name.trim()}
        >
          Save settings
        </Button>
      )}
    >
      <form id="project-settings-form" onSubmit={handleSave}>
      <SettingsRow label="Project name" description="The name used throughout the Hub to identify this project.">
        <input aria-label="Project name" value={name} onChange={(event) => setName(event.target.value)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Hop budget" description="How many agent-to-agent hops a chain may take before it pauses for you.">
        <input aria-label="Hop budget" type="number" min={1} required value={hopBudget} onChange={(event) => setHopBudget(event.target.value)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Per-turn delivery cap" description="The maximum number of queued deliveries processed during one agent turn.">
        <input aria-label="Per-turn delivery cap" type="number" min={1} required value={deliveryCap} onChange={(event) => setDeliveryCap(event.target.value)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Agent budget" description="The maximum number of agents this project may run at the same time.">
        <input aria-label="Agent budget" type="number" min={1} required value={agentBudget} onChange={(event) => setAgentBudget(event.target.value)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Token budget" description="An optional project-wide token allowance; leave blank for no limit.">
        <input aria-label="Token budget" type="number" min={1} placeholder="No limit" value={tokenBudget} onChange={(event) => setTokenBudget(event.target.value)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Allow agent jobs" description="Agents may create and run scheduled jobs for this project.">
        <input aria-label="Allow agent jobs" type="checkbox" checked={allowAgentJobs} onChange={(event) => setAllowAgentJobs(event.target.checked)} />
      </SettingsRow>
      <SettingsRow label="Directory" description={project.path_display ?? project.working_directory ?? 'No directory bound'}>
        {project.directory_state === 'available' ? (
          <span className="text-xs" style={{ color: 'var(--green)' }}>Available</span>
        ) : (
          <div className="flex items-center gap-2">
            <span className="sr-only">Directory unavailable</span>
            <input aria-label="New directory path" value={newPath} onChange={(event) => setNewPath(event.target.value)} className="block w-64 rounded px-2 py-1.5 text-xs" style={fieldStyle} />
            <Button type="button" variant="outline" size="sm" disabled={!newPath.trim() || relocate.isPending} onClick={() => relocate.mutate({ path: newPath.trim() })}>Locate project</Button>
          </div>
        )}
      </SettingsRow>
      {update.isSuccess && <div role="status" className="py-3 text-xs" style={{ color: 'var(--green)' }}>Settings saved.</div>}
      {relocate.isSuccess && <div role="status" className="py-3 text-xs" style={{ color: 'var(--green)' }}>Project directory updated.</div>}
      {error && <div role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>{error instanceof ApiError ? error.message : 'The update could not be saved.'}</div>}
      </form>
    </SettingsSection>
  )
}
