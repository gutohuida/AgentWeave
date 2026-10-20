import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import type { ReachGrants, ReachRoot } from '@/api/projects'

/** What an agent may reach beyond its workspace, as chips you can read at a glance.
 *
 *  Replaces a row of four loose text buttons ("Add root", "Add the temp folder", "Add the project
 *  folder", "Add host") beside a free text box. Each grant is a chip that says what it is and how
 *  far it goes (read, or read and write); one "Add" menu offers the kinds, and a host or folder is
 *  typed into a field that appears in place. */

const EMPTY: ReachGrants = { roots: [], hosts: [] }

function rootLabel(path: string): string {
  if (path === '{temp}') return 'Temp folder'
  if (path === '{project}') return 'Project folder'
  return path
}

export function ReachGrantsChips({
  grants,
  onChange,
  emptyLabel = 'Nothing beyond the workspace',
  readOnly,
}: {
  grants: ReachGrants | null | undefined
  onChange: (grants: ReachGrants | null) => void
  emptyLabel?: string
  readOnly?: boolean
}) {
  const current = grants ?? EMPTY
  const [adding, setAdding] = React.useState<null | 'folder' | 'host'>(null)
  const [draft, setDraft] = React.useState('')

  const emit = (next: ReachGrants) => onChange(next.roots.length || next.hosts.length ? next : null)
  const addRoot = (root: ReachRoot) => {
    if (current.roots.some((r) => r.path === root.path)) return
    emit({ ...current, roots: [...current.roots, root] })
  }
  const submit = () => {
    const value = draft.trim()
    if (!value) return setAdding(null)
    if (adding === 'host') {
      if (!current.hosts.includes(value)) emit({ ...current, hosts: [...current.hosts, value] })
    } else {
      addRoot({ path: value, access: 'read' })
    }
    setDraft('')
    setAdding(null)
  }

  return (
    <div className="aw-reach">
      <div className="aw-reach-chips">
        {current.roots.length === 0 && current.hosts.length === 0 ? <span className="aw-reach-empty">{emptyLabel}</span> : null}
        {current.roots.map((root) => (
          <span key={root.path} className="aw-reach-chip" title={root.path}>
            <Icon name="folder" size={12} />
            <span className="truncate">{rootLabel(root.path)}</span>
            <button
              type="button"
              data-slot="reach-access"
              className="aw-reach-access"
              disabled={readOnly}
              title="Change access"
              onClick={() =>
                emit({
                  ...current,
                  roots: current.roots.map((r) => (r.path === root.path ? { ...r, access: r.access === 'read' ? 'readwrite' : 'read' } : r)),
                })
              }
            >
              {root.access === 'read' ? 'read' : 'read & write'}
            </button>
            {!readOnly ? (
              <button
                type="button"
                data-slot="reach-remove"
                className="aw-reach-remove"
                aria-label={`Remove ${rootLabel(root.path)}`}
                onClick={() => emit({ ...current, roots: current.roots.filter((r) => r.path !== root.path) })}
              >
                <Icon name="close" size={11} />
              </button>
            ) : null}
          </span>
        ))}
        {current.hosts.map((host) => (
          <span key={host} className="aw-reach-chip">
            <Icon name="public" size={12} />
            <span className="truncate font-mono text-[11.5px]">{host}</span>
            {!readOnly ? (
              <button
                type="button"
                data-slot="reach-remove"
                className="aw-reach-remove"
                aria-label={`Remove ${host}`}
                onClick={() => emit({ ...current, hosts: current.hosts.filter((h) => h !== host) })}
              >
                <Icon name="close" size={11} />
              </button>
            ) : null}
          </span>
        ))}
      </div>
      {!readOnly ? (
        adding ? (
          <form
            className="aw-reach-add-form"
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
          >
            <Input
              autoFocus
              value={draft}
              placeholder={adding === 'host' ? 'localhost:* or registry.npmjs.org' : 'C:\\path\\to\\folder'}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') setAdding(null)
              }}
              aria-label={adding === 'host' ? 'Host' : 'Folder path'}
            />
            <Button type="submit" variant="outline" size="sm">
              Add
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(null)}>
              Cancel
            </Button>
          </form>
        ) : (
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="xs">
                <Icon name="add" size={13} /> Add
              </Button>
            </MenuTrigger>
            <MenuContent align="start">
              <MenuItem icon="folder" onSelect={() => setAdding('folder')}>
                A folder…
              </MenuItem>
              <MenuItem icon="folder_open" onSelect={() => addRoot({ path: '{temp}', access: 'readwrite' })}>
                The temp folder
              </MenuItem>
              <MenuItem icon="folder_open" onSelect={() => addRoot({ path: '{project}', access: 'read' })}>
                The project folder
              </MenuItem>
              <MenuSeparator />
              <MenuItem icon="public" onSelect={() => setAdding('host')}>
                A host…
              </MenuItem>
            </MenuContent>
          </Menu>
        )
      ) : null}
    </div>
  )
}
