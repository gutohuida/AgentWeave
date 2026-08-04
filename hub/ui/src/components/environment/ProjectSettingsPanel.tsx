import { useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { useProjects, useRelocateProject, useUpdateProjectSettings } from '@/api/projects'
import { useConfigStore } from '@/store/configStore'

const inputClass = 'mt-1 block w-full rounded px-2 py-1.5 text-xs'

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

  return (
    <section className="max-w-3xl p-4" aria-labelledby="project-settings-heading">
      <h2 id="project-settings-heading" className="text-sm font-semibold">Project settings</h2>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-xs sm:col-span-2">Project name<input aria-label="Project name" value={name} onChange={(event) => setName(event.target.value)} className={inputClass} style={fieldStyle} /></label>
        <label className="text-xs">Hop budget<input aria-label="Hop budget" type="number" min={1} value={hopBudget} onChange={(event) => setHopBudget(event.target.value)} className={inputClass} style={fieldStyle} /></label>
        <label className="text-xs">Per-turn delivery cap<input aria-label="Per-turn delivery cap" type="number" min={1} value={deliveryCap} onChange={(event) => setDeliveryCap(event.target.value)} className={inputClass} style={fieldStyle} /></label>
        <label className="text-xs">Agent budget<input aria-label="Agent budget" type="number" min={1} value={agentBudget} onChange={(event) => setAgentBudget(event.target.value)} className={inputClass} style={fieldStyle} /></label>
        <label className="text-xs">Token budget<input aria-label="Token budget" type="number" min={1} placeholder="No limit" value={tokenBudget} onChange={(event) => setTokenBudget(event.target.value)} className={inputClass} style={fieldStyle} /></label>
        <label className="flex items-center gap-2 text-xs sm:col-span-2"><input aria-label="Allow agent jobs" type="checkbox" checked={allowAgentJobs} onChange={(event) => setAllowAgentJobs(event.target.checked)} />Allow agent jobs</label>
      </div>
      <button
        type="button"
        className="mt-4"
        disabled={update.isPending || !name.trim()}
        onClick={() => update.mutate({
          name: name.trim(), hop_budget: Number(hopBudget), turn_delivery_cap: Number(deliveryCap),
          agent_budget: Number(agentBudget), token_budget: tokenBudget ? Number(tokenBudget) : null,
          allow_agent_jobs: allowAgentJobs,
        })}
      >
        Save settings
      </button>

      <div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
        <h3 className="text-xs font-semibold">Directory</h3>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>{project.path_display ?? project.working_directory ?? 'No directory bound'}</p>
        {project.directory_state !== 'available' && (
          <div className="mt-3 rounded p-3" style={{ background: 'var(--surface-2)' }}>
            <strong className="text-xs">Directory unavailable</strong>
            <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Locate the same marked project at its new local path.</p>
            <label className="mt-3 block text-xs">New directory path<input aria-label="New directory path" value={newPath} onChange={(event) => setNewPath(event.target.value)} className={inputClass} style={fieldStyle} /></label>
            <button type="button" className="mt-3" disabled={!newPath.trim() || relocate.isPending} onClick={() => relocate.mutate({ path: newPath.trim() })}>Locate project</button>
          </div>
        )}
      </div>
      {error && <div role="alert" className="mt-3 text-xs" style={{ color: 'var(--red)' }}>{error instanceof ApiError ? error.message : 'The update could not be saved.'}</div>}
    </section>
  )
}
