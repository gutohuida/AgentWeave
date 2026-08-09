import { useEffect, useState, type FormEvent } from 'react'
import { readableApiError } from '@/api/client'
import {
  useProjectSettings,
  useProjects,
  useRelocateProject,
  useUpdateProjectSettings,
  type ProjectSettings,
} from '@/api/projects'
import { useModelCatalog } from '@/api/modelCatalog'
import { useRunners } from '@/api/runners'
import { Button } from '@/components/ui/button'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { useConfigStore } from '@/store/configStore'

const inputClass = 'block w-48 rounded px-2 py-1.5 text-xs'

/** Token thresholds are stored as an actual count and entered in thousands, because that is the
 *  unit an operator thinks in — "150", not "150000". The conversion lives here, at the only place
 *  that collects the number. */
const TOKENS_PER_UNIT = 1000

function toEntryUnits(mode: string | null, value: number | null): string {
  if (value === null) return ''
  return mode === 'tokens' ? String(Math.round(value / TOKENS_PER_UNIT)) : String(value)
}

function toCanonical(mode: string, entered: string): number | null {
  if (!entered.trim()) return null
  const parsed = Number(entered)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return mode === 'tokens' ? Math.round(parsed * TOKENS_PER_UNIT) : Math.round(parsed)
}

/**
 * The threshold in both readings, where both are knowable.
 *
 * An operator setting one unit is reasoning about the other; making them work it out is how a
 * threshold ends up somewhere it will never fire. Mirrors `checkpoint_policy.describe_threshold`;
 * a test pins the two against the same examples.
 */
export function describeThreshold(
  mode: string | null,
  value: number | null,
  contextWindow: number | null,
): string {
  if (!mode || value === null) return ''
  if (mode === 'percent') {
    if (!contextWindow) return `${value}%`
    return `${value}% — ${Math.round((contextWindow * value) / 100 / 1000)}k of ${Math.round(contextWindow / 1000)}k`
  }
  const thousands = `${Math.round(value / 1000)}k`
  if (!contextWindow) return thousands
  return `${thousands} — ${Math.round((value / contextWindow) * 100)}% of ${Math.round(contextWindow / 1000)}k`
}

const MODE_DESCRIPTION: Record<string, string> = {
  off: 'No checkpoints are produced automatically. You can still write one from a conversation.',
  offered:
    'At the threshold the Hub writes a checkpoint and tells you. Nothing is archived until you cut over.',
  automatic:
    'At the threshold the Hub writes a checkpoint, opens a successor with it, and archives this conversation.',
}

