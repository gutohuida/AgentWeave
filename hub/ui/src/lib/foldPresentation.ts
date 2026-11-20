/** How the fold dialog words a setting's value, and why a folded agent's composer is closed. */

/** Why a folded agent's composer refuses a turn, naming the profile; undefined for any other. */
export function foldedComposerReason(agent: { name: string; folded_into?: string | null }): string | undefined {
  return agent.folded_into
    ? `${agent.name} was folded into ${agent.folded_into}. This conversation is read-only; message ${agent.folded_into} instead.`
    : undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** One setting's value as a sentence fragment. Unknown is never shown as zero or off: a setting
 *  with no value reads "not set". */
export function describeSettingValue(setting: string, value: unknown): string {
  if (value === null || value === undefined) return 'not set'
  if (typeof value === 'boolean') return value ? 'granted' : 'not granted'
  if (setting.endsWith('_seconds')) return `${String(value)} s`
  if (setting === 'runner' && isRecord(value)) {
    const name = (value.name as string | null) ?? (value.runner_id as string)
    const model = value.model ? ` · ${String(value.model)}` : ''
    return `${name}${model}`
  }
  if (setting === 'charter' && isRecord(value)) return String(value.name ?? value.charter_id)
  if (setting === 'reach_grants' && isRecord(value)) {
    const folders = Array.isArray(value.roots) ? value.roots.length : 0
    const hosts = Array.isArray(value.hosts) ? value.hosts.length : 0
    if (!folders && !hosts) return 'nothing beyond the workspace'
    return [folders ? `${folders} folder${folders === 1 ? '' : 's'}` : '', hosts ? `${hosts} host${hosts === 1 ? '' : 's'}` : '']
      .filter(Boolean)
      .join(', ')
  }
  if (setting === 'checkpoint_policy' && isRecord(value)) {
    const parts = Object.entries(value)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => `${k.replace(/^checkpoint_/, '').replace(/_/g, ' ')} ${String(v)}`)
    return parts.length ? parts.join(', ') : 'project default'
  }
  return typeof value === 'string' ? value : JSON.stringify(value)
}
