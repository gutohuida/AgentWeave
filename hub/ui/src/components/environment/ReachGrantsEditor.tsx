import { useState } from 'react'
import type { ReachGrants, ReachRoot } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/input'

const field = 'control-field block px-2 py-1.5 text-xs'

/**
 * What an agent may reach beyond its workspace under Workspace only (reach-1019): roots, each read
 * or read/write, and hosts a shell command may name. Edits the grants only; the caller saves them.
 * Shared by the project's settings and an agent's, where the agent's replace the project's whole.
 */
export function ReachGrantsEditor({
  grants,
  onChange,
  label = 'Granted reach',
}: {
  grants: ReachGrants
  onChange: (grants: ReachGrants) => void
  label?: string
}) {
  const [hostDraft, setHostDraft] = useState('')
  const updateRoot = (index: number, patch: Partial<ReachRoot>) =>
    onChange({
      ...grants,
      roots: grants.roots.map((root, at) => (at === index ? { ...root, ...patch } : root)),
    })
  const addHost = () => {
    const host = hostDraft.trim()
    if (!host || grants.hosts.includes(host)) return
    onChange({ ...grants, hosts: [...grants.hosts, host] })
    setHostDraft('')
  }

  return (
    <div className="space-y-2 w-full" data-testid="reach-grants-editor" aria-label={label}>
      {grants.roots.map((root, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <input
            aria-label={`Granted root ${index + 1}`}
            value={root.path}
            placeholder="C:\\path, {temp} or {project}"
            onChange={(event) => updateRoot(index, { path: event.target.value })}
            className={`${field} flex-1 font-mono`}
          />
          <Select
            aria-label={`Granted root ${index + 1} access`}
            value={root.access}
            onChange={(event) => updateRoot(index, { access: event.target.value as ReachRoot['access'] })}
            wrapperClassName="w-28"
            className="px-2 py-1.5 text-xs"
          >
            <option value="read">Read</option>
            <option value="readwrite">Read and write</option>
          </Select>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={`Remove granted root ${index + 1}`}
            onClick={() => onChange({ ...grants, roots: grants.roots.filter((_, at) => at !== index) })}
          >
            ✕
          </Button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange({ ...grants, roots: [...grants.roots, { path: '', access: 'read' }] })}
        >
          Add root
        </Button>
        {(['{temp}', '{project}'] as const)
          .filter((token) => !grants.roots.some((root) => root.path === token))
          .map((token) => (
            <Button
              key={token}
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange({ ...grants, roots: [...grants.roots, { path: token, access: 'readwrite' }] })}
            >
              Add {token === '{temp}' ? 'the temp folder' : 'the project folder'}
            </Button>
          ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {grants.hosts.map((host) => (
          <span
            key={host}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-mono"
            style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
          >
            {host}
            <button
              type="button"
              aria-label={`Remove granted host ${host}`}
              onClick={() => onChange({ ...grants, hosts: grants.hosts.filter((item) => item !== host) })}
              style={{ color: 'var(--text-3)' }}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          aria-label="Granted host"
          value={hostDraft}
          placeholder="localhost:*"
          onChange={(event) => setHostDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addHost()
            }
          }}
          className={`${field} w-40 font-mono`}
        />
        <Button type="button" variant="outline" size="sm" disabled={!hostDraft.trim()} onClick={addHost}>
          Add host
        </Button>
      </div>
    </div>
  )
}