export function ProjectSettingsPanel() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const project = projects.find((item) => item.id === projectId)
  // The stored settings, not `ProjectSummary` — which omits every field added since it was
  // written, and so cannot round-trip them.
  const { data: settings } = useProjectSettings(projectId ?? null)
  const { data: runners = [] } = useRunners()
  const { data: catalog } = useModelCatalog()
  const update = useUpdateProjectSettings(projectId ?? '')
  const relocate = useRelocateProject(projectId ?? '')

  const [form, setForm] = useState<ProjectSettings | null>(null)
  const [thresholdEntry, setThresholdEntry] = useState('')
  const [notesEntry, setNotesEntry] = useState('')
  const [newPath, setNewPath] = useState('')

  useEffect(() => {
    if (!settings) return
    setForm(settings)
    setThresholdEntry(
      toEntryUnits(settings.checkpoint_threshold_mode, settings.checkpoint_threshold_value),
    )
    setNotesEntry(toEntryUnits(settings.checkpoint_threshold_mode, settings.checkpoint_notes_value))
  }, [settings])

  if (!project || !form) return null
  const fieldStyle = { background: 'var(--surface-2)', border: '1px solid var(--border)' }
  const error = update.error ?? relocate.error

  const set = <K extends keyof ProjectSettings>(key: K, value: ProjectSettings[K]) =>
    setForm((current) => (current ? { ...current, [key]: value } : current))

  const checkpointRunner = runners.find((runner) => runner.id === form.checkpoint_runner_id)
  const contextWindow =
    catalog?.providers
      .find((provider) => provider.provider === checkpointRunner?.cli)
      ?.models.find((model) => model.id === form.checkpoint_model)?.context_window ?? null

  const thresholdMode = form.checkpoint_threshold_mode ?? 'percent'
  const previewValue = toCanonical(thresholdMode, thresholdEntry)
  const preview = describeThreshold(thresholdMode, previewValue, contextWindow)

  const handleSave = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const value = toCanonical(thresholdMode, thresholdEntry)
    const notes = toCanonical(thresholdMode, notesEntry)
    // A threshold is a mode and a value together, or neither — never half, which would read as a
    // number in a unit nobody chose.
    update.mutate({
      ...form,
      name: form.name.trim(),
      checkpoint_threshold_mode: value === null ? null : (thresholdMode as 'percent' | 'tokens'),
      checkpoint_threshold_value: value,
      checkpoint_notes_value: value === null ? null : notes,
    })
  }

  return (
    <SettingsSection
      title="Settings"
      description="Identity, collaboration limits, checkpointing, and where this project lives on disk."
      actions={(
        <Button
          type="submit"
          form="project-settings-form"
          variant="primary"
          size="sm"
          disabled={update.isPending || !form.name.trim()}
        >
          Save settings
        </Button>
      )}
    >
      <form id="project-settings-form" onSubmit={handleSave}>
      <SettingsRow label="Project name" description="The name used throughout the Hub to identify this project.">
        <input aria-label="Project name" value={form.name} onChange={(event) => set('name', event.target.value)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Hop budget" description="How many agent-to-agent hops a chain may take before it pauses for you.">
        <input aria-label="Hop budget" type="number" min={1} required value={form.hop_budget} onChange={(event) => set('hop_budget', Number(event.target.value))} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Per-turn delivery cap" description="The maximum number of queued deliveries processed during one agent turn.">
        <input aria-label="Per-turn delivery cap" type="number" min={1} required value={form.turn_delivery_cap} onChange={(event) => set('turn_delivery_cap', Number(event.target.value))} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Agent budget" description="The maximum number of agents this project may run at the same time.">
        <input aria-label="Agent budget" type="number" min={1} required value={form.agent_budget} onChange={(event) => set('agent_budget', Number(event.target.value))} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Token budget" description="An optional project-wide token allowance; leave blank for no limit.">
        <input aria-label="Token budget" type="number" min={1} placeholder="No limit" value={form.token_budget ?? ''} onChange={(event) => set('token_budget', event.target.value ? Number(event.target.value) : null)} className={inputClass} style={fieldStyle} />
      </SettingsRow>
      <SettingsRow label="Allow agent jobs" description="Agents may create and run scheduled jobs for this project.">
        <input aria-label="Allow agent jobs" type="checkbox" checked={form.allow_agent_jobs} onChange={(event) => set('allow_agent_jobs', event.target.checked)} />
      </SettingsRow>

      <SettingsRow label="Automatic checkpointing" description={MODE_DESCRIPTION[form.checkpoint_mode]}>
        <select
          aria-label="Automatic checkpointing"
          value={form.checkpoint_mode}
          onChange={(event) => set('checkpoint_mode', event.target.value as ProjectSettings['checkpoint_mode'])}
          className={inputClass}
          style={fieldStyle}
        >
          <option value="off">Off</option>
          <option value="offered">Offer me one</option>
          <option value="automatic">Do it automatically</option>
        </select>
      </SettingsRow>
      <SettingsRow
        label="Checkpoint at"
        description={
          preview
            ? `Reached at ${preview}. Leave blank to use the built-in default.`
            : 'How full the context gets before a checkpoint is written. Leave blank for the built-in default.'
        }
      >
        <div className="flex items-center gap-2">
          <select
            aria-label="Threshold unit"
            value={thresholdMode}
            onChange={(event) => set('checkpoint_threshold_mode', event.target.value as 'percent' | 'tokens')}
            className="block w-28 rounded px-2 py-1.5 text-xs"
            style={fieldStyle}
          >
            <option value="percent">Percent</option>
            <option value="tokens">K tokens</option>
          </select>
          <input
            aria-label="Checkpoint threshold"
            type="number"
            min={1}
            placeholder="Default"
            value={thresholdEntry}
            onChange={(event) => setThresholdEntry(event.target.value)}
            className="block w-24 rounded px-2 py-1.5 text-xs"
            style={fieldStyle}
          />
        </div>
      </SettingsRow>
      <SettingsRow
        label="Ask for notes at"
        description="Where the agent is asked what the record cannot show. Must be below the checkpoint threshold, or the notes come from the context the checkpoint exists to escape."
      >
        <input
          aria-label="Notes point"
          type="number"
          min={1}
          placeholder="Default"
          value={notesEntry}
          onChange={(event) => setNotesEntry(event.target.value)}
          className="block w-24 rounded px-2 py-1.5 text-xs"
          style={fieldStyle}
        />
      </SettingsRow>
      <SettingsRow label="Continue automatically" description="After a checkpoint hands over, start the successor's first turn without waiting to be asked. Off means a Continue button — never a message you have to invent.">
        <input aria-label="Continue automatically" type="checkbox" checked={form.checkpoint_auto_continue} onChange={(event) => set('checkpoint_auto_continue', event.target.checked)} />
      </SettingsRow>
      <SettingsRow label="Checkpoint runner" description="Which runner writes checkpoints. A cheap model is usually right — the work runs elsewhere.">
        <select
          aria-label="Checkpoint runner"
          value={form.checkpoint_runner_id ?? ''}
          onChange={(event) => set('checkpoint_runner_id', event.target.value || null)}
          className={inputClass}
          style={fieldStyle}
        >
          <option value="">None — checkpointing stays off</option>
          {runners.map((runner) => (
            <option key={runner.id} value={runner.id}>{runner.name}</option>
          ))}
        </select>
      </SettingsRow>
      <SettingsRow label="Checkpoint model" description="Overrides the runner's own model for checkpoint generation.">
        <select
          aria-label="Checkpoint model"
          value={form.checkpoint_model ?? ''}
          onChange={(event) => set('checkpoint_model', event.target.value || null)}
          className={inputClass}
          style={fieldStyle}
        >
          <option value="">Use the runner's model</option>
          {catalog?.providers
            .find((provider) => provider.provider === checkpointRunner?.cli)
            ?.models.map((model) => (
              <option key={model.id} value={model.id}>{model.label}</option>
            ))}
        </select>
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
      {error && <div role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>{readableApiError(error, 'The update could not be saved.')}</div>}
      </form>
    </SettingsSection>
  )
}
